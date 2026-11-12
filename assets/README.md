# Store UPI QR image

Place your own merchant UPI QR image in this directory using **one** of these exact names:

- `store_upi_qr.jpeg`
- `store_upi_qr.jpg`
- `store_upi_qr.png`

The app checks these names in the order listed and loads the first existing file. Pillow can decode JPEG and PNG without converting the file extension. Keep the QR image square, clear and uncropped.

Use a QR issued by your bank or payment provider. Do not use a payment confirmation screenshot, a customer's QR code, or a random sample QR.

This is a static image: it does not send the changing invoice amount to the UPI app and cannot notify Retail Wizard when money arrives. The payment window displays the amount due separately. In this release, a cashier must verify the payee, amount, successful receipt and transaction reference in the real UPI/bank app before confirming the sale.

No sample or placeholder QR is bundled, to avoid accidentally directing a payment to the wrong account.
