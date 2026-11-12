"""Explainable, offline retail insights built from the store's own SQLite data.

This module intentionally uses transparent business rules, not a remote LLM or
an unverifiable "AI prediction". It does not export personal/customer records.
"""
from __future__ import annotations

from datetime import date, timedelta, datetime
from typing import Any

from .services import list_products, list_low_stock, report_data, profit_loss


def analyze_business(db_path: str | None = None) -> dict[str, Any]:
    today = date.today()
    start = (today - timedelta(days=29)).isoformat()
    end = today.isoformat()
    products = list_products(db_path=db_path)
    low_stock = list_low_stock(db_path=db_path)
    sales = report_data("sales", start, end, db_path)
    best_sellers = report_data("best_sellers", start, end, db_path)
    pnl = profit_loss(start, end, db_path)

    gross_receipts = sum(float(row.get("total", 0) or 0) for row in sales)
    refund_value = sum(float(row.get("refunded_total", 0) or 0) for row in sales)
    refund_rate = (refund_value / gross_receipts * 100) if gross_receipts else 0.0
    sold_skus = {str(row.get("sku", "")).casefold(): float(row.get("units_sold", 0) or 0) for row in best_sellers}
    insights: list[dict[str, str]] = []

    out_of_stock = [p for p in products if float(p.get("stock_qty", 0) or 0) <= 0]
    if out_of_stock:
        names = ", ".join(str(p["name"]) for p in out_of_stock[:5])
        suffix = f" and {len(out_of_stock)-5} more" if len(out_of_stock) > 5 else ""
        insights.append({"priority": "High", "title": f"{len(out_of_stock)} product(s) are out of stock",
            "detail": f"No sellable units remain for: {names}{suffix}.",
            "action": "Create a purchase order or update stock counts after a physical count."})

    replenishment = [p for p in low_stock if float(p.get("stock_qty", 0) or 0) > 0]
    if replenishment:
        names = ", ".join(f"{p['name']} ({float(p['stock_qty']):g}/{float(p['reorder_level']):g})" for p in replenishment[:6])
        insights.append({"priority": "High" if len(replenishment) > 3 else "Medium",
            "title": f"{len(replenishment)} product(s) have reached their reorder point",
            "detail": f"Current quantity / reorder point: {names}.",
            "action": "Review supplier lead times and replenish these products before the next sales cycle."})

    loss_products = []
    for product in products:
        effective_price = float(product.get("price", 0) or 0) * (1 - float(product.get("discount_percent", 0) or 0) / 100)
        cost = float(product.get("cost_price", 0) or 0)
        if cost > 0 and effective_price < cost:
            loss_products.append(str(product["name"]))
    if loss_products:
        insights.append({"priority": "High", "title": f"{len(loss_products)} product(s) may sell below cost",
            "detail": "After the configured item discount, selling price is below purchase cost for: " + ", ".join(loss_products[:7]) + (" and more" if len(loss_products) > 7 else "") + ".",
            "action": "Check supplier costs, retail prices and discount settings; taxes are excluded from this comparison."})

    best_by_sku = {str(row.get("sku", "")).casefold(): row for row in best_sellers}
    slow = [p for p in products if float(p.get("stock_qty", 0) or 0) > 0 and str(p.get("sku", "")).casefold() not in best_by_sku]
    if slow and sales:
        insights.append({"priority": "Info", "title": f"{len(slow)} stocked product(s) had no recorded sales in 30 days",
            "detail": "Examples: " + ", ".join(str(p["name"]) for p in slow[:7]) + (" and more" if len(slow) > 7 else "") + ".",
            "action": "Review demand, placement and reorder quantities. Do not automatically discount without checking margin."})

    expiry_soon = []
    for product in products:
        raw = product.get("expiry_date")
        if not raw:
            continue
        try:
            expires = date.fromisoformat(str(raw))
        except ValueError:
            continue
        if today <= expires <= today + timedelta(days=30):
            expiry_soon.append((product, expires))
    if expiry_soon:
        examples = ", ".join(f"{p['name']} ({d.isoformat()})" for p, d in expiry_soon[:5])
        insights.append({"priority": "Medium", "title": f"{len(expiry_soon)} product(s) expire within 30 days",
            "detail": f"Upcoming expiry dates: {examples}.",
            "action": "Inspect batches, apply a store-approved clearance policy and remove expired stock from sale."})

    if refund_rate >= 10:
        insights.append({"priority": "High" if refund_rate >= 20 else "Medium",
            "title": f"Refund ratio is elevated ({refund_rate:.1f}%)",
            "detail": f"Recorded refunds are {refund_rate:.1f}% of gross receipts during the analysis window.",
            "action": "Review return reasons, product quality and cashier notes before changing the refund policy."})

    if pnl["gross_profit"] > 0 and pnl["operating_expenses"] > pnl["gross_profit"]:
        insights.append({"priority": "High", "title": "Operating expenses exceed gross profit",
            "detail": f"Gross profit is ₹{pnl['gross_profit']:,.2f}, while recorded operating expenses are ₹{pnl['operating_expenses']:,.2f}.",
            "action": "Review recurring expenses and pricing/margins. Treat this as a recorded-period signal, not a forecast."})
    elif pnl["net_profit"] < 0 and sales:
        insights.append({"priority": "Medium", "title": "Net profit is negative for the selected period",
            "detail": f"The recorded 30-day net result is ₹{pnl['net_profit']:,.2f}.",
            "action": "Check product margins, refunds, purchase costs and expenses for incomplete or unusual entries."})

    if not sales:
        insights.append({"priority": "Info", "title": "Not enough recent sales history yet",
            "detail": "No sales are recorded in the last 30 days, so demand and return-rate analysis is limited.",
            "action": "Record a few real or clearly labelled test transactions and run the analysis again."})

    # Estimate recommended stock based on a 14-day cover of observed units sold.
    restock_notes = []
    for product in products:
        row = best_by_sku.get(str(product.get("sku", "")).casefold())
        if not row:
            continue
        units = float(row.get("units_sold", 0) or 0)
        daily_rate = units / 30.0
        target = max(float(product.get("reorder_level", 0) or 0), daily_rate * 14)
        gap = max(0, target - float(product.get("stock_qty", 0) or 0))
        if gap >= 1 and units > 0:
            restock_notes.append((product["name"], gap, daily_rate))
    if restock_notes:
        restock_notes.sort(key=lambda x: x[1], reverse=True)
        examples = ", ".join(f"{name} (+{qty:.0f})" for name, qty, _ in restock_notes[:5])
        insights.append({"priority": "Medium", "title": "Demand-based stock cover estimate",
            "detail": "A simple 14-day cover estimate using the last 30 days of recorded sales suggests: " + examples + ".",
            "action": "Use these quantities as a planning starting point; adjust for supplier lead time, seasonality and upcoming promotions."})

    if not insights:
        insights.append({"priority": "Info", "title": "No rule-based risks detected",
            "detail": "The current inventory and last-30-day records did not trigger the checks in this analysis.",
            "action": "Continue recording accurate stock, sales, purchases and expenses. This is not a guarantee that the business has no risk."})

    priority_order = {"High": 0, "Medium": 1, "Info": 2}
    insights.sort(key=lambda item: priority_order.get(item["priority"], 3))
    metrics = {
        "net_sales": float(pnl["net_sales"]),
        "net_profit": float(pnl["net_profit"]),
        "gross_sales": float(pnl["gross_sales"]),
        "refunds": float(pnl["refunds"]),
        "gross_profit": float(pnl["gross_profit"]),
        "operating_expenses": float(pnl["operating_expenses"]),
        "low_stock_count": len(low_stock),
        "products_count": len(products),
        "transactions_count": len(sales),
        "refund_rate_percent": refund_rate,
    }
    return {"period_start": start, "period_end": end,
            "engine": "Explainable local business rules; no cloud AI/API calls",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "metrics": metrics, "insights": insights}
