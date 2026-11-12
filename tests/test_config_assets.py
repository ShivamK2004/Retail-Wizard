from app.config import ASSETS_DIR, PROJECT_DIR, UPI_QR_IMAGE, UPI_QR_CANDIDATES


def test_merchant_upi_qr_uses_documented_project_asset_path():
    assert ASSETS_DIR == PROJECT_DIR / "assets"
    assert UPI_QR_IMAGE in UPI_QR_CANDIDATES
    assert UPI_QR_CANDIDATES == (
        PROJECT_DIR / "assets" / "store_upi_qr.jpeg",
        PROJECT_DIR / "assets" / "store_upi_qr.jpg",
        PROJECT_DIR / "assets" / "store_upi_qr.png",
    )
    assert ASSETS_DIR.is_dir()
