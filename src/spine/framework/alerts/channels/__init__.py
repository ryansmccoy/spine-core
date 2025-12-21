"""Alert channel implementations.

Manifesto:
    Each channel module implements a single delivery target.
    New channels are added as modules here and registered in
    the alert registry.

Tags:
    spine-core, framework, alerts, channels, delivery

Doc-Types:
    api-reference
"""

from spine.framework.alerts.channels.console import ConsoleChannel
from spine.framework.alerts.channels.email import EmailChannel
from spine.framework.alerts.channels.slack import SlackChannel
from spine.framework.alerts.channels.webhook import WebhookChannel

__all__ = [
    "ConsoleChannel",
    "EmailChannel",
    "SlackChannel",
    "WebhookChannel",
]
