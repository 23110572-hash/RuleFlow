"""Vercel HTTPS-to-SMTP relay for RuleFlow obligation-register emails.

Deliberately separate from send-otp-email.py. That function carries registration
and login; this one carries a PDF attachment. Keeping them apart means a change
here can never break sign-in.

Shares EMAIL_RELAY_SECRET, but signs every field it acts on rather than just the
recipient, so a captured request cannot be replayed with a different subject,
filename or attachment.
"""
from __future__ import annotations

import base64
import binascii
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

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# base64 inflates by ~4/3, so this bounds a ~9MB PDF plus the JSON envelope.
MAX_REQUEST_BYTES = 13 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 9 * 1024 * 1024
MAX_SUBJECT_CHARS = 200
MAX_BODY_CHARS = 20_000
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._json_response(200, {"status": "ok", "service": "RuleFlow report relay"})

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
        subject = str(payload.get("subject", "")).strip()
        body_text = str(payload.get("body_text", ""))
        body_html = str(payload.get("body_html", ""))
        attachment_name = str(payload.get("attachment_name", "")).strip()
        attachment_b64 = str(payload.get("attachment_b64", ""))

        if len(recipient) > 254 or not EMAIL_PATTERN.fullmatch(recipient):
            self._json_response(400, {"status": "error", "message": "Invalid recipient"})
            return
        if not subject or len(subject) > MAX_SUBJECT_CHARS:
            self._json_response(400, {"status": "error", "message": "Invalid subject"})
            return
        if len(body_text) > MAX_BODY_CHARS or len(body_html) > MAX_BODY_CHARS:
            self._json_response(400, {"status": "error", "message": "Body too long"})
            return
        if not SAFE_FILENAME.fullmatch(attachment_name) or not attachment_name.endswith(".pdf"):
            self._json_response(400, {"status": "error", "message": "Invalid attachment name"})
            return

        try:
            attachment = base64.b64decode(attachment_b64, validate=True)
        except (binascii.Error, ValueError):
            self._json_response(400, {"status": "error", "message": "Invalid attachment"})
            return
        if not attachment or len(attachment) > MAX_ATTACHMENT_BYTES:
            self._json_response(400, {"status": "error", "message": "Invalid attachment size"})
            return
        if attachment[:5] != b"%PDF-":
            self._json_response(400, {"status": "error", "message": "Attachment is not a PDF"})
            return

        timestamp = self.headers.get("X-RuleFlow-Relay-Timestamp", "")
        provided_signature = self.headers.get("X-RuleFlow-Relay-Signature", "")
        try:
            timestamp_seconds = int(timestamp)
        except ValueError:
            timestamp_seconds = 0
        # A register PDF takes longer to upload than a 6-digit code, so allow a
        # wider window than the OTP relay while still bounding replay.
        if abs(int(time.time()) - timestamp_seconds) > 300:
            self._json_response(403, {"status": "error", "message": "Forbidden"})
            return

        signed_payload = "\n".join(
            [
                timestamp,
                recipient,
                subject,
                attachment_name,
                hashlib.sha256(attachment).hexdigest(),
            ]
        ).encode("utf-8")
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
        message["Subject"] = subject
        message.set_content(body_text or "Your RuleFlow obligation register is attached.")
        if body_html:
            message.add_alternative(body_html, subtype="html")
        message.add_attachment(
            attachment, maintype="application", subtype="pdf", filename=attachment_name
        )

        try:
            _send_smtp(smtp_server, smtp_port, smtp_user, smtp_password, message)
        except Exception as exc:
            print(f"RuleFlow report relay failed: {type(exc).__name__}: {exc}")
            self._json_response(502, {"status": "error", "message": "Email delivery failed"})
            return

        self._json_response(200, {"status": "success"})

    def log_message(self, *args) -> None:  # keep Vercel logs free of request lines
        return

    def _json_response(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


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
            smtp_server, smtp_port, timeout=30, context=context
        ) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.send_message(message)
