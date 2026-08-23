"""Email OTP service — send and verify one-time passwords for registration."""
from __future__ import annotations

import random
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

# In-memory OTP store: {email: {"code": "123456", "expires": timestamp}}
_otp_store: dict[str, dict] = {}

OTP_EXPIRY_SECONDS = 300  # 5 minutes


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return str(random.randint(100000, 999999))


def send_otp(email: str) -> dict:
    """Generate and send an OTP to the given email address."""
    code = generate_otp()
    _otp_store[email] = {"code": code, "expires": time.time() + OTP_EXPIRY_SECONDS}

    try:
        _send_email(email, code)
        return {"ok": True, "message": "OTP sent to your email"}
    except Exception as e:
        # Remove stored OTP on send failure
        _otp_store.pop(email, None)
        return {"ok": False, "message": f"Failed to send OTP: {str(e)}"}


def verify_otp(email: str, code: str) -> dict:
    """Verify the OTP for a given email."""
    stored = _otp_store.get(email)
    if not stored:
        return {"ok": False, "message": "No OTP found for this email. Please request a new one."}

    if time.time() > stored["expires"]:
        _otp_store.pop(email, None)
        return {"ok": False, "message": "OTP has expired. Please request a new one."}

    if stored["code"] != code.strip():
        return {"ok": False, "message": "Invalid OTP. Please try again."}

    # OTP verified — mark as verified and remove
    _otp_store.pop(email, None)
    # Store verification flag (valid for 10 minutes for registration)
    _otp_store[f"verified:{email}"] = {"code": "verified", "expires": time.time() + 600}
    return {"ok": True, "message": "Email verified successfully"}


def is_email_verified(email: str) -> bool:
    """Check if an email has been recently verified via OTP."""
    stored = _otp_store.get(f"verified:{email}")
    if not stored:
        return False
    if time.time() > stored["expires"]:
        _otp_store.pop(f"verified:{email}", None)
        return False
    return True


def clear_verification(email: str) -> None:
    """Clear verification flag after successful registration."""
    _otp_store.pop(f"verified:{email}", None)


def _send_email(to_email: str, otp_code: str) -> None:
    """Send OTP email via Gmail SMTP."""
    sender_email = settings.smtp_email
    sender_password = settings.smtp_password

    msg = MIMEMultipart("alternative")
    msg["From"] = f"RuleFlow <{sender_email}>"
    msg["To"] = to_email
    msg["Subject"] = f"RuleFlow - Your Verification Code: {otp_code}"

    html = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #1a1a2e; margin: 0; font-size: 24px;">RuleFlow</h1>
                <p style="color: #666; margin-top: 5px; font-size: 14px;">SEBI Compliance Platform</p>
            </div>
            <p style="color: #333; font-size: 16px;">Your verification code is:</p>
            <div style="text-align: center; margin: 25px 0;">
                <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #1a1a2e; background: #f0f4ff; padding: 15px 30px; border-radius: 8px; display: inline-block;">{otp_code}</span>
            </div>
            <p style="color: #666; font-size: 14px;">This code expires in 5 minutes. Do not share it with anyone.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
            <p style="color: #999; font-size: 12px; text-align: center;">If you didn't request this code, please ignore this email.</p>
        </div>
    </body>
    </html>
    """

    text = f"Your RuleFlow verification code is: {otp_code}\n\nThis code expires in 5 minutes."

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
