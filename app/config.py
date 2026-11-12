from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Retail Wizard"
APP_VERSION = "1.0"
PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
BACKUP_DIR = PROJECT_DIR / "backups"
ASSETS_DIR = PROJECT_DIR / "assets"
# Accept the store's supplied QR without requiring extension conversion.
UPI_QR_CANDIDATES = (
    ASSETS_DIR / "store_upi_qr.jpeg",
    ASSETS_DIR / "store_upi_qr.jpg",
    ASSETS_DIR / "store_upi_qr.png",
)
UPI_QR_IMAGE = next((candidate for candidate in UPI_QR_CANDIDATES if candidate.is_file()), UPI_QR_CANDIDATES[0])
DB_PATH = Path(os.environ.get("RETAIL_WIZARD_DB", DATA_DIR / "retail_wizard.db"))
CURRENCY_SYMBOL = "₹"
DEFAULT_LOW_STOCK_THRESHOLD = 5
DEFAULT_TAX_PERCENT = 0.0

DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
