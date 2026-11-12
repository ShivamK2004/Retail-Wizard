from app.db import backup_database
from app.services import (
    add_expense, create_product, create_purchase, create_sale, create_user,
    dashboard_metrics, list_products, profit_loss, report_data,
)


def test_purchase_updates_stock_cost_and_supplier_history(db_path):
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    product_id = create_product({"sku": "MILK", "name": "Milk", "price": 60, "cost_price": 40,
                                 "stock_qty": 5, "reorder_level": 1}, owner, db_path)
    purchase = create_purchase("Fresh Supplier", [{"product_id": product_id, "quantity": 10, "unit_cost": 42}], owner, db_path=db_path)
    product = list_products(db_path=db_path)[0]
    assert product["stock_qty"] == 15
    assert product["cost_price"] == 42
    assert purchase["total"] == 420


def test_profit_loss_and_reports_use_recorded_costs_and_expenses(db_path):
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    product_id = create_product({"sku": "SOAP", "name": "Soap", "price": 100, "cost_price": 40,
                                 "stock_qty": 8, "reorder_level": 1}, owner, db_path)
    create_sale([{"product_id": product_id, "quantity": 2}], "Buyer", "123", owner, "Cash", 250, db_path=db_path)
    add_expense("Rent", "November rent", 30, "2026-11-12", owner, db_path)
    result = profit_loss(db_path=db_path)
    assert result["gross_sales"] == 200
    assert result["cost_of_goods_sold"] == 80
    assert result["operating_expenses"] == 30
    assert result["net_profit"] == 90
    assert len(report_data("sales", db_path=db_path)) == 1
    assert dashboard_metrics(db_path)["products"] == 1


def test_database_backup_is_restorable(db_path, tmp_path):
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    create_product({"sku": "TEA", "name": "Tea", "price": 10, "stock_qty": 4}, owner, db_path)
    backup = backup_database(tmp_path / "backup.db", db_path)
    import sqlite3
    conn = sqlite3.connect(backup)
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    conn.close()


def test_refunds_remove_tax_from_revenue_and_restocked_returns_restore_cogs(db_path):
    from app.services import refund_sale, sale_detail
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    product_id = create_product({"sku": "BOOK", "name": "Book", "price": 100, "cost_price": 40,
                                 "tax_percent": 10, "stock_qty": 3, "reorder_level": 0}, owner, db_path)
    sale = create_sale([{"product_id": product_id, "quantity": 1}], "Buyer", "555", owner, "Cash", 110, db_path=db_path)
    item_id = sale_detail(sale["id"], db_path)["items"][0]["id"]
    refund_sale(sale["id"], {item_id: 1}, "Full return", owner, restock=True, db_path=db_path)
    result = profit_loss(db_path=db_path)
    assert result["gross_sales"] == 100  # Sales-tax component is excluded from revenue.
    assert result["refunds"] == 100
    assert result["net_sales"] == 0
    assert result["cost_of_goods_sold"] == 0  # Restocked goods are credited back into inventory.
    assert result["net_profit"] == 0
