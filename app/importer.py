from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .services import create_product

HEADER_ALIASES = {
    "sku": {"sku", "product code", "product_code", "item code"},
    "barcode": {"barcode", "bar code"},
    "name": {"name", "product name", "product_name", "item name"},
    "category": {"category", "product category"},
    "brand": {"brand", "manufacturer"},
    "unit": {"unit", "uom", "quantity"},
    "price": {"price", "price (₹)", "selling price", "sale price"},
    "cost_price": {"cost price", "cost_price", "purchase price", "unit cost"},
    "discount_percent": {"discount", "discount (%)", "discount percent", "discount_percent"},
    "tax_percent": {"tax", "tax (%)", "tax percent", "tax_percent", "gst"},
    "stock_qty": {"stock", "stock qty", "stock_qty", "available quantity", "quantity in stock"},
    "stock_available": {"stock available", "stock_available", "availability"},
    "reorder_level": {"reorder level", "reorder_level", "minimum stock", "low stock threshold"},
    "expiry_date": {"expiry date", "expiry_date", "expiry"},
}


def _normalise_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    found = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(found.group(0)) if found else default


def _date_value(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _map_headers(headers: list[Any]) -> dict[str, int]:
    normalized = [_normalise_header(h) for h in headers]
    result = {}
    for target, aliases in HEADER_ALIASES.items():
        for index, header in enumerate(normalized):
            if header in aliases:
                result[target] = index
                break
    if "name" not in result or "price" not in result:
        raise ValueError("The spreadsheet must contain Product Name and Price columns.")
    return result


def _row_value(row: tuple[Any, ...], mapping: dict[str, int], key: str, default: Any = None) -> Any:
    index = mapping.get(key)
    return row[index] if index is not None and index < len(row) else default


def import_products(file_path: str | Path, actor_id: int, db_path: str | Path | None = None,
                    default_opening_stock: float = 10) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    elif suffix in {".xlsx", ".xlsm"}:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows = [tuple(r) for r in sheet.iter_rows(values_only=True)]
        finally:
            workbook.close()
    else:
        raise ValueError("Choose an .xlsx or .csv product file.")
    if len(rows) < 2:
        raise ValueError("The selected file contains no product rows.")

    mapping = _map_headers(list(rows[0]))
    imported, skipped = 0, 0
    errors: list[str] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(v not in (None, "") for v in row):
            continue
        name = str(_row_value(row, mapping, "name", "")).strip()
        price = _number(_row_value(row, mapping, "price"), -1)
        sku_value = _row_value(row, mapping, "sku")
        sku = str(sku_value).strip() if sku_value not in (None, "") else f"IMP-{line_no:05d}"
        if not name or price < 0:
            skipped += 1
            errors.append(f"Row {line_no}: missing name or invalid price")
            continue
        stock_raw = _row_value(row, mapping, "stock_qty")
        if stock_raw not in (None, ""):
            stock = max(0.0, _number(stock_raw, 0))
        else:
            available = str(_row_value(row, mapping, "stock_available", "yes") or "yes").strip().lower()
            stock = default_opening_stock if available in {"yes", "y", "true", "available", "in stock", "1"} else 0.0
        unit_raw = _row_value(row, mapping, "unit", "pcs")
        unit = str(unit_raw or "pcs").strip()
        # In the legacy workbook, Quantity describes pack size (e.g. "5 pcs"),
        # while Stock Available is only a Yes/No flag. Keep the unit, not the pack size, here.
        unit_match = re.search(r"[A-Za-z]+", unit)
        unit = unit_match.group(0) if unit_match else "pcs"
        product = {
            "sku": sku, "name": name,
            "barcode": _row_value(row, mapping, "barcode"),
            "category": _row_value(row, mapping, "category", "General") or "General",
            "brand": _row_value(row, mapping, "brand", "") or "",
            "unit": unit,
            "price": price,
            "cost_price": _number(_row_value(row, mapping, "cost_price"), 0),
            "discount_percent": min(100, max(0, _number(_row_value(row, mapping, "discount_percent"), 0))),
            "tax_percent": min(100, max(0, _number(_row_value(row, mapping, "tax_percent"), 0))),
            "stock_qty": stock,
            "reorder_level": max(0, _number(_row_value(row, mapping, "reorder_level"), 5)),
            "expiry_date": _date_value(_row_value(row, mapping, "expiry_date")),
        }
        try:
            create_product(product, actor_id, db_path)
            imported += 1
        except ValueError as exc:
            skipped += 1
            errors.append(f"Row {line_no} ({sku}): {exc}")
    return {"imported": imported, "skipped": skipped, "errors": errors}
