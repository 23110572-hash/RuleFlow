"""Deliver the obligation register PDF by email.

Mirrors :mod:`app.services.otp_service`: on Render outbound SMTP is blocked, so
delivery goes through an HTTPS relay running as a Vercel function; anywhere that
permits port 465 it can send directly.

The report relay is a SEPARATE function from the OTP relay. The OTP path is the
registration and login flow, its payload shape and signature are fixed, and it is
not worth risking to add an attachment to something else.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

import httpx

from app.config import settings

log = logging.getLogger(__name__)

#: Gmail's own ceiling is far higher, but a register this large means something
#: has gone wrong upstream, and a serverless relay should not be asked to
#: base64 it.
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(stem: str, suffix: str = ".pdf", max_len: int = 96) -> str:
    """A filename derived from a document title that is safe in a Content-
    Disposition header and on any filesystem."""
    cleaned = _UNSAFE_FILENAME.sub("-", (stem or "obligation-register").strip())
    cleaned = cleaned.strip("-._") or "obligation-register"
    return cleaned[:max_len] + suffix


def send_register_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    """Send the register. Raises on failure; the caller decides how loud that is."""
    if not to_email:
        raise RuntimeError("No recipient address for the obligation register")
    if not pdf_bytes:
        raise RuntimeError("Refusing to email an empty attachment")
    if len(pdf_bytes) > MAX_ATTACHMENT_BYTES:
        raise RuntimeError(
            f"Register PDF is {len(pdf_bytes):,} bytes, over the "
            f"{MAX_ATTACHMENT_BYTES:,} byte limit"
        )

    relay_url = settings.effective_report_relay_url
    if relay_url:
        _send_via_relay(relay_url, to_email, subject, body_text, body_html, pdf_bytes, filename)
        return
    _send_via_smtp(to_email, subject, body_text, body_html, pdf_bytes, filename)


def _send_via_relay(
    relay_url: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    relay_secret = settings.email_relay_secret

    if not relay_url.startswith("https://"):
        raise RuntimeError("Report relay URL must use HTTPS")
    if not relay_secret:
        raise RuntimeError("EMAIL_RELAY_SECRET is not configured")

    attachment_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    timestamp = str(int(time.time()))
    # Sign every field the relay will act on. Signing only the recipient would
    # let a replayed request swap the subject, body or attachment.
    signed = "\n".join(
        [
            timestamp,
            to_email,
            subject,
            filename,
            hashlib.sha256(pdf_bytes).hexdigest(),
        ]
    ).encode("utf-8")
    signature = hmac.new(relay_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()

    response = httpx.post(
        relay_url,
        json={
            "recipient": to_email,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "attachment_name": filename,
            "attachment_b64": attachment_b64,
        },
        headers={
            "X-RuleFlow-Relay-Timestamp": timestamp,
            "X-RuleFlow-Relay-Signature": signature,
        },
        timeout=httpx.Timeout(60.0, connect=10.0),
        follow_redirects=False,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Report relay returned an invalid response") from exc
    if payload.get("status") != "success":
        raise RuntimeError("Report relay did not confirm delivery")


def _send_via_smtp(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    smtp_user = settings.smtp_user.strip()
    smtp_password = settings.smtp_password.replace(" ", "")
    if not smtp_user or not smtp_password:
        # Name the likely cause. On a hosted deployment outbound SMTP is usually
        # blocked and the credentials live with the relay, not here — so landing
        # in this branch at all normally means no relay URL was resolved.
        raise RuntimeError(
            "No email relay is configured and this host has no SMTP credentials. "
            "Set EMAIL_RELAY_URL (the report relay is derived from it) or "
            "REPORT_RELAY_URL, or provide SMTP_USER and SMTP_PASSWORD."
        )
    if settings.smtp_port != 465:
        raise RuntimeError("Direct SMTP delivery requires SMTP_PORT=465")

    message = EmailMessage()
    message["From"] = f"RuleFlow <{smtp_user}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)
    message.add_alternative(body_html, subtype="html")
    message.add_attachment(
        pdf_bytes, maintype="application", subtype="pdf", filename=filename
    )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(
        settings.smtp_server, settings.smtp_port, timeout=30, context=context
    ) as server:
        server.login(smtp_user, smtp_password)
        server.send_message(message)
