# Automatic UPI payment detection – integration requirements

## What works in Retail Wizard 1.0

- The app displays the store's static merchant QR from `assets/store_upi_qr.jpeg`, `.jpg`, or `.png`.
- The cashier enters the transaction reference / UTR and checks the manual confirmation only after verifying receipt in the payment app or bank statement.
- After the sale is successfully recorded, Retail Wizard creates the invoice and plays an offline voice announcement using the Windows Speech API.
- The UPI voice message explicitly says the payment was recorded after cashier confirmation. It does not claim the application independently verified a bank transfer.

## What is needed for automatic confirmation

A static QR image cannot send a payment status event to this desktop app. Automatic confirmation needs a payment-provider integration, for example Paytm Business Dynamic QR / Payment Gateway:

1. A merchant account approved/enabled for the provider's Dynamic QR or Payment Gateway APIs.
2. Server-side merchant credentials (MID and merchant key / signing secret, according to the enabled product).
3. A backend service that creates a unique provider order / QR for the exact invoice amount.
4. A public HTTPS callback/webhook endpoint, or server-to-server transaction-status verification.
5. Signature/checksum validation and checks that order ID, amount, currency and final status match the pending local sale.
6. Idempotent processing so a duplicated callback cannot create a second sale or invoice.
7. After the backend confirms final success, notify the desktop POS (polling or an authenticated local connection); only then mark the UPI sale paid, generate the invoice, and play the success announcement.

Do not store production merchant secrets in a desktop client, source control, or a public ZIP. Keep them on the backend in environment variables or a secret manager. Never mark a sale paid based only on a customer screenshot, typed UTR, or a client-side callback without server-side validation.

## Paytm official documentation

- Dynamic QR: https://www.paytmpayments.com/docs/dynamic-qr-code-payments/
- Callback and Webhook: https://www.paytmpayments.com/docs/callback-and-webhook/
- Verify Payment Status: https://www.paytmpayments.com/docs/jscheckout-verify-payment/
- Payment status response fields: https://www.paytmpayments.com/docs/payment-status

This project version does not yet include the live Paytm gateway integration. You need the merchant's enabled product and credentials before that part can be implemented and tested.
