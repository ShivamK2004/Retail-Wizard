"""End-to-end smoke test for the browser version using an isolated temp database."""
from __future__ import annotations
import os
import re
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="rw-web-smoke-") as temp:
    os.environ["RETAIL_WIZARD_DB"] = os.path.join(temp, "smoke.db")
    os.environ["SECRET_KEY"] = "smoke-test-secret-that-is-never-used-in-production"
    os.environ["INITIAL_ADMIN_SETUP_KEY"] = "smoke-one-time-setup-key"
    os.environ["COOKIE_SECURE"] = "false"
    os.environ["APP_TIMEZONE"] = "Asia/Kolkata"

    from fastapi.testclient import TestClient
    from webapp.main import app

    def token(client: TestClient, path: str) -> str:
        response = client.get(path)
        response.raise_for_status()
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        assert match, f"CSRF token missing on {path}"
        return match.group(1)

    with TestClient(app) as client:
        assert client.get("/", follow_redirects=False).status_code == 303
        csrf = token(client, "/setup")
        rejected = client.post("/setup", data={"csrf_token": csrf, "setup_key": "wrong-key",
            "full_name": "Should Not Exist", "username": "wrong-admin",
            "password": "smoke-password-123", "confirm_password": "smoke-password-123"})
        assert rejected.status_code == 400 and "setup key is incorrect" in rejected.text
        csrf = token(client, "/setup")
        assert client.post("/setup", data={"csrf_token": csrf, "setup_key": "smoke-one-time-setup-key",
            "full_name": "Smoke Admin",
            "username": "smoke-admin", "password": "smoke-password-123",
            "confirm_password": "smoke-password-123"}, follow_redirects=False).status_code == 303
        assert client.get("/setup", follow_redirects=False).status_code == 303
        csrf = token(client, "/login")
        assert client.post("/login", data={"csrf_token": csrf, "username": "smoke-admin",
            "password": "smoke-password-123"}, follow_redirects=False).status_code == 303
        csrf = token(client, "/products")
        client.post("/products/create", data={"csrf_token": csrf, "sku": "SMOKE-001",
            "name": "Smoke Test Product", "price": "20", "cost_price": "8",
            "stock_qty": "5", "reorder_level": "1"}, follow_redirects=True).raise_for_status()
        csrf = token(client, "/pos")
        response = client.post("/pos/checkout", data={"csrf_token": csrf,
            "items_json": '[{"product_id":1,"quantity":1}]', "customer_name": "Smoke Customer",
            "payment_method": "Cash", "amount_tendered": "20", "order_discount_percent": "0"},
            follow_redirects=True)
        response.raise_for_status()
        assert "Smoke Test Product" in response.text
        pdf = client.get("/sales/1/invoice.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert client.get("/dashboard").status_code == 200
        assert client.get("/sales").status_code == 200
        assert client.get("/reports").status_code == 200
        assert client.get("/insights").status_code == 200

print("Retail Wizard Web smoke test passed: setup, login, product, POS, sale details, PDF, dashboard, sales, reports and insights.")
