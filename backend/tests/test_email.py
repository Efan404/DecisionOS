from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import MagicMock, patch


def test_send_skips_when_no_smtp_config(monkeypatch):
    """send_notification_email returns False and does not raise when SMTP is not configured."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    import importlib
    import app.core.email as email_mod
    importlib.reload(email_mod)
    from app.db.repo_notifications import NotificationRecord
    from app.core.time import utc_now_iso
    notif = NotificationRecord(
        id="n1", user_id="u1", type="news_match",
        title="Test", body="Body", metadata_json="{}",
        read_at=None, created_at=utc_now_iso(),
    )
    result = email_mod.send_notification_email(to="user@example.com", notification=notif)
    assert result is False


def test_send_calls_smtp_when_configured(monkeypatch):
    """send_notification_email calls smtplib.SMTP when SMTP_HOST is set."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    import importlib
    import app.core.email as email_mod
    importlib.reload(email_mod)
    from app.db.repo_notifications import NotificationRecord
    from app.core.time import utc_now_iso
    notif = NotificationRecord(
        id="n1", user_id="u1", type="news_match",
        title="Test title", body="Test body", metadata_json="{}",
        read_at=None, created_at=utc_now_iso(),
    )
    mock_smtp_instance = MagicMock()
    mock_smtp_cls = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", mock_smtp_cls):
        result = email_mod.send_notification_email(to="user@example.com", notification=notif)
    assert result is True
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("user", "pass")
    mock_smtp_instance.sendmail.assert_called_once()
