# Retail Wizard 1.0 - SRS traceability

| Original SRS requirement | 1.0 implementation | Status / boundary |
|---|---|---|
| Secure user registration and login | Welcome screen with separate Register/Login, first registration as admin, later public registration as cashier, PBKDF2 hashes, admin/cashier roles and account activation | Implemented locally |
| Inventory CRUD and categorization | Product add/edit/deactivate, category, SKU/barcode, price/cost, discount, tax, expiry | Implemented |
| Stock tracking and restock alerts | Stock ledger, sale/purchase/refund movements, manual adjustments, reorder levels, dashboard alerts | Implemented |
| Accounts management | Sales, supplier purchase records, operating expenses and audit log | Implemented |
| Sales/purchase/stock reports | Date filters and CSV export | Implemented |
| Cash payment | Tendered amount validation and correct change calculation | Implemented |
| UPI payment and validation | Separate payment window displays the store-provided `assets/store_upi_qr.png`, shows amount due, captures reference and requires manual confirmation | Static QR may not encode amount; local recording only; no live provider verification |
| Tax and discount calculation | Per-product discount/tax and additional order discount | Implemented at sale time |
| Invoice generation and storage | Unique invoice number, stored line items and PDF generation | Implemented locally |
| Printing / digital invoice access | PDF file can be opened/printed using the operating system | Implemented via PDF file; no printer driver integration |
| Refund | Item-level partial/full refund record with optional restock | Actual transfer must be completed outside the app |
| Supplier purchase order tracking | Supplier records, purchase lines and stock receipt | Basic purchase receipt workflow; no email or supplier portal |
| Security backup | SQLite online backup and audit log | Manual local backup; no encrypted cloud backup |
| Offline operation | Local SQLite desktop database | Implemented for local use |
| Business analysis / AI assistance | Explainable local analysis of inventory, margin, expiry, demand, refunds and operating expenses | Implemented as transparent offline rules; not a trained predictive model or cloud LLM |

## Explicit scope decisions

- There was no time schedule or delivery deadline in the uploaded material. The 13-page `Retail_Wizard_SRS.pdf` was used as the functional baseline.
- No external payment gateway, bank credentials, email provider, cloud storage or supplier service credentials were supplied. These integrations are not faked; UPI/refunds require out-of-band confirmation.
- The implementation is a single-store desktop application. Multi-user concurrent access over a network and cloud synchronization are outside this delivery.
