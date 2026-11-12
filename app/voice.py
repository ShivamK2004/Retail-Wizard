from __future__ import annotations

import base64
import os
import shutil
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def build_payment_announcement(
    payment_method: str,
    amount: Any,
    invoice_no: str,
    invoice_generated: bool = True,
) -> str:
    """Build a concise spoken status; does not claim independent bank verification."""
    method = str(payment_method).strip().upper()
    if method not in {"CASH", "UPI"}:
        method = "PAYMENT"
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amount_text = f"{value:.2f}"
    invoice_safe = "".join(ch for ch in str(invoice_no) if ch.isalnum() or ch in "-_")
    if method == "UPI":
        lead = f"UPI payment of {amount_text} rupees has been recorded after cashier confirmation."
    elif method == "CASH":
        lead = f"Cash payment of {amount_text} rupees received successfully."
    else:
        lead = f"Payment of {amount_text} rupees recorded successfully."
    if invoice_generated:
        return f"{lead} Invoice {invoice_safe} generated. Thank you."
    return f"{lead} Invoice generation needs attention. Please reprint the invoice."


def announce_payment_success(
    payment_method: str,
    amount: Any,
    invoice_no: str,
    invoice_generated: bool = True,
) -> bool:
    """Speak the completed-sale announcement asynchronously using local TTS.

    On Windows this uses the built-in SAPI.SpVoice engine through PowerShell,
    so no cloud service or API key is required. Linux can use spd-say/espeak.
    This function must be called only after the payment/sale has been accepted.
    """
    phrase = build_payment_announcement(payment_method, amount, invoice_no, invoice_generated)

    try:
        if os.name == "nt":
            encoded = base64.b64encode(phrase.encode("utf-8")).decode("ascii")
            script = (
                "$text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "'));"
                "$voice=New-Object -ComObject SAPI.SpVoice;"
                "[void]$voice.Speak($text)"
            )
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=True,
            )
            return True

        speaker = shutil.which("spd-say") or shutil.which("espeak")
        if speaker:
            subprocess.Popen(
                [speaker, phrase],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False
