# Alerting Framework

This document covers the multi-channel alerting system for operational notifications.

---

## Overview

The **Alerting Framework** provides:
- Multiple notification channels (Slack, Email, Webhook)
- Severity-based routing
- Domain filtering (send FINRA alerts only to FINRA channel)
- Delivery tracking and retry
- Throttling to prevent alert storms

---

## Core Concepts

### Alert

An alert contains the notification content:

```python
from spine.framework.alerts import Alert, AlertSeverity

alert = Alert(
    severity=AlertSeverity.ERROR,
    title="FINRA Ingestion Failed",
    message="Weekly OTC file download timed out after 30 seconds",
    source="finra.otc.ingest",
    domain="finra.otc_transparency",
    metadata={"file": "otc_weekly_20260111.psv"},
)
```

### Severity Levels

| Severity | Use Case | Typical Action |
|----------|----------|----------------|
| `INFO` | Informational notices | Log only |
| `WARNING` | Potential issues | Monitor |
| `ERROR` | Failures requiring attention | Investigate |
| `CRITICAL` | System-wide emergencies | Immediate action |

### Channels

Channels are the destinations for alerts:

```python
from spine.framework.alerts import SlackChannel, EmailChannel

slack = SlackChannel(
    name="ops-slack",
    webhook_url="https://hooks.slack.com/services/...",
    min_severity=AlertSeverity.ERROR,
)

email = EmailChannel(
    name="ops-email",
    smtp_host="smtp.company.com",
    from_address="spine@company.com",
    recipients=["ops-team@company.com"],
    min_severity=AlertSeverity.CRITICAL,
)
```

---

## Channel Types

### SlackChannel

Sends formatted messages to Slack via incoming webhooks.

```python
from spine.framework.alerts import SlackChannel, alert_registry

slack = SlackChannel(
    name="engineering-alerts",
    webhook_url="https://hooks.slack.com/services/T.../B.../...",
    
    # Optional settings
    channel="#data-alerts",     # Override default channel
    username="Spine Bot",       # Bot name
    icon_emoji=":robot_face:",  # Bot icon
    min_severity=AlertSeverity.ERROR,
    domains=["finra.*", "market_data.*"],  # Filter by domain
)

alert_registry.register(slack)
```

**Slack Message Format**:
```
🔴 ERROR: FINRA Ingestion Failed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Source: finra.otc.ingest
Domain: finra.otc_transparency
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Weekly OTC file download timed out after 30 seconds
```

### EmailChannel

Sends emails via SMTP.

```python
from spine.framework.alerts import EmailChannel

email = EmailChannel(
    name="ops-email",
    smtp_host="smtp.company.com",
    smtp_port=587,
    smtp_user="alerts@company.com",
    smtp_password="...",  # Consider using secrets manager
    from_address="spine-alerts@company.com",
    recipients=["ops-team@company.com", "manager@company.com"],
    use_tls=True,
    min_severity=AlertSeverity.CRITICAL,
)

alert_registry.register(email)
```

### WebhookChannel

POST alerts to any HTTP endpoint.

```python
from spine.framework.alerts import WebhookChannel

webhook = WebhookChannel(
    name="custom-webhook",
    url="https://monitoring.company.com/api/alerts",
    headers={
        "Authorization": "Bearer ...",
        "X-Source": "spine",
    },
    min_severity=AlertSeverity.WARNING,
)

alert_registry.register(webhook)
```

**Webhook Payload**:
```json
{
    "severity": "ERROR",
    "title": "FINRA Ingestion Failed",
    "message": "Weekly OTC file download timed out",
    "source": "finra.otc.ingest",
    "domain": "finra.otc_transparency",
    "created_at": "2026-01-11T10:30:00Z",
    "fingerprint": "ERROR|finra.otc.ingest|FINRA Ingestion Failed|finra.otc_transparency"
}
```

### ConsoleChannel

For development and testing—prints to stdout.

```python
from spine.framework.alerts import ConsoleChannel

console = ConsoleChannel(
    name="dev-console",
    min_severity=AlertSeverity.INFO,
    color=True,  # ANSI colors
)

alert_registry.register(console)
```

---

## Alert Registry

The global registry manages all channels:

```python
from spine.framework.alerts import alert_registry

# Register channels
alert_registry.register(slack)
alert_registry.register(email)

# Send to all matching channels
results = alert_registry.send_to_all(alert)

# Send to specific channel
result = alert_registry.send(alert, "ops-slack")

# Send to all channels of a type
results = alert_registry.send_to_type(alert, ChannelType.SLACK)

# List channels
names = alert_registry.list_channels()
slack_channels = alert_registry.list_by_type(ChannelType.SLACK)
```

---

## Convenience Function

The simplest way to send alerts:

```python
from spine.framework.alerts import send_alert, AlertSeverity

send_alert(
    severity=AlertSeverity.ERROR,
    title="Pipeline Failed",
    message="FINRA ingestion could not complete",
    source="finra.otc.ingest",
    domain="finra",
)
```

---

## Filtering

### By Severity

Each channel has a `min_severity` threshold:

```python
SlackChannel(
    name="critical-only",
    webhook_url="...",
    min_severity=AlertSeverity.CRITICAL,  # Only CRITICAL alerts
)
```

### By Domain

Filter alerts to specific domains using glob patterns:

```python
SlackChannel(
    name="finra-alerts",
    webhook_url="...",
    domains=["finra.*"],  # Only FINRA domain alerts
)

SlackChannel(
    name="all-trading",
    webhook_url="...",
    domains=["finra.*", "market_data.*", "trading.*"],
)
```

### Enabling/Disabling

```python
channel = alert_registry.get("ops-slack")
channel.disable()  # Temporarily stop sending

# Later
channel.enable()
```

---

## Delivery Results

Every send returns a `DeliveryResult`:

```python
result = alert_registry.send(alert, "ops-slack")

if result.success:
    print(f"Delivered at {result.delivered_at}")
else:
    print(f"Failed: {result.error}")
    print(f"Attempt: {result.attempt}")
```

---

## SQL Schema

Alert operations are tracked in the database:

### `core_alert_channels` - Channel Configuration

```sql
CREATE TABLE core_alert_channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    channel_type TEXT NOT NULL,  -- slack, email, webhook
    config_json TEXT NOT NULL,   -- Type-specific config
    min_severity TEXT NOT NULL DEFAULT 'ERROR',
    domains TEXT,                -- JSON array of domain patterns
    enabled INTEGER NOT NULL DEFAULT 1,
    throttle_minutes INTEGER NOT NULL DEFAULT 5,
    
    -- Health tracking
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### `core_alerts` - Alert Log

```sql
CREATE TABLE core_alerts (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    domain TEXT,
    execution_id TEXT,
    run_id TEXT,
    metadata_json TEXT,
    dedup_key TEXT,      -- For throttling
    created_at TEXT NOT NULL
);
```

### `core_alert_deliveries` - Delivery Status

```sql
CREATE TABLE core_alert_deliveries (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    status TEXT NOT NULL,  -- PENDING, SENT, FAILED, THROTTLED
    attempted_at TEXT,
    delivered_at TEXT,
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    next_retry_at TEXT
);
```

### `core_alert_throttle` - Deduplication

```sql
CREATE TABLE core_alert_throttle (
    dedup_key TEXT PRIMARY KEY,
    last_sent_at TEXT NOT NULL,
    send_count INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT NOT NULL
);
```

---

## Integration with Workflows

Alert on workflow failures:

```python
from spine.orchestration import Workflow, Step, StepResult
from spine.framework.alerts import send_alert, AlertSeverity

def notify_on_failure(ctx, config):
    # Check if previous step failed
    ingest_result = ctx.get_output("ingest")
    if ingest_result.get("error"):
        send_alert(
            severity=AlertSeverity.ERROR,
            title=f"Workflow {ctx.workflow_name} failed",
            message=ingest_result["error"],
            source=ctx.workflow_name,
            domain=ctx.get_param("domain"),
            run_id=ctx.run_id,
        )
        return StepResult.ok(output={"alerted": True})
    
    return StepResult.ok(output={"alerted": False})

workflow = Workflow(
    name="finra.weekly",
    steps=[
        Step.pipeline("ingest", "finra.otc.ingest"),
        Step.lambda_("alert_on_fail", notify_on_failure),
    ],
)
```

---

## Configuration Example

Typical production setup:

```python
# config.py
from spine.framework.alerts import (
    SlackChannel,
    EmailChannel,
    WebhookChannel,
    alert_registry,
    AlertSeverity,
)

def configure_alerting():
    """Configure alert channels at application startup."""
    
    # Engineering Slack (all errors)
    alert_registry.register(SlackChannel(
        name="eng-slack",
        webhook_url=os.environ["SLACK_WEBHOOK_ENG"],
        min_severity=AlertSeverity.ERROR,
    ))
    
    # Ops Slack (critical only)
    alert_registry.register(SlackChannel(
        name="ops-slack",
        webhook_url=os.environ["SLACK_WEBHOOK_OPS"],
        min_severity=AlertSeverity.CRITICAL,
    ))
    
    # FINRA-specific channel
    alert_registry.register(SlackChannel(
        name="finra-slack",
        webhook_url=os.environ["SLACK_WEBHOOK_FINRA"],
        min_severity=AlertSeverity.WARNING,
        domains=["finra.*"],
    ))
    
    # Email for critical
    alert_registry.register(EmailChannel(
        name="critical-email",
        smtp_host=os.environ["SMTP_HOST"],
        from_address="spine@company.com",
        recipients=["oncall@company.com"],
        min_severity=AlertSeverity.CRITICAL,
    ))
    
    # Monitoring system integration
    alert_registry.register(WebhookChannel(
        name="datadog",
        url="https://api.datadoghq.com/api/v1/events",
        headers={"DD-API-KEY": os.environ["DATADOG_API_KEY"]},
        min_severity=AlertSeverity.ERROR,
    ))
```

---

## Best Practices

### 1. Use Appropriate Severity

```python
# ❌ Everything is critical
send_alert(severity=AlertSeverity.CRITICAL, ...)

# ✅ Graduated severity
send_alert(severity=AlertSeverity.INFO, ...)     # FYI notices
send_alert(severity=AlertSeverity.WARNING, ...)  # Potential issues
send_alert(severity=AlertSeverity.ERROR, ...)    # Actual failures
send_alert(severity=AlertSeverity.CRITICAL, ...) # P0 emergencies
```

### 2. Include Context

```python
# ❌ No context
send_alert(
    severity=AlertSeverity.ERROR,
    title="Pipeline failed",
    message="Something went wrong",
    source="unknown",
)

# ✅ Rich context
send_alert(
    severity=AlertSeverity.ERROR,
    title="FINRA OTC Ingestion Failed",
    message="File download timed out after 30s. Retry scheduled.",
    source="finra.otc.ingest",
    domain="finra.otc_transparency",
    metadata={
        "file": "otc_weekly_20260111.psv",
        "url": "https://api.finra.org/...",
        "timeout_seconds": 30,
        "retry_at": "2026-01-11T11:00:00Z",
    },
)
```

### 3. Use Domain Filtering

```python
# ❌ One channel for everything
SlackChannel(name="all-alerts", ...)

# ✅ Separate channels by domain
SlackChannel(name="finra-alerts", domains=["finra.*"], ...)
SlackChannel(name="trading-alerts", domains=["trading.*"], ...)
```

### 4. Test Channels

```python
# Send test alert on startup
def verify_alerting():
    results = send_alert(
        severity=AlertSeverity.INFO,
        title="Alerting System Test",
        message="This is a test alert from Spine startup",
        source="spine.system",
    )
    for r in results:
        if not r.success:
            log.error(f"Channel {r.channel_name} failed: {r.error}")
```
