from __future__ import annotations

import sqlite3
from contextlib import closing
import uuid
import math
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from .db import connect, transaction
from .security import hash_password, verify_password

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def as_float(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _audit(conn: sqlite3.Connection, user_id: int | None, action: str,
           entity_type: str | None = None, entity_id: int | None = None,
           details: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, entity_type, entity_id, details),
    )


def settings(db_path: str | Path | None = None) -> dict[str, str]:
    with closing(connect(db_path)) as conn:
        return {r["setting_key"]: r["setting_value"] for r in conn.execute("SELECT * FROM app_settings")}


def update_settings(values: dict[str, Any], user_id: int, db_path: str | Path | None = None) -> None:
    allowed = {"store_name", "store_address", "store_phone", "store_email", "low_stock_threshold",
               "default_tax_percent", "upi_vpa"}
    for key, value in values.items():
        if key not in allowed:
            raise ValueError(f"Unsupported setting: {key}")
        if key in {"low_stock_threshold", "default_tax_percent"}:
            number = float(value)
            if number < 0 or (key == "default_tax_percent" and number > 100):
                raise ValueError(f"Invalid value for {key}.")
    with transaction(db_path) as conn:
        conn.executemany(
            "INSERT INTO app_settings(setting_key, setting_value) VALUES (?, ?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
            [(k, str(v).strip()) for k, v in values.items()],
        )
        _audit(conn, user_id, "UPDATE_SETTINGS", "settings", None, ", ".join(values))


def create_user(full_name: str, username: str, password: str, role: str = "cashier",
                db_path: str | Path | None = None) -> int:
    full_name, username = full_name.strip(), username.strip()
    if not full_name or not username:
        raise ValueError("Full name and username are required.")
    if role not in {"admin", "cashier"}:
        raise ValueError("Role must be admin or cashier.")
    password_hash = hash_password(password)
    try:
        with transaction(db_path) as conn:
            cur = conn.execute(
                "INSERT INTO users(full_name, username, password_hash, role) VALUES (?, ?, ?, ?)",
                (full_name, username, password_hash, role),
            )
            _audit(conn, cur.lastrowid, "CREATE_USER", "user", cur.lastrowid, role)
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("That username is already in use.") from exc


def authenticate(username: str, password: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, full_name, username, password_hash, role, is_active FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "full_name": row["full_name"], "username": row["username"], "role": row["role"]}


def list_users(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        rows = conn.execute("SELECT id, full_name, username, role, is_active, created_at FROM users ORDER BY full_name").fetchall()
        return [dict(r) for r in rows]


def set_user_active(target_user_id: int, active: bool, actor_id: int, db_path: str | Path | None = None) -> None:
    if target_user_id == actor_id and not active:
        raise ValueError("You cannot deactivate your own account.")
    with transaction(db_path) as conn:
        row = conn.execute("SELECT role, is_active FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not row:
            raise ValueError("User not found.")
        if row["role"] == "admin" and not active:
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
            if admins <= 1:
                raise ValueError("At least one active administrator must remain.")
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(active), target_user_id))
        _audit(conn, actor_id, "ACTIVATE_USER" if active else "DEACTIVATE_USER", "user", target_user_id)


def change_password(user_id: int, current_password: str, new_password: str,
                    db_path: str | Path | None = None) -> None:
    with transaction(db_path) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            raise ValueError("Current password is incorrect.")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), user_id))
        _audit(conn, user_id, "CHANGE_PASSWORD", "user", user_id)


def create_product(data: dict[str, Any], actor_id: int, db_path: str | Path | None = None) -> int:
    sku = str(data.get("sku", "")).strip()
    name = str(data.get("name", "")).strip()
    if not sku or not name:
        raise ValueError("Product SKU and name are required.")
    price = money(data.get("price", 0))
    cost = money(data.get("cost_price", 0))
    discount = float(data.get("discount_percent", 0) or 0)
    tax = float(data.get("tax_percent", 0) or 0)
    stock = float(data.get("stock_qty", 0) or 0)
    reorder = float(data.get("reorder_level", 5) or 0)
    if not all(v.is_finite() for v in (price, cost)) or not all(math.isfinite(v) for v in (stock, reorder, discount, tax)):
        raise ValueError("Numeric product fields must be finite numbers.")
    expiry_date = data.get("expiry_date") or None
    if expiry_date:
        try: date.fromisoformat(str(expiry_date))
        except ValueError as exc: raise ValueError("Expiry date must use YYYY-MM-DD.") from exc
    if price < 0 or cost < 0 or stock < 0 or reorder < 0:
        raise ValueError("Price, cost, stock and reorder level cannot be negative.")
    if not 0 <= discount <= 100 or not 0 <= tax <= 100:
        raise ValueError("Discount and tax must be between 0 and 100.")
    try:
        with transaction(db_path) as conn:
            cur = conn.execute("""
                INSERT INTO products(sku, barcode, name, category, brand, unit, price, cost_price,
                                     discount_percent, tax_percent, stock_qty, reorder_level, expiry_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sku, data.get("barcode") or None, name, data.get("category") or "General",
                  data.get("brand") or "", data.get("unit") or "pcs", as_float(price), as_float(cost),
                  discount, tax, stock, reorder, expiry_date))
            if stock:
                conn.execute("INSERT INTO stock_movements(product_id, movement_type, quantity, note, created_by) VALUES (?, 'OPENING', ?, 'Opening stock', ?)",
                             (cur.lastrowid, stock, actor_id))
            _audit(conn, actor_id, "CREATE_PRODUCT", "product", cur.lastrowid, sku)
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("A product with this SKU already exists, or one of the values is invalid.") from exc


def update_product(product_id: int, data: dict[str, Any], actor_id: int,
                   db_path: str | Path | None = None) -> None:
    sku, name = str(data.get("sku", "")).strip(), str(data.get("name", "")).strip()
    if not sku or not name:
        raise ValueError("Product SKU and name are required.")
    numbers = {k: float(data.get(k, 0) or 0) for k in ("price", "cost_price", "discount_percent", "tax_percent", "reorder_level")}
    if not all(math.isfinite(v) for v in numbers.values()):
        raise ValueError("Numeric product fields must be finite numbers.")
    expiry_date = data.get("expiry_date") or None
    if expiry_date:
        try: date.fromisoformat(str(expiry_date))
        except ValueError as exc: raise ValueError("Expiry date must use YYYY-MM-DD.") from exc
    if any(numbers[k] < 0 for k in ("price", "cost_price", "reorder_level")):
        raise ValueError("Price, cost and reorder level cannot be negative.")
    if not 0 <= numbers["discount_percent"] <= 100 or not 0 <= numbers["tax_percent"] <= 100:
        raise ValueError("Discount and tax must be between 0 and 100.")
    try:
        with transaction(db_path) as conn:
            conn.execute("""UPDATE products SET sku=?, barcode=?, name=?, category=?, brand=?, unit=?, price=?,
                cost_price=?, discount_percent=?, tax_percent=?, reorder_level=?, expiry_date=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (sku, data.get("barcode") or None, name, data.get("category") or "General", data.get("brand") or "",
                 data.get("unit") or "pcs", numbers["price"], numbers["cost_price"], numbers["discount_percent"],
                 numbers["tax_percent"], numbers["reorder_level"], expiry_date, product_id))
            if conn.total_changes == 0:
                raise ValueError("Product not found.")
            _audit(conn, actor_id, "UPDATE_PRODUCT", "product", product_id, sku)
    except sqlite3.IntegrityError as exc:
        raise ValueError("A product with this SKU already exists.") from exc


def delete_product(product_id: int, actor_id: int, db_path: str | Path | None = None) -> None:
    with transaction(db_path) as conn:
        try:
            conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        except sqlite3.IntegrityError as exc:
            raise ValueError("This product has transaction history and cannot be deleted. Deactivate it instead.") from exc
        _audit(conn, actor_id, "DELETE_PRODUCT", "product", product_id)


def deactivate_product(product_id: int, actor_id: int, db_path: str | Path | None = None) -> None:
    with transaction(db_path) as conn:
        cur = conn.execute("UPDATE products SET is_active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?", (product_id,))
        if cur.rowcount == 0:
            raise ValueError("Product not found.")
        _audit(conn, actor_id, "DEACTIVATE_PRODUCT", "product", product_id)


def list_products(search: str = "", include_inactive: bool = False,
                  db_path: str | Path | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM products WHERE 1=1"
    params: list[Any] = []
    if not include_inactive:
        query += " AND is_active=1"
    if search.strip():
        term = f"%{search.strip()}%"
        query += " AND (sku LIKE ? OR barcode LIKE ? OR name LIKE ? OR category LIKE ? OR brand LIKE ?)"
        params.extend([term] * 5)
    query += " ORDER BY name COLLATE NOCASE"
    with closing(connect(db_path)) as conn:
        return [dict(r) for r in conn.execute(query, params)]


def adjust_stock(product_id: int, quantity_delta: float, reason: str, actor_id: int,
                 db_path: str | Path | None = None) -> None:
    delta = float(quantity_delta)
    if delta == 0:
        raise ValueError("Adjustment quantity cannot be zero.")
    with transaction(db_path) as conn:
        row = conn.execute("SELECT stock_qty FROM products WHERE id=? AND is_active=1", (product_id,)).fetchone()
        if not row:
            raise ValueError("Product not found or inactive.")
        new_stock = float(row["stock_qty"]) + delta
        if new_stock < 0:
            raise ValueError("Stock adjustment would make stock negative.")
        conn.execute("UPDATE products SET stock_qty=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_stock, product_id))
        conn.execute("INSERT INTO stock_movements(product_id, movement_type, quantity, note, created_by) VALUES (?, 'ADJUSTMENT', ?, ?, ?)",
                     (product_id, delta, reason.strip() or "Manual adjustment", actor_id))
        _audit(conn, actor_id, "ADJUST_STOCK", "product", product_id, f"{delta:+g}: {reason}")


def _upsert_customer(conn: sqlite3.Connection, name: str, phone: str | None) -> int | None:
    if not name.strip() and not (phone or "").strip():
        return None
    customer_name = name.strip() or "Walk-in Customer"
    phone_value = (phone or "").strip() or None
    if phone_value:
        found = conn.execute("SELECT id FROM customers WHERE phone=?", (phone_value,)).fetchone()
        if found:
            conn.execute("UPDATE customers SET name=? WHERE id=?", (customer_name, found["id"]))
            return int(found["id"])
    cur = conn.execute("INSERT INTO customers(name, phone) VALUES (?, ?)", (customer_name, phone_value))
    return int(cur.lastrowid)


def create_sale(items: Iterable[dict[str, Any]], customer_name: str, customer_phone: str,
                cashier_id: int, payment_method: str, amount_tendered: Any = 0,
                payment_reference: str = "", order_discount_percent: float = 0,
                upi_confirmed: bool = False, notes: str = "",
                db_path: str | Path | None = None) -> dict[str, Any]:
    cart = list(items)
    if not cart:
        raise ValueError("Add at least one product to the cart.")
    if payment_method not in {"Cash", "UPI"}:
        raise ValueError("Choose Cash or UPI as the payment method.")
    order_discount_percent = float(order_discount_percent or 0)
    if not 0 <= order_discount_percent <= 100:
        raise ValueError("Order discount must be between 0 and 100 percent.")

    # Merge repeated product IDs before validating stock so a duplicated cart line
    # cannot oversell the same product within one checkout.
    aggregated: dict[int, Decimal] = {}
    for entry in cart:
        product_id = int(entry["product_id"])
        qty = Decimal(str(entry.get("quantity", 0)))
        if not qty.is_finite() or qty <= 0:
            raise ValueError("Each cart quantity must be a positive finite number.")
        aggregated[product_id] = aggregated.get(product_id, Decimal("0")) + qty

    with transaction(db_path) as conn:
        customer_id = _upsert_customer(conn, customer_name, customer_phone)
        prepared: list[dict[str, Any]] = []
        pre_order_total = Decimal("0.00")
        for product_id, qty in aggregated.items():
            if qty <= 0:
                raise ValueError("Each cart quantity must be greater than zero.")
            product = conn.execute("SELECT * FROM products WHERE id=? AND is_active=1", (product_id,)).fetchone()
            if not product:
                raise ValueError(f"Product #{product_id} is unavailable.")
            if qty > Decimal(str(product["stock_qty"])):
                raise ValueError(f"Insufficient stock for {product['name']}. Available: {product['stock_qty']:g}.")
            unit_price = money(product["price"])
            gross = money(unit_price * qty)
            item_discount_pct = Decimal(str(product["discount_percent"] or 0))
            item_discount = money(gross * item_discount_pct / Decimal("100"))
            discounted = gross - item_discount
            tax_pct = Decimal(str(product["tax_percent"] or 0))
            pre_order_total += discounted
            prepared.append({
                "product": product, "product_id": product_id, "qty": qty,
                "unit_price": unit_price, "unit_cost": money(product["cost_price"]),
                "gross": gross, "item_discount": item_discount, "discounted": discounted,
                "tax_pct": tax_pct,
            })

        order_discount_total = money(pre_order_total * Decimal(str(order_discount_percent)) / Decimal("100"))
        subtotal = money(sum((r["gross"] for r in prepared), Decimal("0.00")))
        item_discount_total = money(sum((r["item_discount"] for r in prepared), Decimal("0.00")))
        tax_total = Decimal("0.00")
        total_before_round = Decimal("0.00")
        computed_lines = []
        discount_remaining = order_discount_total
        for index, row in enumerate(prepared):
            if not pre_order_total or not order_discount_total:
                allocated_order_discount = Decimal("0.00")
            elif index == len(prepared) - 1:
                allocated_order_discount = discount_remaining
            else:
                allocated_order_discount = min(
                    money(order_discount_total * row["discounted"] / pre_order_total),
                    row["discounted"],
                )
                discount_remaining = money(discount_remaining - allocated_order_discount)
            discount = money(row["item_discount"] + allocated_order_discount)
            taxable = money(row["gross"] - discount)
            tax_amount = money(taxable * row["tax_pct"] / Decimal("100"))
            line_total = money(taxable + tax_amount)
            tax_total += tax_amount
            total_before_round += line_total
            computed_lines.append({**row, "discount": discount, "tax": tax_amount, "line_total": line_total})

        discount_total = money(item_discount_total + order_discount_total)
        total = money(total_before_round)
        if payment_method == "Cash":
            tendered = money(amount_tendered)
            if tendered < total:
                raise ValueError(f"Cash received is below the amount due (₹{total:.2f}).")
            change_due = money(tendered - total)
            reference = None
        else:
            if not upi_confirmed:
                raise ValueError("UPI payment must be manually confirmed after checking the payment in your UPI app.")
            reference = payment_reference.strip()
            if not reference:
                raise ValueError("Enter the UPI transaction/reference ID for reconciliation.")
            tendered = total
            change_due = Decimal("0.00")

        invoice_no = f"RW-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        cur = conn.execute("""INSERT INTO sales(invoice_no, customer_id, cashier_id, subtotal, discount_total,
            tax_total, total, payment_method, amount_tendered, change_due, payment_reference, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (invoice_no, customer_id, cashier_id, as_float(subtotal), as_float(discount_total),
             as_float(money(tax_total)), as_float(total), payment_method, as_float(tendered),
             as_float(change_due), reference, notes.strip() or None))
        sale_id = int(cur.lastrowid)
        for row in computed_lines:
            product = row["product"]
            cur_item = conn.execute("""INSERT INTO sale_items(sale_id, product_id, sku, product_name,
                quantity, unit_price, unit_cost, discount_percent, tax_percent, gross_amount,
                discount_amount, tax_amount, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sale_id, row["product_id"], product["sku"], product["name"], float(row["qty"]),
                 as_float(row["unit_price"]), as_float(row["unit_cost"]), float(product["discount_percent"]),
                 float(row["tax_pct"]), as_float(row["gross"]), as_float(row["discount"]),
                 as_float(row["tax"]), as_float(row["line_total"])))
            conn.execute("UPDATE products SET stock_qty=stock_qty-?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (float(row["qty"]), row["product_id"]))
            conn.execute("INSERT INTO stock_movements(product_id, movement_type, quantity, reference_type, reference_id, note, created_by) VALUES (?, 'SALE', ?, 'sale', ?, ?, ?)",
                         (row["product_id"], -float(row["qty"]), sale_id, invoice_no, cashier_id))
        conn.execute("INSERT INTO payments(sale_id, method, amount, reference, status) VALUES (?, ?, ?, ?, 'RECORDED')",
                     (sale_id, payment_method, as_float(total), reference))
        _audit(conn, cashier_id, "CREATE_SALE", "sale", sale_id, invoice_no)
        return {"id": sale_id, "invoice_no": invoice_no, "subtotal": as_float(subtotal),
                "discount_total": as_float(discount_total), "tax_total": as_float(money(tax_total)),
                "total": as_float(total), "payment_method": payment_method,
                "amount_tendered": as_float(tendered), "change_due": as_float(change_due)}


def list_sales(search: str = "", limit: int = 500, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    sql = """SELECT s.*, COALESCE(c.name, 'Walk-in Customer') customer_name, c.phone customer_phone,
             u.full_name cashier_name FROM sales s LEFT JOIN customers c ON c.id=s.customer_id
             JOIN users u ON u.id=s.cashier_id WHERE 1=1"""
    params: list[Any] = []
    if search.strip():
        term = f"%{search.strip()}%"
        sql += " AND (s.invoice_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ?)"
        params.extend([term, term, term])
    sql += " ORDER BY s.sold_at DESC LIMIT ?"
    params.append(limit)
    with closing(connect(db_path)) as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def sale_detail(sale_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        sale = conn.execute("""SELECT s.*, COALESCE(c.name, 'Walk-in Customer') customer_name,
            c.phone customer_phone, u.full_name cashier_name FROM sales s
            LEFT JOIN customers c ON c.id=s.customer_id JOIN users u ON u.id=s.cashier_id WHERE s.id=?""",
            (sale_id,)).fetchone()
        if not sale:
            return None
        data = dict(sale)
        data["items"] = [dict(r) for r in conn.execute("SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,))]
        data["refunds"] = [dict(r) for r in conn.execute("SELECT * FROM refunds WHERE sale_id=? ORDER BY created_at", (sale_id,))]
        return data


def refund_sale(sale_id: int, quantities: dict[int, float], reason: str, actor_id: int,
                payment_method: str = "Original method", restock: bool = True,
                db_path: str | Path | None = None) -> dict[str, Any]:
    if not quantities:
        raise ValueError("Select at least one item quantity to refund.")
    if payment_method not in {"Original method", "Cash", "UPI"}:
        raise ValueError("Invalid refund method.")
    with transaction(db_path) as conn:
        sale = conn.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale or sale["status"] == "REFUNDED":
            raise ValueError("Sale was not found or has already been fully refunded.")
        refund_amount = Decimal("0.00")
        selected: list[tuple[sqlite3.Row, Decimal, Decimal, Decimal]] = []
        for item_id, raw_qty in quantities.items():
            qty = Decimal(str(raw_qty))
            item = conn.execute("SELECT * FROM sale_items WHERE id=? AND sale_id=?", (item_id, sale_id)).fetchone()
            if not item or qty <= 0:
                raise ValueError("Refund item or quantity is invalid.")
            available = Decimal(str(item["quantity"])) - Decimal(str(item["refunded_qty"]))
            if qty > available:
                raise ValueError(f"Refund quantity exceeds the remaining quantity for {item['product_name']}.")
            amount = money(Decimal(str(item["line_total"])) * qty / Decimal(str(item["quantity"])))
            tax_amount = money(Decimal(str(item["tax_amount"])) * qty / Decimal(str(item["quantity"])))
            refund_amount += amount
            selected.append((item, qty, amount, tax_amount))
        refund_amount = money(refund_amount)
        already_refunded = money(sale["refunded_total"])
        if refund_amount <= 0 or already_refunded + refund_amount > money(sale["total"]):
            raise ValueError("Refund amount is invalid or exceeds the amount paid.")
        refund_no = f"RF-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        refund_tax_total = money(sum((tax for _, _, _, tax in selected), Decimal("0.00")))
        cur = conn.execute("INSERT INTO refunds(refund_no, sale_id, amount, tax_amount, payment_method, reason, restocked, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (refund_no, sale_id, as_float(refund_amount), as_float(refund_tax_total), payment_method, reason.strip(), int(restock), actor_id))
        refund_id = int(cur.lastrowid)
        for item, qty, amount, tax_amount in selected:
            conn.execute("UPDATE sale_items SET refunded_qty=refunded_qty+? WHERE id=?", (float(qty), item["id"]))
            conn.execute("INSERT INTO refund_items(refund_id, sale_item_id, product_id, quantity, amount, tax_amount) VALUES (?, ?, ?, ?, ?, ?)",
                         (refund_id, item["id"], item["product_id"], float(qty), as_float(amount), as_float(tax_amount)))
            if restock and item["product_id"] is not None:
                conn.execute("UPDATE products SET stock_qty=stock_qty+?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                             (float(qty), item["product_id"]))
                conn.execute("INSERT INTO stock_movements(product_id, movement_type, quantity, reference_type, reference_id, note, created_by) VALUES (?, 'RETURN', ?, 'refund', ?, ?, ?)",
                             (item["product_id"], float(qty), refund_id, refund_no, actor_id))
        new_refunded = money(already_refunded + refund_amount)
        status = "REFUNDED" if new_refunded >= money(sale["total"]) else "PARTIALLY_REFUNDED"
        conn.execute("UPDATE sales SET refunded_total=?, status=? WHERE id=?",
                     (as_float(new_refunded), status, sale_id))
        _audit(conn, actor_id, "REFUND_SALE", "sale", sale_id, f"{refund_no}: {as_float(refund_amount):.2f}")
        return {"id": refund_id, "refund_no": refund_no, "amount": as_float(refund_amount), "status": status}


def create_purchase(supplier_name: str, items: Iterable[dict[str, Any]], actor_id: int,
                    notes: str = "", db_path: str | Path | None = None) -> dict[str, Any]:
    cart = list(items)
    if not supplier_name.strip() or not cart:
        raise ValueError("Supplier name and at least one purchase item are required.")
    with transaction(db_path) as conn:
        existing = conn.execute("SELECT id FROM suppliers WHERE name=? COLLATE NOCASE", (supplier_name.strip(),)).fetchone()
        if existing:
            supplier_id = int(existing["id"])
        else:
            supplier_id = int(conn.execute("INSERT INTO suppliers(name) VALUES (?)", (supplier_name.strip(),)).lastrowid)
        prepared = []
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        for item in cart:
            product_id = int(item["product_id"])
            qty = Decimal(str(item.get("quantity", 0)))
            unit_cost = money(item.get("unit_cost", 0))
            tax_pct = Decimal(str(item.get("tax_percent", 0) or 0))
            if qty <= 0 or unit_cost < 0 or not 0 <= tax_pct <= 100:
                raise ValueError("Purchase quantity, cost or tax is invalid.")
            product = conn.execute("SELECT id, sku, name FROM products WHERE id=? AND is_active=1", (product_id,)).fetchone()
            if not product:
                raise ValueError("A selected purchase product is unavailable.")
            net = money(qty * unit_cost)
            tax = money(net * tax_pct / Decimal("100"))
            subtotal += net
            tax_total += tax
            prepared.append((product, qty, unit_cost, tax_pct, net, tax))
        subtotal, tax_total = money(subtotal), money(tax_total)
        total = money(subtotal + tax_total)
        purchase_no = f"PO-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        purchase_id = int(conn.execute("INSERT INTO purchases(purchase_no, supplier_id, subtotal, tax_total, total, notes, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                       (purchase_no, supplier_id, as_float(subtotal), as_float(tax_total), as_float(total), notes.strip(), actor_id)).lastrowid)
        for product, qty, unit_cost, tax_pct, net, tax in prepared:
            conn.execute("INSERT INTO purchase_items(purchase_id, product_id, quantity, unit_cost, tax_percent, line_total) VALUES (?, ?, ?, ?, ?, ?)",
                         (purchase_id, product["id"], float(qty), as_float(unit_cost), float(tax_pct), as_float(net + tax)))
            conn.execute("UPDATE products SET stock_qty=stock_qty+?, cost_price=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (float(qty), as_float(unit_cost), product["id"]))
            conn.execute("INSERT INTO stock_movements(product_id, movement_type, quantity, reference_type, reference_id, note, created_by) VALUES (?, 'PURCHASE', ?, 'purchase', ?, ?, ?)",
                         (product["id"], float(qty), purchase_id, purchase_no, actor_id))
        _audit(conn, actor_id, "CREATE_PURCHASE", "purchase", purchase_id, purchase_no)
        return {"id": purchase_id, "purchase_no": purchase_no, "subtotal": as_float(subtotal),
                "tax_total": as_float(tax_total), "total": as_float(total)}


def list_purchases(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        return [dict(r) for r in conn.execute("""SELECT p.*, s.name supplier_name, u.full_name created_by_name
            FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id JOIN users u ON u.id=p.created_by
            ORDER BY p.purchased_at DESC""")]


def add_expense(category: str, description: str, amount: Any, expense_date: str,
                actor_id: int, db_path: str | Path | None = None) -> int:
    value = money(amount)
    if not category.strip() or not description.strip() or value <= 0:
        raise ValueError("Expense category, description and a positive amount are required.")
    try:
        date.fromisoformat(expense_date)
    except ValueError as exc:
        raise ValueError("Expense date must use YYYY-MM-DD.") from exc
    with transaction(db_path) as conn:
        cur = conn.execute("INSERT INTO expenses(category, description, amount, expense_date, created_by) VALUES (?, ?, ?, ?, ?)",
                           (category.strip(), description.strip(), as_float(value), expense_date, actor_id))
        _audit(conn, actor_id, "ADD_EXPENSE", "expense", cur.lastrowid, description)
        return int(cur.lastrowid)


def list_expenses(start_date: str | None = None, end_date: str | None = None,
                  db_path: str | Path | None = None) -> list[dict[str, Any]]:
    sql = "SELECT e.*, u.full_name created_by_name FROM expenses e JOIN users u ON u.id=e.created_by WHERE 1=1"
    params: list[Any] = []
    if start_date:
        sql += " AND expense_date>=?"; params.append(start_date)
    if end_date:
        sql += " AND expense_date<=?"; params.append(end_date)
    sql += " ORDER BY expense_date DESC, e.id DESC"
    with closing(connect(db_path)) as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def list_low_stock(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM products WHERE is_active=1 AND stock_qty<=reorder_level ORDER BY stock_qty, name")]


def dashboard_metrics(db_path: str | Path | None = None) -> dict[str, Any]:
    """Return dashboard KPIs using the computer's local calendar day/month.

    Sales timestamps are written by SQLite CURRENT_TIMESTAMP in UTC. Applying
    SQLite's localtime modifier before extracting the date prevents sales close
    to midnight UTC from being assigned to the wrong local business day.
    """
    with closing(connect(db_path)) as conn:
        sales_today = conn.execute(
            """SELECT COALESCE(SUM(total - refunded_total), 0)
               FROM sales WHERE date(sold_at, 'localtime') = date('now', 'localtime')"""
        ).fetchone()[0]
        tx_today = conn.execute(
            """SELECT COUNT(*) FROM sales
               WHERE date(sold_at, 'localtime') = date('now', 'localtime')"""
        ).fetchone()[0]
        stock_count = conn.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0]
        low_stock_count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE is_active=1 AND stock_qty<=reorder_level"
        ).fetchone()[0]
        month_sales = conn.execute(
            """SELECT COALESCE(SUM(total - refunded_total), 0) FROM sales
               WHERE strftime('%Y-%m', sold_at, 'localtime') = strftime('%Y-%m', 'now', 'localtime')"""
        ).fetchone()[0]
        return {
            "sales_today": float(sales_today),
            "transactions_today": int(tx_today),
            "products": int(stock_count),
            "low_stock": int(low_stock_count),
            "month_sales": float(month_sales),
        }


def report_data(report_type: str, start_date: str | None = None, end_date: str | None = None,
                db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        if report_type == "sales":
            sql = """SELECT date(s.sold_at, 'localtime') date, s.invoice_no, COALESCE(c.name,'Walk-in Customer') customer,
                s.payment_method, s.subtotal, s.discount_total, s.tax_total, s.total, s.refunded_total,
                s.total-s.refunded_total net_total, s.status FROM sales s LEFT JOIN customers c ON c.id=s.customer_id WHERE 1=1"""
            params: list[Any] = []
            if start_date: sql += " AND date(s.sold_at, 'localtime')>=?"; params.append(start_date)
            if end_date: sql += " AND date(s.sold_at, 'localtime')<=?"; params.append(end_date)
            sql += " ORDER BY s.sold_at DESC"
            return [dict(r) for r in conn.execute(sql, params)]
        if report_type == "stock":
            return [dict(r) for r in conn.execute("""SELECT sku, name, category, stock_qty, reorder_level,
                price, cost_price, CASE WHEN stock_qty<=reorder_level THEN 'LOW' ELSE 'OK' END stock_status
                FROM products WHERE is_active=1 ORDER BY stock_qty, name""")]
        if report_type == "best_sellers":
            sql = """SELECT si.sku, si.product_name, SUM(si.quantity-si.refunded_qty) units_sold,
                SUM((si.line_total-si.tax_amount) * (si.quantity-si.refunded_qty) / si.quantity) net_revenue
                FROM sale_items si JOIN sales s ON s.id=si.sale_id WHERE 1=1"""
            params = []
            if start_date: sql += " AND date(s.sold_at, 'localtime')>=?"; params.append(start_date)
            if end_date: sql += " AND date(s.sold_at, 'localtime')<=?"; params.append(end_date)
            sql += " GROUP BY si.product_id, si.sku, si.product_name ORDER BY units_sold DESC"
            return [dict(r) for r in conn.execute(sql, params)]
        if report_type == "transactions":
            sql = """SELECT s.invoice_no, s.sold_at, COALESCE(c.name,'Walk-in Customer') customer,
                c.phone, u.full_name cashier, s.payment_method, s.payment_reference, s.total,
                s.refunded_total, s.status FROM sales s LEFT JOIN customers c ON c.id=s.customer_id
                JOIN users u ON u.id=s.cashier_id WHERE 1=1"""
            params = []
            if start_date: sql += " AND date(s.sold_at, 'localtime')>=?"; params.append(start_date)
            if end_date: sql += " AND date(s.sold_at, 'localtime')<=?"; params.append(end_date)
            sql += " ORDER BY s.sold_at DESC"
            return [dict(r) for r in conn.execute(sql, params)]
        if report_type == "purchases":
            sql = """SELECT p.purchase_no, p.purchased_at, s.name supplier, p.subtotal, p.tax_total, p.total
                FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1"""
            params = []
            if start_date: sql += " AND date(p.purchased_at, 'localtime')>=?"; params.append(start_date)
            if end_date: sql += " AND date(p.purchased_at, 'localtime')<=?"; params.append(end_date)
            sql += " ORDER BY p.purchased_at DESC"
            return [dict(r) for r in conn.execute(sql, params)]
        raise ValueError("Unknown report type.")


def profit_loss(start_date: str | None = None, end_date: str | None = None,
                db_path: str | Path | None = None) -> dict[str, float]:
    with closing(connect(db_path)) as conn:
        sales_sql = "SELECT COALESCE(SUM(total-tax_total),0) FROM sales WHERE 1=1"
        sales_params: list[Any] = []
        if start_date: sales_sql += " AND date(sold_at, 'localtime')>=?"; sales_params.append(start_date)
        if end_date: sales_sql += " AND date(sold_at, 'localtime')<=?"; sales_params.append(end_date)
        gross_sales = conn.execute(sales_sql, sales_params).fetchone()[0]

        refund_sql = "SELECT COALESCE(SUM(amount-tax_amount),0) FROM refunds WHERE 1=1"
        refund_params: list[Any] = []
        if start_date: refund_sql += " AND date(created_at, 'localtime')>=?"; refund_params.append(start_date)
        if end_date: refund_sql += " AND date(created_at, 'localtime')<=?"; refund_params.append(end_date)
        refunds = conn.execute(refund_sql, refund_params).fetchone()[0]

        cogs_sql = """SELECT COALESCE(SUM(si.unit_cost * si.quantity),0)
            FROM sale_items si JOIN sales s ON s.id=si.sale_id WHERE 1=1"""
        cogs_params: list[Any] = []
        if start_date: cogs_sql += " AND date(s.sold_at, 'localtime')>=?"; cogs_params.append(start_date)
        if end_date: cogs_sql += " AND date(s.sold_at, 'localtime')<=?"; cogs_params.append(end_date)
        cogs_sold = conn.execute(cogs_sql, cogs_params).fetchone()[0]
        return_sql = """SELECT COALESCE(SUM(si.unit_cost * ri.quantity),0)
            FROM refund_items ri JOIN refunds r ON r.id=ri.refund_id
            JOIN sale_items si ON si.id=ri.sale_item_id WHERE r.restocked=1"""
        return_params: list[Any] = []
        if start_date: return_sql += " AND date(r.created_at, 'localtime')>=?"; return_params.append(start_date)
        if end_date: return_sql += " AND date(r.created_at, 'localtime')<=?"; return_params.append(end_date)
        cogs_returned = conn.execute(return_sql, return_params).fetchone()[0]
        cogs = float(cogs_sold) - float(cogs_returned)
        expense_sql = "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE 1=1"
        expense_params: list[Any] = []
        if start_date: expense_sql += " AND expense_date>=?"; expense_params.append(start_date)
        if end_date: expense_sql += " AND expense_date<=?"; expense_params.append(end_date)
        expenses = conn.execute(expense_sql, expense_params).fetchone()[0]
        net_sales = float(gross_sales) - float(refunds)
        gross_profit = net_sales - float(cogs)
        net_profit = gross_profit - float(expenses)
        return {"gross_sales": float(gross_sales), "refunds": float(refunds), "net_sales": net_sales,
                "cost_of_goods_sold": float(cogs), "gross_profit": gross_profit,
                "operating_expenses": float(expenses), "net_profit": net_profit}
