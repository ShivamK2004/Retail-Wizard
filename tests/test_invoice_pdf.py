from app.invoices import generate_invoice_pdf


def test_invoice_pdf_generation(db_path, tmp_path):
    from app.services import create_product, create_sale, create_user, sale_detail
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    product_id = create_product({"sku": "PDF-1", "name": "Invoice Test Item", "price": 99,
                                 "cost_price": 50, "stock_qty": 4}, owner, db_path)
    sale = create_sale([{"product_id": product_id, "quantity": 1}], "Test Buyer", "1234567890",
                       owner, "Cash", 100, db_path=db_path)
    detail = sale_detail(sale["id"], db_path)
    target = generate_invoice_pdf(detail, tmp_path / "invoice.pdf", {"store_name": "Test Store"})
    assert target.exists()
    assert target.read_bytes().startswith(b"%PDF-")
