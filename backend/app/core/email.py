from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.db.repo_notifications import NotificationRecord

logger = logging.getLogger(__name__)

_SMTP_HOST = os.environ.get("SMTP_HOST", "")
_SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
_SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
_SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@decisionos.app")


def send_notification_email(*, to: str, notification: NotificationRecord) -> bool:
    """Send a single notification email via SMTP. Returns True on success, False otherwise.

    Configuration via env vars:
        SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM

    Compatible with any SMTP provider (Resend, Gmail, SendGrid, self-hosted).
    For Resend: SMTP_HOST=smtp.resend.com, SMTP_USERNAME=resend, SMTP_PASSWORD=<api_key>
    """
    if not _SMTP_HOST:
        logger.debug("email.send skipped — SMTP_HOST not configured")
        return False

    subject = f"[DecisionOS] {notification.title}"
    body_html = f"""
<html><body>
<h2>{notification.title}</h2>
<p>{notification.body}</p>
<hr>
<p style="color:#888;font-size:12px;">
  Notification type: {notification.type}<br>
  You can manage your notification preferences in your
  <a href="http://localhost:3000/profile">Profile settings</a>.
</p>
</body></html>
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _SMTP_FROM
    msg["To"] = to
    msg.attach(MIMEText(notification.body, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(_SMTP_USERNAME, _SMTP_PASSWORD)
            smtp.sendmail(_SMTP_FROM, to, msg.as_string())
        logger.info("email.sent to=%s notification_id=%s", to, notification.id)
        return True
    except Exception:
        logger.warning("email.send_failed to=%s notification_id=%s", to, notification.id, exc_info=True)
        return False
