from app.insights import analyze_business
from app.services import create_product, create_sale, create_user, add_expense


def test_ai_insights_report_stock_risk_and_loss_margins(db_path):
    admin = create_user("Admin", "insightadmin", "SecurePass123", "admin", db_path)
    create_product({
        "sku": "LOW-001", "name": "Low Stock Item", "price": 10,
        "cost_price": 12, "discount_percent": 20, "tax_percent": 0,
        "stock_qty": 1, "reorder_level": 3,
    }, admin, db_path)
    result = analyze_business(str(db_path))
    assert result["metrics"]["products_count"] == 1
    assert result["metrics"]["low_stock_count"] == 1
    assert any("reorder point" in item["title"] for item in result["insights"])
    assert any("below cost" in item["title"] for item in result["insights"])
    assert result["engine"].startswith("Explainable local")


def test_ai_insights_calculate_recent_sales_and_expenses(db_path):
    admin = create_user("Admin", "insightadmin2", "SecurePass123", "admin", db_path)
    product = create_product({
        "sku": "RICE-001", "name": "Rice", "price": 100,
        "cost_price": 60, "discount_percent": 0, "tax_percent": 0,
        "stock_qty": 20, "reorder_level": 2,
    }, admin, db_path)
    create_sale([{"product_id": product, "quantity": 2}], "Test", "", admin, "Cash", 200, db_path=db_path)
    add_expense("Utilities", "Electricity", 100, __import__("datetime").date.today().isoformat(), admin, db_path)
    result = analyze_business(str(db_path))
    assert result["metrics"]["transactions_count"] == 1
    assert result["metrics"]["net_sales"] == 200
    assert result["metrics"]["net_profit"] == -20
    assert any("Operating expenses exceed gross profit" in item["title"] for item in result["insights"])
