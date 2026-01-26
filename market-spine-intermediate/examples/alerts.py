#!/usr/bin/env python3
"""
Alerting Framework Example - AlertChannel for Notifications

This example demonstrates spine-core's alerting framework:
1. Alert creation with severity levels
2. ConsoleChannel for development/testing
3. SlackChannel for production alerts
4. AlertRegistry for managing channels
5. Filtering by severity and domain

Run:
    cd market-spine-intermediate
    uv run python -m examples.alerts
"""

from __future__ import annotations

import sys
from datetime import datetime

# Spine core imports
from spine.framework.alerts import (
    # Enums
    AlertSeverity,
    ChannelType,
    # Data classes
    Alert,
    DeliveryResult,
    # Protocols
    AlertChannel,
    # Implementations
    BaseChannel,
    ConsoleChannel,
    SlackChannel,
    # Registry
    AlertRegistry,
    alert_registry,
    # Functions
    send_alert,
)
from spine.core.errors import SourceError, ErrorContext


# =============================================================================
# Example 1: Creating Alerts
# =============================================================================


def demo_alert_creation():
    """Demonstrate creating Alert objects."""
    print("=" * 70)
    print("EXAMPLE 1: Creating Alerts")
    print("=" * 70)
    print()
    
    # INFO alert - informational
    info_alert = Alert(
        severity=AlertSeverity.INFO,
        title="Weekly ingestion started",
        message="FINRA OTC transparency data ingestion has started for week 2025-07-04",
        source="finra.otc_transparency.ingest_week",
        domain="finra.otc_transparency",
        execution_id="exec_abc123",
    )
    
    print("INFO Alert:")
    print(f"  Title: {info_alert.title}")
    print(f"  Severity: {info_alert.severity.value}")
    print(f"  Source: {info_alert.source}")
    print(f"  Fingerprint: {info_alert.fingerprint}")
    print()
    
    # WARNING alert - needs attention
    warning_alert = Alert(
        severity=AlertSeverity.WARNING,
        title="Data quality below threshold",
        message="Completeness score 85% is below 90% threshold",
        source="finra.quality_check",
        domain="finra.otc_transparency",
        metadata={
            "actual_completeness": 0.85,
            "threshold": 0.90,
            "week_ending": "2025-07-04",
        },
    )
    
    print("WARNING Alert:")
    print(f"  Title: {warning_alert.title}")
    print(f"  Metadata: {warning_alert.metadata}")
    print()
    
    # ERROR alert - pipeline failure
    source_error = SourceError(
        "Connection timeout after 30s",
        context=ErrorContext(
            pipeline="finra.otc_transparency.ingest_week",
            http_status=504,
        ),
    )
    
    error_alert = Alert(
        severity=AlertSeverity.ERROR,
        title="Pipeline failed",
        message="FINRA ingestion failed: Connection timeout after 30s",
        source="finra.otc_transparency.ingest_week",
        domain="finra.otc_transparency",
        error=source_error,
        execution_id="exec_def456",
    )
    
    print("ERROR Alert:")
    print(f"  Title: {error_alert.title}")
    print(f"  Error type: {type(error_alert.error).__name__}")
    print()
    
    # CRITICAL alert - requires immediate action
    critical_alert = Alert(
        severity=AlertSeverity.CRITICAL,
        title="Database connection pool exhausted",
        message="All database connections are in use. New requests will fail.",
        source="market_spine.db",
        domain="infrastructure",
    )
    
    print("CRITICAL Alert:")
    print(f"  Title: {critical_alert.title}")
    print(f"  Source: {critical_alert.source}")
    print()
    
    return [info_alert, warning_alert, error_alert, critical_alert]


# =============================================================================
# Example 2: Console Channel
# =============================================================================


def demo_console_channel():
    """Demonstrate ConsoleChannel for development."""
    print("=" * 70)
    print("EXAMPLE 2: Console Channel")
    print("=" * 70)
    print()
    
    # Create console channel
    console = ConsoleChannel(
        name="dev-console",
        min_severity=AlertSeverity.WARNING,  # Only WARNING and above
        color=True,
    )
    
    print(f"Channel: {console.name}")
    print(f"Type: {console.channel_type.value}")
    print(f"Min severity: {console.min_severity.value}")
    print(f"Enabled: {console.enabled}")
    print()
    
    # Create test alerts
    info_alert = Alert(
        severity=AlertSeverity.INFO,
        title="This should be filtered",
        message="INFO is below WARNING threshold",
        source="test",
    )
    
    warning_alert = Alert(
        severity=AlertSeverity.WARNING,
        title="Data quality degraded",
        message="Quality score dropped to 85%",
        source="quality_monitor",
        domain="finra",
    )
    
    # Check filtering
    print(f"Should send INFO? {console.should_send(info_alert)}")
    print(f"Should send WARNING? {console.should_send(warning_alert)}")
    print()
    
    # Send the warning alert
    print("Sending WARNING alert:")
    result = console.send(warning_alert)
    print(f"Delivery result: success={result.success}")
    print()


# =============================================================================
# Example 3: Slack Channel (Mock)
# =============================================================================


def demo_slack_channel():
    """Demonstrate SlackChannel configuration."""
    print("=" * 70)
    print("EXAMPLE 3: Slack Channel Configuration")
    print("=" * 70)
    print()
    
    # Create Slack channel (won't actually send - just configuration)
    slack = SlackChannel(
        name="ops-alerts",
        webhook_url="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXX",
        channel="#data-ops",
        username="Spine Bot",
        icon_emoji=":chart_with_upwards_trend:",
        min_severity=AlertSeverity.ERROR,
        domains=["finra.*", "market.*"],  # Filter to specific domains
    )
    
    print(f"Slack Channel: {slack.name}")
    print(f"  Type: {slack.channel_type.value}")
    print(f"  Min severity: {slack.min_severity.value}")
    print(f"  Enabled: {slack.enabled}")
    print()
    
    # Test domain filtering
    finra_alert = Alert(
        severity=AlertSeverity.ERROR,
        title="FINRA pipeline failed",
        message="Ingestion error",
        source="finra.ingest",
        domain="finra.otc_transparency",
    )
    
    other_alert = Alert(
        severity=AlertSeverity.ERROR,
        title="Other domain alert",
        message="Different domain",
        source="other.pipeline",
        domain="other.domain",
    )
    
    print(f"Should send FINRA alert? {slack.should_send(finra_alert)}")
    print(f"Should send other domain alert? {slack.should_send(other_alert)}")
    print()
    
    # Show payload structure (without actually sending)
    print("Slack message payload structure:")
    payload = slack._build_payload(finra_alert)
    print(f"  Username: {payload.get('username')}")
    print(f"  Attachments: {len(payload.get('attachments', []))} attachment(s)")
    if payload.get("attachments"):
        att = payload["attachments"][0]
        print(f"    Title: {att.get('title', '')[:50]}...")
        print(f"    Color: {att.get('color')}")
        print(f"    Fields: {len(att.get('fields', []))} field(s)")
    print()


# =============================================================================
# Example 4: Alert Registry
# =============================================================================


def demo_alert_registry():
    """Demonstrate AlertRegistry for managing channels."""
    print("=" * 70)
    print("EXAMPLE 4: Alert Registry")
    print("=" * 70)
    print()
    
    # Create a local registry (not the global one)
    registry = AlertRegistry()
    
    # Register multiple channels
    console = ConsoleChannel(
        name="console-all",
        min_severity=AlertSeverity.INFO,
    )
    
    console_errors = ConsoleChannel(
        name="console-errors",
        min_severity=AlertSeverity.ERROR,
    )
    
    registry.register(console)
    registry.register(console_errors)
    
    print("Registered channels:")
    for name in registry.list_channels():
        channel = registry.get(name)
        if channel:
            print(f"  - {name}: {channel.channel_type.value}, min={channel.min_severity.value}")
    print()
    
    # Send to all channels
    alert = Alert(
        severity=AlertSeverity.ERROR,
        title="Test broadcast",
        message="This goes to all matching channels",
        source="test",
    )
    
    print("Broadcasting ERROR alert to all channels:")
    results = registry.send_to_all(alert)
    
    print()
    print(f"Delivery results: {len(results)} channel(s)")
    for result in results:
        print(f"  - {result.channel_name}: success={result.success}")
    print()


# =============================================================================
# Example 5: Custom Alert Channel
# =============================================================================


class TeamsChannel(BaseChannel):
    """
    Custom Microsoft Teams channel implementation.
    
    Demonstrates how to create custom channels.
    """
    
    def __init__(
        self,
        name: str,
        webhook_url: str,
        *,
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        **kwargs,
    ):
        super().__init__(name, ChannelType.WEBHOOK, min_severity=min_severity, **kwargs)
        self._webhook_url = webhook_url
    
    def _build_card(self, alert: Alert) -> dict:
        """Build Teams adaptive card."""
        color_map = {
            AlertSeverity.INFO: "0078D4",
            AlertSeverity.WARNING: "FF8C00", 
            AlertSeverity.ERROR: "D13438",
            AlertSeverity.CRITICAL: "8B0000",
        }
        
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color_map.get(alert.severity, "808080"),
            "summary": alert.title,
            "sections": [{
                "activityTitle": f"[{alert.severity.value}] {alert.title}",
                "facts": [
                    {"name": "Source", "value": alert.source},
                    {"name": "Domain", "value": alert.domain or "N/A"},
                ],
                "text": alert.message,
            }],
        }
    
    def send(self, alert: Alert) -> DeliveryResult:
        """Send alert to Teams (mock implementation)."""
        # In real implementation: post to self._webhook_url
        card = self._build_card(alert)
        
        print(f"[TEAMS] Would send to {self._webhook_url[:30]}...")
        print(f"  Card color: #{card['themeColor']}")
        print(f"  Summary: {card['summary']}")
        
        return DeliveryResult.ok(self._name, "Mock delivery successful")


def demo_custom_channel():
    """Demonstrate creating custom alert channels."""
    print("=" * 70)
    print("EXAMPLE 5: Custom Alert Channel (Teams)")
    print("=" * 70)
    print()
    
    teams = TeamsChannel(
        name="teams-data-ops",
        webhook_url="https://outlook.office.com/webhook/...",
        min_severity=AlertSeverity.WARNING,
    )
    
    print(f"Custom channel: {teams.name}")
    print(f"Type: {teams.channel_type.value}")
    print()
    
    alert = Alert(
        severity=AlertSeverity.ERROR,
        title="Daily batch failed",
        message="The daily ETL batch failed at step 3",
        source="etl.daily_batch",
        domain="etl",
    )
    
    result = teams.send(alert)
    print(f"\nResult: success={result.success}, message={result.message}")
    print()


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    # Windows console encoding fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    alerts = demo_alert_creation()
    print()
    demo_console_channel()
    print()
    demo_slack_channel()
    print()
    demo_alert_registry()
    print()
    demo_custom_channel()
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("Key spine-core alerting framework patterns:")
    print("  1. Alert: Structured alert with severity, title, message, metadata")
    print("  2. AlertSeverity: INFO < WARNING < ERROR < CRITICAL")
    print("  3. ConsoleChannel: Print to console for development")
    print("  4. SlackChannel: Slack webhook integration")
    print("  5. AlertRegistry: Manage multiple channels, broadcast alerts")
    print("  6. Custom channels: Extend BaseChannel for Teams, PagerDuty, etc.")
    print()
