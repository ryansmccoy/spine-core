"""Email (SMTP) alert channel."""

from __future__ import annotations

from typing import Any

from spine.core.errors import TransientError
from spine.framework.alerts.base import BaseChannel
from spine.framework.alerts.protocol import (
    Alert,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)


class EmailChannel(BaseChannel):
    """
    Email channel using SMTP.

    Sends alerts via email.
    """

    def __init__(
        self,
        name: str,
        smtp_host: str,
        from_address: str,
        recipients: list[str],
        *,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        use_tls: bool = True,
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        **kwargs: Any,
    ):
        super().__init__(name, ChannelType.EMAIL, min_severity=min_severity, **kwargs)
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_address = from_address
        self._recipients = recipients
        self._use_tls = use_tls

    def _build_message(self, alert: Alert) -> str:
        """Build email message."""
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{alert.severity.value}] {alert.title}"
        msg["From"] = self._from_address
        msg["To"] = ", ".join(self._recipients)

        # Plain text
        text = f"""
{alert.severity.value}: {alert.title}

Source: {alert.source}
Domain: {alert.domain or "N/A"}
Time: {alert.created_at.isoformat()}

{alert.message}
"""
        if alert.error:
            text += f"\nError: {alert.error.message}"

        msg.attach(MIMEText(text, "plain"))

        return msg.as_string()

    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert via email."""
        import smtplib

        try:
            if self._use_tls:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port)

            if self._smtp_user and self._smtp_password:
                server.login(self._smtp_user, self._smtp_password)

            message = self._build_message(alert)
            server.sendmail(self._from_address, self._recipients, message)
            server.quit()

            return DeliveryResult.ok(self._name)

        except smtplib.SMTPException as e:
            return DeliveryResult.fail(self._name, TransientError(str(e), cause=e))
        except Exception as e:
            return DeliveryResult.fail(self._name, e)
