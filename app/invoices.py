from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Any


def _format_local_sold_at(value: Any) -> str:
    """Convert SQLite's naive UTC timestamp to the computer's local time."""
    raw = str(value or "-").strip()
    if not raw or raw == "-":
        return "-"
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%d %b %Y, %I:%M:%S %p")
    except (TypeError, ValueError, OverflowError):
        return raw


def generate_invoice_pdf(sale: dict[str, Any], destination: str | Path,
                         store_settings: dict[str, str] | None = None) -> Path:
    """Generate a printable invoice PDF. Requires the fpdf2 package."""
    try:
        from fpdf import FPDF, XPos, YPos
    except ImportError as exc:
        raise RuntimeError("Invoice PDF export requires fpdf2. Install requirements.txt.") from exc

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    prefs = store_settings or {}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(14, 14, 14)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 11, (prefs.get("store_name") or "Retail Wizard Store")[:60], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", size=9)
    for detail in (prefs.get("store_address", ""), prefs.get("store_phone", ""), prefs.get("store_email", "")):
        if detail:
            pdf.cell(0, 5, str(detail)[:100], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, "TAX INVOICE / RECEIPT", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(95, 7, f"Invoice: {sale['invoice_no']}")
    pdf.cell(0, 7, f"Date: {_format_local_sold_at(sale.get('sold_at'))}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(95, 7, f"Customer: {sale.get('customer_name') or 'Walk-in Customer'}")
    pdf.cell(0, 7, f"Phone: {sale.get('customer_phone') or '-'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, f"Cashier: {sale.get('cashier_name', '-')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    widths = [72, 20, 26, 24, 34]
    headers = ["Product", "Qty", "Unit Price", "Discount", "Line Total"]
    pdf.set_font("Helvetica", "B", 9)
    for width, title in zip(widths, headers):
        pdf.cell(width, 8, title, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    for item in sale.get("items", []):
        name = str(item["product_name"]).encode("latin-1", "replace").decode("latin-1")[:38]
        values = [name, f"{item['quantity']:g}", f"Rs. {item['unit_price']:.2f}",
                  f"Rs. {item['discount_amount']:.2f}", f"Rs. {item['line_total']:.2f}"]
        for width, value in zip(widths, values):
            pdf.cell(width, 8, value, border=1, align="L" if width == widths[0] else "R")
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Helvetica", size=10)
    totals = [
        ("Subtotal", sale["subtotal"]),
        ("Discount", sale["discount_total"]),
        ("Tax", sale["tax_total"]),
        ("Grand Total", sale["total"]),
    ]
    for label, amount in totals:
        pdf.cell(130, 7, label, align="R")
        pdf.cell(0, 7, f"Rs. {amount:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.ln(2)
    pdf.cell(130, 7, f"Payment: {sale['payment_method']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if sale.get("payment_reference"):
        pdf.cell(0, 7, f"UPI reference: {sale['payment_reference']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if sale.get("payment_method") == "Cash":
        pdf.cell(130, 7, f"Cash received: Rs. {sale['amount_tendered']:.2f}")
        pdf.cell(0, 7, f"Change: Rs. {sale['change_due']:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 7, "Thank you for shopping with us!", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.output(str(target))
    return target
