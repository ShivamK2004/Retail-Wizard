# Retail Wizard 1.0 — Verification report

Validation run: 2026-11-13

## Automated checks

| Check | Result |
|---|---|
| Python compile check (`python -m compileall -q app run.py`) | Passed |
| Automated unit tests (`python -m pytest -q`) | 21 passed |
| Authentication / password hashing / role rules | Passed |
| Product create/update and catalogue import | Passed |
| Cash sale, tax/discount, change and stock decrement | Passed |
| UPI manual confirmation and reference validation | Passed |
| Refund and optional stock restock | Passed |
| Purchase stock receipt and cost update | Passed |
| Cost-based Profit & Loss | Passed |
| SQLite backup / read-back | Passed |
| PDF invoice generation | Passed |
| Voice announcement text for cash / UPI and invoice status | Passed |
| Dashboard and Sales History transaction detail source compiles | Passed |
| Dashboard KPI dates use local timezone for SQLite UTC timestamps | Passed |
| Dashboard clock updates every second under Xvfb | Passed |
| Dashboard KPIs and recent transactions refresh after a new sale | Passed |
| Dashboard automatic data refresh and manual Refresh action | Passed in UI smoke test |
| Test CSV import (`Retail_Wizard_Test_Products.csv`) | 8 imported, 0 skipped |
| Test Excel import (`Retail_Wizard_Test_Dataset.xlsx`) | 8 imported, 0 skipped |
| Full catalogue import (`Updated_Product_Catalogue.xlsx`) | 200 imported, 0 skipped |
| Local AI-insights inventory, price-cost and P&L checks | Passed |

## Desktop UI smoke tests (Xvfb)

| Workflow | Result |
|---|---|
| Welcome page exposes Register and Login | Passed |
| Register → separate Login → Dashboard transition | Passed; screens do not stack |
| All nine admin pages render, including AI Insights | Passed |
| Product dialog shows Save/Cancel while fields scroll | Passed |
| Product form saved a record through the visible Save button | Passed |
| POS Add to cart control is visible beside search | Passed |
| POS cart quantity is added and cash due auto-fills | Passed |
| Cash checkout created a sale and PDF invoice | Passed |
| UPI opens a separate payment window | Passed |
| Merchant QR supports JPEG / JPG / PNG configured paths | Passed in configuration checks |
| Missing or invalid merchant QR prevents UPI confirmation | Passed in prior UI smoke test |
| UPI reference entry and manual confirmation created a sale and PDF invoice | Passed in prior UI smoke test |
| POS Cash/UPI checkout action remains visible at 1120 × 680 and 1440 × 850 | Passed in prior UI smoke test |
| Dashboard transaction details open and display stored cost fields | Passed with a temporary sale in a disposable test database |

## Environment limitations

These checks ran in a Linux Python environment; desktop UI automation used Xvfb. A native Windows 10/11 run and actual Windows SAPI voice playback were not performed here. The voice helper uses Windows' local SAPI voice via PowerShell and does not require cloud TTS. Test playback on the target Windows machine. UPI is still manual cashier confirmation only; no real bank/payment provider was connected or tested. Automatic UPI confirmation requires a payment-provider Dynamic QR / Gateway integration with server-side webhook or transaction-status verification.
