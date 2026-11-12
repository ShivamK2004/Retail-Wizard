from openpyxl import Workbook

from app.importer import import_products
from app.services import create_user, list_products


def test_importer_maps_legacy_excel_headers(db_path, tmp_path):
    owner = create_user("Owner", "owner", "SecurePass123", "admin", db_path)
    path = tmp_path / "products.xlsx"
    workbook = Workbook(); sheet = workbook.active
    sheet.append(["Sr No", "Category", "Product Name", "Brand", "Product Code", "Quantity", "Price (₹)", "Discount (%)", "Final Price (₹)", "Stock Available", "Expiry Date"])
    sheet.append([1, "Grocery", "Rice", "Brand A", "SKU-RICE", "5 kg", 100, 5, 95, "Yes", "2027-02-01"])
    sheet.append([2, "Grocery", "Dal", "Brand B", "SKU-DAL", "1 kg", 80, 0, 80, "No", "bad-date"])
    workbook.save(path)
    result = import_products(path, owner, db_path)
    assert result["imported"] == 2
    products = list_products(db_path=db_path)
    rice = next(p for p in products if p["sku"] == "SKU-RICE")
    dal = next(p for p in products if p["sku"] == "SKU-DAL")
    assert rice["stock_qty"] == 10
    assert rice["unit"] == "kg"
    assert rice["discount_percent"] == 5
    assert dal["stock_qty"] == 0
    assert dal["expiry_date"] is None
