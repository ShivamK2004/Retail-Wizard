from app.services import (
    authenticate, create_product, create_user, deactivate_product, list_products,
    update_product,
)


def test_first_user_and_password_hashing(db_path):
    user_id = create_user("Store Owner", "owner", "SecurePass123", "admin", db_path)
    assert user_id > 0
    assert authenticate("owner", "SecurePass123", db_path)["role"] == "admin"
    assert authenticate("owner", "wrong-password", db_path) is None
    assert authenticate("missing", "SecurePass123", db_path) is None


def test_product_crud_and_deactivation(db_path):
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    product_id = create_product({
        "sku": "SKU-1", "name": "Coffee", "category": "Beverages", "price": 120,
        "cost_price": 80, "discount_percent": 5, "tax_percent": 5,
        "stock_qty": 10, "reorder_level": 2,
    }, owner, db_path)
    product = list_products(db_path=db_path)[0]
    assert product["id"] == product_id
    assert product["stock_qty"] == 10
    assert product["discount_percent"] == 5

    update_product(product_id, {
        "sku": "SKU-1", "name": "Coffee Pack", "category": "Beverages", "price": 130,
        "cost_price": 85, "discount_percent": 0, "tax_percent": 5, "reorder_level": 3,
    }, owner, db_path)
    assert list_products(db_path=db_path)[0]["name"] == "Coffee Pack"
    deactivate_product(product_id, owner, db_path)
    assert list_products(db_path=db_path) == []
    assert list_products(include_inactive=True, db_path=db_path)[0]["is_active"] == 0
