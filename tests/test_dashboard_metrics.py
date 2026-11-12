from datetime import datetime, timedelta, timezone

from app.db import connect
from app.services import create_user, dashboard_metrics


def test_dashboard_metrics_use_local_date_for_utc_sale_timestamps(db_path):
    """A sale shortly after local midnight may still have yesterday's UTC date."""
    cashier_id = create_user("Dashboard Owner", "dashboard_owner", "SecurePass123", "admin", db_path)

    local_midnight_sale = datetime.now().astimezone().replace(
        hour=0, minute=10, second=0, microsecond=0
    )
    utc_timestamp = local_midnight_sale.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO sales(invoice_no, cashier_id, sold_at, subtotal, total,
                   payment_method, refunded_total, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("RW-LOCAL-DAY-TEST", cashier_id, utc_timestamp, 100.0, 100.0,
             "Cash", 25.0, "PARTIALLY_REFUNDED"),
        )

    metrics = dashboard_metrics(db_path)
    assert metrics["sales_today"] == 75.0
    assert metrics["transactions_today"] == 1


def test_dashboard_metrics_exclude_previous_local_day_sale(db_path):
    cashier_id = create_user("Dashboard Owner", "dashboard_owner", "SecurePass123", "admin", db_path)
    yesterday_local = datetime.now().astimezone().replace(
        hour=12, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)
    utc_timestamp = yesterday_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO sales(invoice_no, cashier_id, sold_at, subtotal, total,
                   payment_method, refunded_total, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("RW-PREVIOUS-DAY-TEST", cashier_id, utc_timestamp, 50.0, 50.0,
             "Cash", 0.0, "COMPLETED"),
        )

    metrics = dashboard_metrics(db_path)
    assert metrics["sales_today"] == 0.0
    assert metrics["transactions_today"] == 0
