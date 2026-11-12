import pytest

from app.services import (
    create_product, create_sale, create_user, list_products, refund_sale, sale_detail,
)


def setup_catalog(db_path):
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    product_id = create_product({
        "sku": "RICE-1", "name": "Rice", "price": 100, "cost_price": 60,
        "discount_percent": 10, "tax_percent": 5, "stock_qty": 20, "reorder_level": 2,
    }, owner, db_path)
    return owner, product_id


def test_cash_sale_calculates_discount_tax_change_and_stock(db_path):
    owner, product_id = setup_catalog(db_path)
    sale = create_sale([{"product_id": product_id, "quantity": 2}], "Test Customer", "9999999999",
                       owner, "Cash", amount_tendered=250, db_path=db_path)
    # Gross 200; item discount 20; GST 9 => 189 total; change 61.
    assert sale["subtotal"] == 200
    assert sale["discount_total"] == 20
    assert sale["tax_total"] == 9
    assert sale["total"] == 189
    assert sale["change_due"] == 61
    assert list_products(db_path=db_path)[0]["stock_qty"] == 18
    detail = sale_detail(sale["id"], db_path)
    assert detail["invoice_no"] == sale["invoice_no"]
    assert len(detail["items"]) == 1


def test_sale_is_atomic_and_insufficient_cash_is_rejected(db_path):
    owner, product_id = setup_catalog(db_path)
    with pytest.raises(ValueError, match="below"):
        create_sale([{"product_id": product_id, "quantity": 1}], "", "", owner, "Cash", 1, db_path=db_path)
    assert list_products(db_path=db_path)[0]["stock_qty"] == 20
    with pytest.raises(ValueError, match="Insufficient stock"):
        create_sale([{"product_id": product_id, "quantity": 30}], "", "", owner, "Cash", 9999, db_path=db_path)
    assert list_products(db_path=db_path)[0]["stock_qty"] == 20


def test_upi_requires_manual_confirmation_and_reference(db_path):
    owner, product_id = setup_catalog(db_path)
    with pytest.raises(ValueError, match="manually confirmed"):
        create_sale([{"product_id": product_id, "quantity": 1}], "", "", owner, "UPI", upi_confirmed=False,
                    payment_reference="UPI123", db_path=db_path)
    with pytest.raises(ValueError, match="reference ID"):
        create_sale([{"product_id": product_id, "quantity": 1}], "", "", owner, "UPI", upi_confirmed=True,
                    payment_reference="", db_path=db_path)
    sale = create_sale([{"product_id": product_id, "quantity": 1}], "", "", owner, "UPI", upi_confirmed=True,
                       payment_reference="UPI123", db_path=db_path)
    assert sale["payment_method"] == "UPI"


def test_partial_refund_restocks_stock_and_updates_status(db_path):
    owner, product_id = setup_catalog(db_path)
    sale = create_sale([{"product_id": product_id, "quantity": 3}], "", "", owner, "Cash", 1000, db_path=db_path)
    detail = sale_detail(sale["id"], db_path)
    item_id = detail["items"][0]["id"]
    refund = refund_sale(sale["id"], {item_id: 1}, "Wrong item", owner, restock=True, db_path=db_path)
    assert refund["amount"] == 94.5
    assert refund["status"] == "PARTIALLY_REFUNDED"
    assert list_products(db_path=db_path)[0]["stock_qty"] == 18
    updated = sale_detail(sale["id"], db_path)
    assert updated["refunded_total"] == 94.5
    assert updated["items"][0]["refunded_qty"] == 1


def test_duplicate_cart_lines_are_aggregated_before_stock_validation(db_path):
    owner, product_id = setup_catalog(db_path)
    with pytest.raises(ValueError, match="Insufficient stock"):
        create_sale([
            {"product_id": product_id, "quantity": 11},
            {"product_id": product_id, "quantity": 10},
        ], "", "", owner, "Cash", 5000, db_path=db_path)
    assert list_products(db_path=db_path)[0]["stock_qty"] == 20
