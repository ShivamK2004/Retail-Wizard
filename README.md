# Retail Wizard 1.0

Retail Wizard is a desktop retail/POS and inventory management application built with **Python, Tkinter and SQLite**. This upgraded edition uses the supplied Software Requirements Specification (SRS) as its acceptance baseline and replaces the earlier set of side-effect-heavy scripts with a modular, testable application.

## What is included

- Secure first-run administrator setup and login using salted PBKDF2-SHA256 password hashes.
- Admin and cashier roles with separate navigation and account activation controls.
- Product catalogue CRUD, SKU/barcode search, price/cost, item discount, tax, stock, reorder level and expiry date.
- Excel (`.xlsx`) and CSV import, product CSV export, and manual stock adjustments with a stock movement ledger.
- POS cart with visible add/quantity controls, customer details, item/order discounts, product-level tax, automatic cash-due prefill/change calculation and a separate UPI QR/reference/confirmation step.
- Persistent sales and sale line-items, invoice numbers, printable PDF invoices and sales history.
- Partial/full item refunds, optional stock restocking and refund history.
- Supplier purchases that increase on-hand stock and update product purchase cost.
- Operating expense capture, low-stock alerts and sales/stock/purchase/best-seller/transaction reports.
- Profit & loss calculation based on recorded sales, refunds, item costs and operating expenses (not a hard-coded margin).
- CSV report export, audit trail, SQLite online backups and an explainable offline AI-assisted business-insights module for stock risks, margin, expiry, refunds, sales and expenses.

## Requirements

- Windows 10/11, macOS or Linux.
- Python 3.10 or newer.
- Tkinter (included with most standard Python distributions; on some Linux distributions install `python3-tk`).
- Python packages listed in `requirements.txt` (`openpyxl` for Excel import, `fpdf2` for invoices and `Pillow` to display your merchant QR image).

## Run on Windows

1. Extract the ZIP file to a writable folder.
2. Double-click `run_windows.bat`, or run these commands from PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

## Run on macOS / Linux

```bash
chmod +x run_unix.sh
./run_unix.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

## First-time setup

The first screen always presents **Register** and **Login**. Register the first account to create the store administrator; registration after an administrator exists creates a cashier account (not another public admin). After registration, the app opens the separate Login screen. Admin users can create cashier/admin accounts from **Users & Settings**. Cashiers can use the POS, products and sales history areas; administration pages are restricted to admins.

The database is created automatically at `data/retail_wizard.db`. Do not delete it unless you intend to remove all store data. The `backups/` folder stores database backups created from the application.

## Import the supplied catalogue

Open **Products → Import Excel / CSV** and choose `sample_data/Updated_Product_Catalogue.xlsx`. For focused testing, choose `sample_data/Retail_Wizard_Test_Dataset.xlsx` (Excel with test checklist) or `sample_data/Retail_Wizard_Test_Products.csv` (8 test products). The importer recognizes supported headers, validates SKU/name/price, skips duplicates and reports rows that need attention.

The legacy workbook represents `Quantity` as a pack/unit label (for example, `5 pcs`) and `Stock Available` as a Yes/No flag. For this workbook only, a Yes value becomes an initial stock quantity of 10 and No becomes 0. Review these opening quantities and adjust them to the store's real counted stock before using the POS. Expiry dates that cannot be parsed are left blank.

## Payment boundary / important limitation

Cash is calculated and recorded by the application. The cash received field is prefilled with the cart total until the cashier edits it; the checkout action remains pinned at the bottom of the POS panel. UPI opens a separate checkout window and displays your own merchant QR image from `assets/store_upi_qr.png` alongside the amount due. The app does **not** generate a replacement merchant QR, integrate with a payment gateway or verify UPI in real time. The cashier must verify the payee, amount and successful receipt in the actual UPI/bank application, then enter the UTR/reference and tick the confirmation checkbox. A static merchant QR may not encode the sale amount, so enter the displayed amount in the UPI app when required. The app does not collect card data or initiate actual refunds. See `assets/README.md` for QR setup.

## AI-assisted business insights

The **AI Insights** page runs transparent local rules against the last 30 days of sales and the current catalogue. It identifies out-of-stock and reorder items, products priced below cost after item discount, items with no recorded demand, upcoming expiry dates, high refund ratios, expense/profit pressure and a simple 14-day stock-cover estimate. It runs locally without an API key and does not send customer or financial data to a cloud AI service. Recommendations are decision support, not guaranteed forecasts; verify stock counts, supplier lead times and accounting records before acting.

## Invoices, refunds and reports

- PDF invoices are stored under `invoices/`.
- A refund creates a refund record. The cashier/admin must actually return funds outside this app; the app does not transfer money.
- Refunds can optionally return inventory to stock.
- Profit & Loss uses recorded sales net of refunds, cost-of-goods-sold from sale-time product costs, and operating expenses entered in the Expenses page. Supplier purchases update inventory and product cost; they are not double-counted as an immediate operating expense.
- Reports can be filtered by date and exported as CSV.

## Data and security notes

- SQLite foreign keys and transactional updates protect the sale, inventory and payment-record workflows from partial writes.
- Passwords are stored as salted PBKDF2 hashes; plaintext passwords are never stored.
- User deactivation is supported; at least one active administrator must remain.
- The SQLite data file itself is not encrypted at rest in this edition. Use operating-system disk encryption and file permissions, and protect backup copies.
- Audit events capture account, product, settings, sale, purchase, refund, stock and expense actions.
- Backups contain sensitive customer and financial information. Store them securely and test restoring a copy before relying on disaster recovery.
- This is a local single-store desktop application. It is not a multi-terminal network server, cloud backup system or audited accounting package.

## Run tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The business logic tests use temporary SQLite databases and do not require a graphical display. To launch the desktop interface, the system must have a working Tk display.

## Project layout

```text
Retail_Wizard_Project/
├── app/
│   ├── config.py       # App paths and defaults
│   ├── db.py           # SQLite schema, transactions and backups
│   ├── importer.py     # Excel/CSV catalogue import
│   ├── invoices.py     # PDF invoice generation
│   ├── insights.py     # Explainable offline business analysis
│   ├── security.py     # Password hashing/verification
│   ├── services.py     # Testable business operations
│   └── ui.py           # Tkinter desktop interface
├── assets/             # Place your merchant QR here as store_upi_qr.png
├── data/               # Created SQLite database
├── backups/            # Database backups
├── invoices/           # Generated invoices
├── docs/               # Original SRS and diagrams
├── sample_data/        # Supplied Excel catalogue
├── tests/              # Headless unit tests
├── run.py
├── requirements.txt
└── README.md
```


## Voice payment announcements

After the application successfully records a sale, Retail Wizard speaks a local announcement using Windows SAPI (no cloud voice service or API key). The announcement is generated after the sale record is committed and the invoice generation attempt completes. Cash is announced after the cash tender validation succeeds. UPI is announced only after the current manual cashier confirmation and transaction-reference checks. This local voice feature does **not** independently detect or verify a bank transfer.

## Automatic UPI payment detection

The supplied static merchant QR is display-only. It does not send a payment-completed event to this desktop application. Genuine automatic payment confirmation requires a payment-provider integration, such as a Paytm Business Dynamic QR / Payment Gateway flow, a merchant order ID, server-side credentials, and a publicly reachable HTTPS callback/webhook or a server-to-server transaction-status check. Merchant secrets must be stored on a secure backend, not in this desktop source code. Do not mark an order paid based solely on a customer screenshot, typed UTR, or unchecked/checked cashier box.

The app accepts these store QR filenames (first existing file wins): `assets/store_upi_qr.jpeg`, `assets/store_upi_qr.jpg`, or `assets/store_upi_qr.png`.

## Transaction details

On the Dashboard, select a recent transaction and click **View details**, or double-click its row. Sales History also supports double-click / Enter or the **View / invoice** button. The details view displays the historical unit purchase cost stored with each sale item, total cost, line profit and invoice totals.

## Browser / online web edition

A separate FastAPI + responsive HTML web interface is included for browser use. It reuses the existing business services and SQLite schema. For local browser testing, run `run_web_windows.bat` on Windows or `./run_web_unix.sh` on macOS/Linux, then open `http://127.0.0.1:8000`. See `WEB_DEPLOYMENT.md` for the Render Free testing deployment, its temporary SQLite storage limitations, security settings and the migration path before production use. The original Tkinter launcher remains available.
