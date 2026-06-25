"""Optional email delivery for morning reports."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_report(subject: str, body: str) -> bool:
    """Send morning report via SMTP. Returns True if sent."""
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    to_addr = os.getenv("EMAIL_TO", "").strip()
    from_addr = os.getenv("EMAIL_FROM", user).strip()
    port = int(os.getenv("SMTP_PORT", "587"))

    if not all([host, user, password, to_addr]):
        logger.info("Email not configured — skipping send")
        return False

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("Morning report emailed to %s", to_addr)
        return True
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return False
