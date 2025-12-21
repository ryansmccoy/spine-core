#!/usr/bin/env python3
"""Alert Routing — AlertRegistry and delivery channels.

WHY STRUCTURED ALERTING
───────────────────────
A operation or workflow failure buried in a log file means nobody gets
paged until users complain.  Spine’s alerting framework routes alerts
to multiple channels (console, Slack, email) filtered by severity,
with fingerprint-based deduplication to prevent alert storms.

Alerts work at both the Operation level (one step failed) and the
Workflow level (an entire workflow completed with errors).  The
Workflow engine can be configured to emit alerts automatically on
step failure via TrackedWorkflowRunner.

ARCHITECTURE
────────────
    Operation/Workflow failure
         │
         ▼
    Alert(severity, title, message, source, domain)
         │
         ▼
    ┌──────────────────────────┐
    │ AlertRegistry            │
    │  .send_to_all(alert)     │
    └────┬───────┬───────┬──────┘
         │       │       │
    ┌────┴──┐ ┌──┴───┐ ┌─┴─────┐
    │Console│ │ Slack │ │ Email │
    │≥ WARN │ │≥ ERROR│ │≥ CRIT │
    └───────┘ └──────┘ └───────┘

    Each channel has min_severity — only alerts at or above
    that level are delivered to it.

SEVERITY LEVELS
───────────────
    Level        Value   Meaning
    ──────────── ─────── ───────────────────────────
    INFO         10      Routine events
    WARNING      20      Needs attention soon
    ERROR        30      Operation failed
    CRITICAL     40      System-wide impact

FINGERPRINTING
──────────────
    Fingerprint = hash(severity + title + source).
    Same severity/title/source → same fingerprint → dedup.
    Different messages still match (“Instance 1” vs “Instance 2”).

Run: python examples/08_framework/05_alert_routing.py

See Also:
    06_source_connectors — source failure alerts
    07_framework_logging — log events that trigger alerts
    04_orchestration/08_tracked_runner — auto-alerting on workflow failure
"""

from spine.framework.alerts import (
    Alert,
    AlertRegistry,
    AlertSeverity,
    ChannelType,
    ConsoleChannel,
    DeliveryResult,
)


def main():
    print("=" * 60)
    print("Alert Routing")
    print("=" * 60)

    # ── 1. Create a console channel ─────────────────────────────
    print("\n--- 1. Create channels ---")
    # This channel only forwards WARNING and above
    warning_channel = ConsoleChannel(
        name="ops-console",
        min_severity=AlertSeverity.WARNING,
        color=False,  # Disable ANSI for clean output
    )
    print(f"  Channel: {warning_channel.name}")
    print(f"  Type:    {warning_channel.channel_type.value}")
    print(f"  Min sev: {warning_channel.min_severity.value}")

    # All-levels channel
    debug_channel = ConsoleChannel(
        name="debug-console",
        min_severity=AlertSeverity.INFO,
        color=False,
    )

    # ── 2. Register channels ────────────────────────────────────
    print("\n--- 2. Register channels ---")
    registry = AlertRegistry()
    registry.register(warning_channel)
    registry.register(debug_channel)
    print(f"  Registered: {registry.list_channels()}")
    print(f"  Console channels: {registry.list_by_type(ChannelType.CONSOLE)}")

    # ── 3. Send alerts at different severities ──────────────────
    print("\n--- 3. Send alerts ---")
    alerts = [
        Alert(
            severity=AlertSeverity.INFO,
            title="Operation started",
            message="SEC filing ingestion operation began processing",
            source="sec_ingestion",
            domain="filings",
        ),
        Alert(
            severity=AlertSeverity.WARNING,
            title="Slow response",
            message="SEC EDGAR API response time exceeded 5s threshold",
            source="sec_ingestion",
            domain="filings",
            metadata={"response_time_ms": 5200},
        ),
        Alert(
            severity=AlertSeverity.ERROR,
            title="Parse failure",
            message="Failed to parse 10-K filing for CIK 0000320193",
            source="sec_parser",
            domain="filings",
            execution_id="exec_abc123",
        ),
        Alert(
            severity=AlertSeverity.CRITICAL,
            title="Database connection lost",
            message="Cannot connect to PostgreSQL after 3 retries",
            source="db_monitor",
        ),
    ]

    for alert in alerts:
        print(f"\n  Sending [{alert.severity.value}] {alert.title}:")
        results = registry.send_to_all(alert)
        for r in results:
            status = "delivered" if r.success else "failed"
            msg = f" ({r.message})" if r.message else ""
            print(f"    -> {r.channel_name}: {status}{msg}")

    # ── 4. Send to specific channel ─────────────────────────────
    print("\n--- 4. Send to specific channel ---")
    result = registry.send(
        Alert(
            severity=AlertSeverity.INFO,
            title="Test alert",
            message="This goes only to ops-console",
            source="test",
        ),
        channel_name="ops-console",
    )
    print(f"  Result: success={result.success}, message={result.message}")
    # INFO is below ops-console's WARNING threshold, so it's filtered

    # ── 5. Alert fingerprinting ─────────────────────────────────
    print("\n--- 5. Alert fingerprinting ---")
    alert_a = Alert(
        severity=AlertSeverity.ERROR,
        title="Connection timeout",
        message="Instance 1",
        source="db_monitor",
    )
    alert_b = Alert(
        severity=AlertSeverity.ERROR,
        title="Connection timeout",
        message="Instance 2",
        source="db_monitor",
    )
    print(f"  Alert A fingerprint: {alert_a.fingerprint}")
    print(f"  Alert B fingerprint: {alert_b.fingerprint}")
    print(f"  Same fingerprint (dedup): {alert_a.fingerprint == alert_b.fingerprint}")

    # ── 6. Severity ordering ────────────────────────────────────
    print("\n--- 6. Severity ordering ---")
    print(f"  INFO < WARNING: {AlertSeverity.INFO < AlertSeverity.WARNING}")
    print(f"  ERROR < CRITICAL: {AlertSeverity.ERROR < AlertSeverity.CRITICAL}")
    print(f"  WARNING >= INFO: {AlertSeverity.WARNING >= AlertSeverity.INFO}")

    # ── 7. DeliveryResult factory methods ───────────────────────
    print("\n--- 7. DeliveryResult ---")
    ok = DeliveryResult.ok("slack-ops", message="Sent to #alerts")
    fail = DeliveryResult.fail("email-ops", error=ConnectionError("SMTP timeout"))
    print(f"  OK:   success={ok.success}, channel={ok.channel_name}")
    print(f"  Fail: success={fail.success}, error={fail.error}")

    print("\n" + "=" * 60)
    print("[OK] Alert routing example complete")


if __name__ == "__main__":
    main()
