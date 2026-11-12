# Retail Wizard 1.0 - User guide

## 1. Start and secure the store

1. Run `run_windows.bat` on Windows or `./run_unix.sh` on macOS/Linux.
2. The welcome page offers **Register** and **Login**. Register the first account to create the store administrator; choose at least eight characters for the password.
3. After registration, the application opens a separate Login screen. Sign in with the new account.
4. When an administrator already exists, public registration creates a cashier account only. Admins can create additional admin/cashier accounts from **Users & Settings**.
5. Open **Users & Settings** to configure the store name, contact information, low-stock default and tax default. The optional UPI VPA is displayed as a reference only; the merchant QR image is loaded from the `assets` folder.

## 2. Add inventory

1. Open **Products**.
2. Use **Add product** for individual SKUs. Enter SKU, product name, category, unit, selling price, purchase cost, discount, tax, opening stock and reorder level. The form scrolls; its Save/Cancel buttons remain pinned at the bottom.
3. Use **Import Excel / CSV** for bulk catalogue import. The original 200-row catalogue is in `sample_data/Updated_Product_Catalogue.xlsx`. Use `sample_data/Retail_Wizard_Test_Dataset.xlsx` or `sample_data/Retail_Wizard_Test_Products.csv` for a small eight-product test dataset. Import a test file into a fresh/test database or only once to avoid duplicate SKUs.
4. Review imported stock quantities and expiry dates. The legacy workbook uses `Stock Available` as Yes/No, so the importer assigns 10 opening units for Yes and 0 for No. These are demonstration defaults; replace them with a physical stock count.
5. Use **Adjust stock** for shrinkage, damage, corrections and stock counts. Add a reason so the movement is auditable.
6. Products with stock at or below their reorder level appear on the dashboard.

## 3. Complete a sale

1. Open **Point of Sale** and search by SKU, barcode or product name.
2. Select a product, choose quantity next to the search field, and click **Add to cart** in the same top toolbar. Use + Qty / − Qty to change a selected cart line. The system checks available stock.
3. Enter customer name and phone (both optional for walk-in sales) and any additional order discount.
4. For **Cash**, the Cash received field defaults to the exact amount due. Change it if the customer pays more. Checkout is blocked when cash received is less than the amount due; change is calculated automatically.
5. For **UPI**, a separate payment window opens with your own merchant QR image and the amount due. Before using UPI, copy your bank/provider-issued QR image into `assets/store_upi_qr.png` (exact filename). Scan it in the UPI app, check the payee, enter the displayed amount if your QR is static, verify receipt in the store's actual UPI/bank application, enter its UTR/reference and tick the confirmation checkbox. The application only records the cashier's confirmation; it does not independently verify payment. UPI confirmation is disabled if the image is missing or invalid.
6. Complete the sale. A unique invoice number is generated, sale items and payment are stored, inventory is reduced atomically and a PDF invoice is saved under `invoices/`.

## 4. Record a supplier purchase

1. Open **Purchases** (admin only).
2. Enter the supplier name, select an existing product, enter quantity and unit cost, and add the line.
3. Add more lines as needed and choose **Record purchase**.
4. The system creates the supplier record if needed, saves the purchase and increases stock. The latest unit cost becomes the product's current cost for future margin analysis.

## 5. Manage operating expenses

1. Open **Expenses** (admin only).
2. Select a category, describe the expense, enter the amount and date, then save.
3. These records are included in the operating expense and net profit calculations.

## 6. Review invoices and issue refunds

1. Open **Sales History** and search for an invoice or customer.
2. Use **View / invoice** to inspect line items or generate its PDF again.
3. Use **Refund selected**, choose a sale item and enter the quantity being returned.
4. Choose whether the returned goods go back into available stock. The refund is recorded; staff must separately return money using the original payment channel.

## 7. Reports and backups

- Admins can open **Reports**, select Sales, Stock, Transactions, Purchases, Best sellers or Profit & Loss, and optionally set a date range.
- Report rows can be exported as CSV.
- **AI Insights** runs a 30-day explainable local analysis of stockouts, reorder levels, margins, expiry, no-sales items, refunds and expenses. Export its recommendations to CSV. It uses local rules and sends no data to a cloud AI API; recommendations are guidance, not guaranteed forecasts.
- Profit & Loss excludes sales tax from revenue, accounts for refund amounts and restocked cost of goods, and subtracts recorded operating expenses. It does not invent a gross margin percentage.
- Create backups from **Users & Settings** or the Dashboard. Backups are saved under `backups/` as SQLite database files.

## 8. Data storage and restore precautions

The live database is `data/retail_wizard.db`. Invoices are in `invoices/`; backups are in `backups/`. Close the app before manually copying database files. For restore, preserve a copy of the current database, replace it with a verified backup while the app is closed, then launch and check key records. A backup file contains customer and financial data and should be access-controlled.


## POS checkout updates

- Select a product, set the quantity in the quantity control beside Search, then click **Add to cart** above the product list.
- Use + Qty / − Qty to adjust the selected cart row; Remove deletes it.
- Cash checkout pre-fills the amount due. Its checkout button remains visible in the fixed footer. Change Cash received when the customer pays a different amount. Insufficient cash is rejected.
- UPI opens a separate payment window and displays `assets/store_upi_qr.png`. Add your own bank/provider-issued merchant QR image using that exact filename. Verify payee and amount in the UPI app, verify actual receipt, enter the UTR/reference, and tick the manual confirmation box. Only then is the sale recorded and the invoice generated. The image is static and may not carry the current amount; use the displayed amount when paying.

## Product form

The product editor has a scrollable field area and fixed Save/Cancel buttons. If the optional expiry field is below the fold, scroll inside the form; the Save button stays visible.

## AI Insights

Open **AI Insights** as an administrator and select Run analysis. The local rule-based engine checks inventory, sales, refunds, expiry, product margin and operating expenses over the last 30 days. Export recommendations to CSV. This is explainable decision support, not a trained predictive model or a substitute for accounting review.


## View product details for a completed transaction

On Dashboard, choose a row under Recent transactions and click **View details**, or double-click the row. In Sales History, double-click a transaction or select it and click **View / invoice**. The transaction detail window shows the sold product, quantity, selling price, purchase cost captured at sale time, discount, tax, line total and gross profit estimate. Purchase cost / profit is internal information and is not printed on the customer invoice.

## Voice announcement after checkout

When a sale is successfully committed, the application uses the computer's local speech engine to announce the payment method, amount and invoice status. UPI announcements currently occur only after the cashier manually verifies receipt in the UPI app, enters the UTR and confirms. This is not automatic bank detection.

## To enable automatic UPI detection

A static QR image cannot report payment status to the app. Ask Paytm Business / your payment provider for Dynamic QR or Payment Gateway API access. The integration must create a unique order per bill, verify the provider's signed callback/webhook or query its server-to-server transaction-status API, and only then mark the sale paid and play the voice announcement. Keep merchant keys on a secure backend.
