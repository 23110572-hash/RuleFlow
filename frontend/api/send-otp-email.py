"""Vercel HTTPS-to-SMTP relay for RuleFlow registration OTP emails."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler

MAX_REQUEST_BYTES = 8_192
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._json_response(200, {"status": "ok", "service": "RuleFlow email relay"})

    def do_POST(self) -> None:
        expected_secret = os.getenv("EMAIL_RELAY_SECRET", "")
        if not expected_secret:
            self._json_response(503, {"status": "error", "message": "Relay is not configured"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._json_response(400, {"status": "error", "message": "Invalid request size"})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json_response(400, {"status": "error", "message": "Invalid JSON"})
            return

        recipient = str(payload.get("recipient", "")).strip().lower()
        otp_code = str(payload.get("otp", "")).strip()
        if len(recipient) > 254 or not EMAIL_PATTERN.fullmatch(recipient):
            self._json_response(400, {"status": "error", "message": "Invalid recipient"})
            return
        if len(otp_code) != 6 or not otp_code.isdigit():
            self._json_response(400, {"status": "error", "message": "Invalid OTP"})
            return

        timestamp = self.headers.get("X-RuleFlow-Relay-Timestamp", "")
        provided_signature = self.headers.get("X-RuleFlow-Relay-Signature", "")
        try:
            timestamp_seconds = int(timestamp)
        except ValueError:
            timestamp_seconds = 0

        if abs(int(time.time()) - timestamp_seconds) > 60:
            self._json_response(403, {"status": "error", "message": "Forbidden"})
            return

        signed_payload = f"{timestamp}\n{recipient}\n{otp_code}".encode("utf-8")
        expected_signature = hmac.new(
            expected_secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        if not provided_signature or not hmac.compare_digest(
            provided_signature,
            expected_signature,
        ):
            self._json_response(403, {"status": "error", "message": "Forbidden"})
            return

        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip()
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
        try:
            smtp_port = int(os.getenv("SMTP_PORT", "465"))
        except ValueError:
            smtp_port = 0

        if not smtp_user or not smtp_password or smtp_port not in {465, 587}:
            self._json_response(503, {"status": "error", "message": "SMTP is not configured"})
            return

        message = EmailMessage()
        message["From"] = f"RuleFlow <{smtp_user}>"
        message["To"] = recipient
        message["Subject"] = "RuleFlow email verification"
        message.set_content(
            f"Your RuleFlow verification code is {otp_code}. "
            "It expires in 5 minutes. Do not share it with anyone."
        )
        message.add_alternative(_otp_html(otp_code), subtype="html")

        try:
            _send_smtp(smtp_server, smtp_port, smtp_user, smtp_password, message)
        except Exception as exc:
            print(f"RuleFlow SMTP relay failed: {type(exc).__name__}: {exc}")
            self._json_response(502, {"status": "error", "message": "Email delivery failed"})
            return

        self._json_response(200, {"status": "success"})

    def _json_response(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _send_smtp(
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    message: EmailMessage,
) -> None:
    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(
            smtp_server,
            smtp_port,
            timeout=15,
            context=context,
        ) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
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
