"""Generate, deliver, and verify registration email OTPs."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# This is safe only while Render runs a single process/instance. A shared store
# (database or Redis) is required before increasing WEB_CONCURRENCY or replicas.
_otp_store: dict[str, dict] = {}

OTP_EXPIRY_SECONDS = 300
VERIFICATION_EXPIRY_SECONDS = 600


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_otp() -> str:
    """Generate a cryptographically secure six-digit OTP."""
    return f"{secrets.randbelow(900_000) + 100_000:06d}"


def send_otp(email: str) -> dict:
    """Generate an OTP and deliver it to the normalized email address."""
    normalized_email = _normalize_email(email)
    code = generate_otp()
    _otp_store[normalized_email] = {
        "code": code,
        "expires": time.time() + OTP_EXPIRY_SECONDS,
    }

    try:
        _send_email(normalized_email, code)
    except Exception:
        logger.exception("OTP email delivery failed")
        _otp_store.pop(normalized_email, None)
        return {
            "ok": False,
            "message": "We could not send the verification email. Please try again.",
        }

    return {"ok": True, "message": "OTP sent to your email"}


def verify_otp(email: str, code: str) -> dict:
    """Verify the active OTP for an email address."""
    normalized_email = _normalize_email(email)
    stored = _otp_store.get(normalized_email)
    if not stored:
        return {"ok": False, "message": "No OTP found for this email. Please request a new one."}

    if time.time() > stored["expires"]:
        _otp_store.pop(normalized_email, None)
        return {"ok": False, "message": "OTP has expired. Please request a new one."}

    if not secrets.compare_digest(stored["code"], code.strip()):
        return {"ok": False, "message": "Invalid OTP. Please try again."}

    _otp_store.pop(normalized_email, None)
    _otp_store[f"verified:{normalized_email}"] = {
        "code": "verified",
        "expires": time.time() + VERIFICATION_EXPIRY_SECONDS,
    }
    return {"ok": True, "message": "Email verified successfully"}


def is_email_verified(email: str) -> bool:
    """Return whether the email has a current successful OTP verification."""
    normalized_email = _normalize_email(email)
    key = f"verified:{normalized_email}"
    stored = _otp_store.get(key)
    if not stored:
        return False
    if time.time() > stored["expires"]:
        _otp_store.pop(key, None)
        return False
    return True


def clear_verification(email: str) -> None:
    """Consume an email verification after successful registration."""
    _otp_store.pop(f"verified:{_normalize_email(email)}", None)


def _send_email(to_email: str, otp_code: str) -> None:
    """Send through the HTTPS relay on Render, or direct SMTP for local use."""
    if settings.email_relay_url:
        _send_email_via_relay(to_email, otp_code)
        return

    _send_email_via_smtp(to_email, otp_code)


def _send_email_via_relay(to_email: str, otp_code: str) -> None:
    """Ask the RuleFlow Vercel function to perform Gmail SMTP delivery."""
    relay_url = settings.email_relay_url.strip()
    relay_secret = settings.email_relay_secret

    if not relay_url.startswith("https://"):
        raise RuntimeError("EMAIL_RELAY_URL must use HTTPS")
    if not relay_secret:
        raise RuntimeError("EMAIL_RELAY_SECRET is not configured")

    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}\n{to_email}\n{otp_code}".encode("utf-8")
    signature = hmac.new(
        relay_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    response = httpx.post(
        relay_url,
        json={"recipient": to_email, "otp": otp_code},
        headers={
            "X-RuleFlow-Relay-Timestamp": timestamp,
            "X-RuleFlow-Relay-Signature": signature,
        },
        timeout=httpx.Timeout(20.0, connect=10.0),
        follow_redirects=False,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Email relay returned an invalid response") from exc

    if payload.get("status") != "success":
        raise RuntimeError("Email relay did not confirm delivery")


def _send_email_via_smtp(to_email: str, otp_code: str) -> None:
    """Direct SMTP fallback for environments where outbound port 465 works."""
    smtp_user = settings.smtp_user.strip()
    smtp_password = settings.smtp_password.replace(" ", "")

    if not smtp_user or not smtp_password:
        raise RuntimeError(
            "Email delivery is not configured. Set EMAIL_RELAY_URL and "
            "EMAIL_RELAY_SECRET, or SMTP_USER and SMTP_PASSWORD."
        )
    if settings.smtp_port != 465:
        raise RuntimeError("Direct SMTP delivery requires SMTP_PORT=465")

    message = EmailMessage()
    message["From"] = f"RuleFlow <{smtp_user}>"
    message["To"] = to_email
    message["Subject"] = "RuleFlow email verification"
    message.set_content(
        f"Your RuleFlow verification code is {otp_code}. "
        "It expires in 5 minutes. Do not share it with anyone."
    )
    message.add_alternative(_otp_html(otp_code), subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(
        settings.smtp_server,
        settings.smtp_port,
        timeout=15,
        context=context,
    ) as server:
        server.login(smtp_user, smtp_password)
        server.send_message(message)


def _otp_html(otp_code: str) -> str:
    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:24px;background:#f5f5f5;font-family:Segoe UI,Arial,sans-serif">
        <div style="max-width:500px;margin:auto;background:#fff;border-radius:12px;padding:40px">
          <h1 style="margin:0;color:#1a1a2e;font-size:24px;text-align:center">RuleFlow</h1>
          <p style="color:#666;text-align:center">SEBI Compliance Platform</p>
          <p style="color:#333;font-size:16px">Your verification code is:</p>
          <div style="margin:25px 0;text-align:center">
            <span style="display:inline-block;padding:15px 30px;border-radius:8px;background:#f0f4ff;color:#1a1a2e;font-size:36px;font-weight:bold;letter-spacing:8px">{otp_code}</span>
          </div>
          <p style="color:#666;font-size:14px">This code expires in 5 minutes. Do not share it with anyone.</p>
          <hr style="margin:25px 0;border:0;border-top:1px solid #eee">
          <p style="color:#999;font-size:12px;text-align:center">If you did not request this code, ignore this email.</p>
        </div>
      </body>
    </html>
    """
