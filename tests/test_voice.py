from app.voice import build_payment_announcement


def test_cash_payment_announcement_contains_amount_and_invoice():
    text = build_payment_announcement("Cash", 183.26, "RW-123", True)
    assert "Cash payment of 183.26 rupees received successfully" in text
    assert "Invoice RW-123 generated" in text


def test_upi_announcement_says_manual_cashier_confirmation():
    text = build_payment_announcement("UPI", "183.26", "RW-456", True)
    assert "UPI payment of 183.26 rupees has been recorded after cashier confirmation" in text


def test_invoice_failure_announcement_does_not_claim_generated():
    text = build_payment_announcement("Cash", 50, "RW-789", False)
    assert "Invoice generation needs attention" in text
    assert "Invoice RW-789 generated" not in text
