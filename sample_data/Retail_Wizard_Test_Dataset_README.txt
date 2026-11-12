RETAIL WIZARD 1.0 - TEST DATASET
================================

Files:
- Retail_Wizard_Test_Dataset.xlsx (Products is the first/active tab; Step-by-step Test Plan is the second tab)
- Retail_Wizard_Test_Products.csv (the same 8 products in CSV form)

Import:
1. Open Retail Wizard and sign in as Admin.
2. Go to Products > Import Excel / CSV.
3. Select either the XLSX or CSV file.
4. Expected import result: 8 imported, 0 skipped.

IMPORTANT:
- Import this test dataset only once into a fresh/demo database. Re-importing the same SKUs will be skipped as duplicates.
- Do not use the test products as real inventory or claim a demo UPI reference is a real payment.
- The app's UPI checkbox is cashier confirmation only; it does not connect to or verify a bank/payment gateway.
- Keep a backup before trying the workflow on a database containing real store records.
- A detailed step-by-step test sequence and expected values are included in the second worksheet.
