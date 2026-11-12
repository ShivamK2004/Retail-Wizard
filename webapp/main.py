from __future__ import annotations

import csv
import io
import json
import os
import secrets
import sqlite3
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# The desktop modules read RETAIL_WIZARD_DB when app.config is imported.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "retail_wizard.db"
os.environ.setdefault("RETAIL_WIZARD_DB", str(DEFAULT_DB))
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
DEMO_MODE = os.getenv("RETAIL_WIZARD_DEMO_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
os.environ.setdefault("TZ", APP_TIMEZONE)
if hasattr(time, "tzset"):
    try:
        time.tzset()
    except OSError:
        pass

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from app import services
from app.db import connect, init_db
from app.security import hash_password
from app.invoices import generate_invoice_pdf
from app.insights import analyze_business
from app.config import ASSETS_DIR, DB_PATH

LOGIN_ATTEMPTS: dict[str, list[float]] = {}
APP_SECRET = os.getenv("SECRET_KEY", "")
if not APP_SECRET and os.getenv("RENDER"):
    raise RuntimeError("SECRET_KEY must be set in production. Generate a random secret and set it as an environment variable.")
if not APP_SECRET:
    APP_SECRET = "local-development-only-" + secrets.token_urlsafe(32)

app = FastAPI(title="Retail Wizard Web", version="1.0.0")
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "webapp" / "static"), name="static")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "webapp" / "templates"))


@app.on_event("startup")
def startup() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    init_db(DB_PATH)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https" or os.getenv("RENDER"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def get_user(request: Request) -> dict[str, Any] | None:
    value = request.session.get("user")
    return value if isinstance(value, dict) else None


def require_admin(request: Request) -> dict[str, Any]:
    user = get_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return user


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, form: Any) -> None:
    supplied = str(form.get("csrf_token", ""))
    expected = str(request.session.get("csrf", ""))
    if not supplied or not expected or not secrets.compare_digest(supplied, expected):
        raise ValueError("Your form session expired. Refresh the page and try again.")


def flash(request: Request, message: str, kind: str = "success") -> None:
    request.session["flash"] = {"message": message, "kind": kind}


def render(request: Request, name: str, context: dict[str, Any] | None = None, status_code: int = 200):
    user = get_user(request)
    flash_message = request.session.pop("flash", None)
    payload = {
        "request": request,
        "user": user,
        "csrf": csrf_token(request),
        "flash": flash_message,
        "store": services.settings(DB_PATH),
        "page_title": "Retail Wizard",
        "app_version": "Web Edition 1.0",
        "demo_mode": DEMO_MODE,
    }
    if context:
        payload.update(context)
    return templates.TemplateResponse(request=request, name=name, context=payload, status_code=status_code)


def go(path: str, message: str | None = None, kind: str = "success") -> RedirectResponse:
    # Flash is set by the caller, path itself never contains user-provided data.
    return RedirectResponse(path, status_code=303)


def local_dt(raw: Any) -> str:
    if not raw:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(raw))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo(APP_TIMEZONE)).strftime("%d %b %Y, %I:%M:%S %p")
    except (ValueError, TypeError, OverflowError):
        return str(raw)


def parse_items_json(raw: str, label: str = "cart") -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label} data. Please rebuild the {label}.") from exc
    if not isinstance(value, list) or not value:
        raise ValueError(f"Add at least one item to the {label}.")
    if len(value) > 100:
        raise ValueError("Too many line items in one operation.")
    result = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("Invalid line item.")
        result.append(row)
    return result


@app.middleware("http")
async def login_guard(request: Request, call_next):
    path = request.url.path
    public = path in {"/login", "/setup", "/health", "/favicon.ico"} or path.startswith("/static/") or path.startswith("/assets/")
    session_user = get_user(request)
    if session_user:
        with connect(DB_PATH) as conn:
            active_row = conn.execute("SELECT id, full_name, username, role, is_active FROM users WHERE id=?", (session_user.get("id"),)).fetchone()
        if not active_row or not active_row["is_active"]:
            request.session.clear()
            session_user = None
        else:
            request.session["user"] = {"id": active_row["id"], "full_name": active_row["full_name"],
                "username": active_row["username"], "role": active_row["role"]}
    if not public and not session_user:
        return RedirectResponse("/setup" if not services.list_users(DB_PATH) else "/login", status_code=303)
    if path == "/setup" and services.list_users(DB_PATH):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "service": "retail-wizard-web"}


@app.get("/")
def root(request: Request):
    return RedirectResponse("/dashboard" if get_user(request) else ("/setup" if not services.list_users(DB_PATH) else "/login"), status_code=303)


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    if services.list_users(DB_PATH):
        return RedirectResponse("/login", status_code=303)
    return render(request, "auth.html", {"mode": "setup", "page_title": "Create store administrator"})


@app.post("/setup")
async def setup(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form)
        if services.list_users(DB_PATH):
            raise ValueError("Initial setup has already been completed. Ask an administrator to create your account.")
        setup_key = os.getenv("INITIAL_ADMIN_SETUP_KEY", "")
        if not setup_key:
            raise ValueError("Initial administrator setup is locked because INITIAL_ADMIN_SETUP_KEY is not configured.")
        supplied_setup_key = str(form.get("setup_key", ""))
        if not secrets.compare_digest(supplied_setup_key, setup_key):
            raise ValueError("The initial setup key is incorrect.")
        password = str(form.get("password", ""))
        if password != str(form.get("confirm_password", "")):
            raise ValueError("Passwords do not match.")
        services.create_user(str(form.get("full_name", "")), str(form.get("username", "")), password, "admin", DB_PATH)
        flash(request, "Administrator account created. Sign in to continue.")
        return go("/login")
    except Exception as exc:
        return render(request, "auth.html", {"mode": "setup", "error": str(exc)}, 400)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_user(request):
        return RedirectResponse("/dashboard", status_code=303)
    if not services.list_users(DB_PATH):
        return RedirectResponse("/setup", status_code=303)
    return render(request, "auth.html", {"mode": "login", "page_title": "Sign in"})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form)
        username = str(form.get("username", "")).strip()
        client_ip = request.client.host if request.client else "unknown"
        throttle_key = f"{client_ip}:{username.casefold()}"
        now = time.time()
        recent = [stamp for stamp in LOGIN_ATTEMPTS.get(throttle_key, []) if now - stamp < 300]
        LOGIN_ATTEMPTS[throttle_key] = recent
        if len(recent) >= 8:
            raise ValueError("Too many sign-in attempts for this username. Try again in five minutes.")
        user = services.authenticate(username, str(form.get("password", "")), DB_PATH)
        if not user:
            LOGIN_ATTEMPTS[throttle_key].append(now)
            raise ValueError("Username or password is incorrect, or the account is inactive.")
        LOGIN_ATTEMPTS.pop(throttle_key, None)
        request.session.clear()
        request.session["user"] = user
        csrf_token(request)
        flash(request, f"Welcome back, {user['full_name']}.")
        return go("/dashboard")
    except Exception as exc:
        return render(request, "auth.html", {"mode": "login", "error": str(exc)}, 401)


@app.post("/logout")
async def logout(request: Request):
    form = await request.form()
    check_csrf(request, form)
    request.session.clear()
    return go("/login")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    metrics = services.dashboard_metrics(DB_PATH)
    recent = services.list_sales(limit=12, db_path=DB_PATH)
    for row in recent:
        row["sold_at_local"] = local_dt(row.get("sold_at"))
    return render(request, "dashboard.html", {"metrics": metrics, "recent": recent,
        "low_stock": services.list_low_stock(DB_PATH)[:8], "page_title": "Dashboard"})


@app.get("/products", response_class=HTMLResponse)
def products_page(request: Request, q: str = ""):
    rows = services.list_products(search=q, include_inactive=get_user(request)["role"] == "admin", db_path=DB_PATH)
    return render(request, "products.html", {"products": rows, "q": q, "page_title": "Products"})


@app.post("/products/create")
async def product_create(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); user = require_admin(request)
        data = {key: form.get(key, "") for key in ("sku", "barcode", "name", "category", "brand", "unit", "price", "cost_price", "discount_percent", "tax_percent", "stock_qty", "reorder_level", "expiry_date")}
        services.create_product(data, user["id"], DB_PATH)
        flash(request, "Product added successfully.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return go("/products")


@app.post("/products/{product_id}/adjust")
async def product_adjust(request: Request, product_id: int):
    form = await request.form()
    try:
        check_csrf(request, form); user = require_admin(request)
        services.adjust_stock(product_id, float(form.get("quantity_delta", 0)), str(form.get("reason", "Manual adjustment")), user["id"], DB_PATH)
        flash(request, "Stock quantity updated.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return go("/products")


@app.get("/pos", response_class=HTMLResponse)
def pos_page(request: Request, q: str = ""):
    products = services.list_products(search=q, db_path=DB_PATH)
    qr = next((p for p in [ASSETS_DIR / "store_upi_qr.jpeg", ASSETS_DIR / "store_upi_qr.jpg", ASSETS_DIR / "store_upi_qr.png"] if p.is_file()), None)
    return render(request, "pos.html", {"products": products, "q": q,
        "qr_url": f"/assets/{qr.name}" if qr else None, "page_title": "Point of Sale"})


@app.get("/assets/{filename}")
def assets(filename: str):
    if filename not in {"store_upi_qr.jpeg", "store_upi_qr.jpg", "store_upi_qr.png"}:
        return Response(status_code=404)
    path = ASSETS_DIR / filename
    if not path.is_file():
        return Response(status_code=404)
    from fastapi.responses import FileResponse
    return FileResponse(path)


@app.post("/pos/checkout")
async def checkout(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); user = get_user(request)
        items = parse_items_json(str(form.get("items_json", "")))
        result = services.create_sale(
            items=items,
            customer_name=str(form.get("customer_name", "")),
            customer_phone=str(form.get("customer_phone", "")),
            cashier_id=user["id"],
            payment_method=str(form.get("payment_method", "Cash")),
            amount_tendered=form.get("amount_tendered", 0),
            payment_reference=str(form.get("payment_reference", "")),
            order_discount_percent=float(form.get("order_discount_percent", 0) or 0),
            upi_confirmed=str(form.get("upi_confirmed", "")) == "on",
            notes=str(form.get("notes", "")), db_path=DB_PATH)
        flash(request, f"Sale recorded: {result['invoice_no']} · ₹{result['total']:.2f}")
        return go(f"/sales/{result['id']}")
    except Exception as exc:
        flash(request, str(exc), "error")
        return go("/pos")


@app.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request, q: str = ""):
    rows = services.list_sales(search=q, db_path=DB_PATH)
    for row in rows:
        row["sold_at_local"] = local_dt(row.get("sold_at"))
    return render(request, "sales.html", {"sales": rows, "q": q, "page_title": "Sales History"})


@app.get("/sales/{sale_id}", response_class=HTMLResponse)
def sale_detail_page(request: Request, sale_id: int):
    sale = services.sale_detail(sale_id, DB_PATH)
    if not sale:
        flash(request, "Transaction not found.", "error")
        return go("/sales")
    sale["sold_at_local"] = local_dt(sale.get("sold_at"))
    for refund in sale["refunds"]:
        refund["created_at_local"] = local_dt(refund.get("created_at"))
    return render(request, "sale_detail.html", {"sale": sale, "page_title": sale["invoice_no"]})


@app.get("/sales/{sale_id}/refund", response_class=HTMLResponse)
def refund_page(request: Request, sale_id: int):
    sale = services.sale_detail(sale_id, DB_PATH)
    if not sale:
        flash(request, "Transaction not found.", "error"); return go("/sales")
    for item in sale["items"]:
        item["remaining"] = max(0.0, float(item["quantity"]) - float(item["refunded_qty"]))
    return render(request, "refund.html", {"sale": sale, "page_title": "Record refund"})


@app.post("/sales/{sale_id}/refund")
async def refund_create(request: Request, sale_id: int):
    form = await request.form()
    try:
        check_csrf(request, form); user = get_user(request)
        quantities: dict[int, float] = {}
        for key, value in form.items():
            if str(key).startswith("qty_") and str(value).strip():
                try: qty = float(value)
                except ValueError: raise ValueError("Refund quantities must be numeric.")
                if qty > 0: quantities[int(str(key)[4:])] = qty
        result = services.refund_sale(sale_id, quantities, str(form.get("reason", "Customer return")),
            user["id"], str(form.get("payment_method", "Original method")),
            str(form.get("restock", "")) == "on", DB_PATH)
        flash(request, f"Refund {result['refund_no']} recorded: ₹{result['amount']:.2f}.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return go(f"/sales/{sale_id}")


@app.get("/sales/{sale_id}/invoice.pdf")
def invoice_pdf(sale_id: int, view: bool = False):
    sale = services.sale_detail(sale_id, DB_PATH)
    if not sale:
        return Response("Transaction not found", status_code=404)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / f"{sale['invoice_no']}.pdf"
            generate_invoice_pdf(sale, target, services.settings(DB_PATH))
            content = target.read_bytes()
        disposition = "inline" if view else "attachment"
        headers = {"Content-Disposition": f'{disposition}; filename="{sale["invoice_no"]}.pdf"'}
        return Response(content, media_type="application/pdf", headers=headers)
    except Exception as exc:
        return Response(f"Could not generate invoice: {exc}", status_code=500)


@app.get("/purchases", response_class=HTMLResponse)
def purchases_page(request: Request):
    require_admin(request)
    return render(request, "purchases.html", {"products": services.list_products(db_path=DB_PATH),
        "purchases": services.list_purchases(DB_PATH), "page_title": "Purchases"})


@app.post("/purchases")
async def purchase_create(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); user = require_admin(request)
        items = parse_items_json(str(form.get("items_json", "")), "purchase")
        result = services.create_purchase(str(form.get("supplier_name", "")), items, user["id"],
                                          str(form.get("notes", "")), DB_PATH)
        flash(request, f"Purchase {result['purchase_no']} saved. Stock quantities updated.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return go("/purchases")


@app.get("/expenses", response_class=HTMLResponse)
def expenses_page(request: Request):
    require_admin(request)
    return render(request, "expenses.html", {"expenses": services.list_expenses(db_path=DB_PATH), "now_date": date.today().isoformat(), "page_title": "Expenses"})


@app.post("/expenses")
async def expense_create(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); user = require_admin(request)
        services.add_expense(str(form.get("category", "")), str(form.get("description", "")),
            form.get("amount", 0), str(form.get("expense_date", "")), user["id"], DB_PATH)
        flash(request, "Expense recorded.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return go("/expenses")


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, type: str = "sales", start_date: str = "", end_date: str = ""):
    require_admin(request)
    allowed = {"sales", "stock", "best_sellers", "transactions", "purchases"}
    if type not in allowed: type = "sales"
    rows = services.report_data(type, start_date or None, end_date or None, DB_PATH)
    pnl = services.profit_loss(start_date or None, end_date or None, DB_PATH)
    return render(request, "reports.html", {"rows": rows, "report_type": type, "start_date": start_date,
        "end_date": end_date, "pnl": pnl, "page_title": "Reports"})


@app.get("/reports/export.csv")
def report_export(request: Request, type: str = "sales", start_date: str = "", end_date: str = ""):
    require_admin(request)
    allowed = {"sales", "stock", "best_sellers", "transactions", "purchases"}
    if type not in allowed:
        return Response("Unknown report type", status_code=400)
    rows = services.report_data(type, start_date or None, end_date or None, DB_PATH)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="retail-wizard-{type}.csv"'})


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request):
    require_admin(request)
    data = analyze_business(str(DB_PATH))
    return render(request, "insights.html", {"analysis": data, "page_title": "AI Business Insights"})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    require_admin(request)
    return render(request, "settings.html", {"users": services.list_users(DB_PATH), "settings": services.settings(DB_PATH),
        "page_title": "Users & Settings"})


@app.post("/settings/store")
async def settings_update(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); user = require_admin(request)
        values = {key: form.get(key, "") for key in ("store_name", "store_address", "store_phone", "store_email", "low_stock_threshold", "default_tax_percent", "upi_vpa")}
        services.update_settings(values, user["id"], DB_PATH)
        flash(request, "Store settings saved.")
    except Exception as exc: flash(request, str(exc), "error")
    return go("/settings")


@app.post("/settings/users")
async def user_create(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); require_admin(request)
        services.create_user(str(form.get("full_name", "")), str(form.get("username", "")),
            str(form.get("password", "")), str(form.get("role", "cashier")), DB_PATH)
        flash(request, "User account created.")
    except Exception as exc: flash(request, str(exc), "error")
    return go("/settings")


@app.post("/settings/users/{target_id}/active")
async def user_active(request: Request, target_id: int):
    form = await request.form()
    try:
        check_csrf(request, form); user = require_admin(request)
        services.set_user_active(target_id, str(form.get("active", "")) == "1", user["id"], DB_PATH)
        flash(request, "User status updated.")
    except Exception as exc: flash(request, str(exc), "error")
    return go("/settings")


@app.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request):
    return render(request, "change_password.html", {"page_title": "Change password"})


@app.post("/change-password")
async def change_password_post(request: Request):
    form = await request.form()
    try:
        check_csrf(request, form); user = get_user(request)
        services.change_password(user["id"], str(form.get("current_password", "")), str(form.get("new_password", "")), DB_PATH)
        flash(request, "Password changed.")
    except Exception as exc: flash(request, str(exc), "error")
    return go("/change-password")


# Keep signed-session middleware outside the request middleware above so request.session
# is available to authentication and CSRF checks. This must be registered before startup.
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET,
    session_cookie="retailwizard_session",
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true" or bool(os.getenv("RENDER")),
    max_age=60 * 60 * 8,
)
