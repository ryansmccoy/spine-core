"""Tests for spine.framework.alerts module."""

import pytest
from unittest.mock import Mock, patch

from spine.core.errors import SourceError
from spine.framework.alerts.protocol import (
    Alert,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
    AlertChannel,
    ConsoleChannel,
)


class TestAlertSeverity:
    """Test AlertSeverity enum."""

    def test_severity_ordering(self):
        """Severity levels are ordered correctly."""
        assert AlertSeverity.WARNING > AlertSeverity.INFO
        assert AlertSeverity.ERROR > AlertSeverity.WARNING
        assert AlertSeverity.CRITICAL > AlertSeverity.ERROR

    def test_severity_comparison(self):
        """Severity comparison operators work."""
        assert AlertSeverity.ERROR >= AlertSeverity.WARNING
        assert AlertSeverity.WARNING >= AlertSeverity.INFO
        assert not (AlertSeverity.INFO > AlertSeverity.ERROR)


class TestAlert:
    """Test Alert dataclass."""

    def test_create_minimal_alert(self):
        """Create alert with required fields."""
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Something went wrong",
            source="test_pipeline",
        )
        assert alert.severity == AlertSeverity.ERROR
        assert alert.title == "Test Alert"
        assert alert.source == "test_pipeline"

    def test_create_alert_with_context(self):
        """Create alert with additional context."""
        alert = Alert(
            severity=AlertSeverity.WARNING,
            title="Data Quality Issue",
            message="10% of records failed validation",
            source="validation_pipeline",
            domain="finra.otc_transparency",
            execution_id="exec_123",
            run_id="run_456",
            metadata={"failed_count": 100, "total_count": 1000},
        )
        assert alert.domain == "finra.otc_transparency"
        assert alert.execution_id == "exec_123"
        assert alert.metadata["failed_count"] == 100

    def test_create_alert_with_error(self):
        """Create alert from error."""
        error = SourceError("API timeout")
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Source Failed",
            message="Failed to fetch data from API",
            source="api_source",
            error=error,
        )
        assert alert.error == error

    def test_fingerprint_auto_generated(self):
        """Fingerprint is auto-generated from key fields."""
        alert1 = Alert(
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Message 1",
            source="test_pipeline",
        )
        alert2 = Alert(
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Message 2",  # Different message
            source="test_pipeline",
        )
        # Same fingerprint (severity + source + title)
        assert alert1.fingerprint == alert2.fingerprint

    def test_fingerprint_includes_domain(self):
        """Fingerprint includes domain if provided."""
        alert1 = Alert(
            severity=AlertSeverity.ERROR,
            title="Test",
            message="msg",
            source="src",
            domain="domain1",
        )
        alert2 = Alert(
            severity=AlertSeverity.ERROR,
            title="Test",
            message="msg",
            source="src",
            domain="domain2",
        )
        assert alert1.fingerprint != alert2.fingerprint

    def test_to_dict(self):
        """Convert alert to dictionary."""
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test_source",
            domain="test_domain",
            metadata={"key": "value"},
        )
        d = alert.to_dict()
        
        assert d["severity"] == "ERROR"
        assert d["title"] == "Test Alert"
        assert d["message"] == "Test message"
        assert d["source"] == "test_source"
        assert d["domain"] == "test_domain"
        assert d["metadata"]["key"] == "value"


class TestDeliveryResult:
    """Test DeliveryResult dataclass."""

    def test_create_success_result(self):
        """Create successful delivery result."""
        result = DeliveryResult.ok("slack_channel", "Sent to Slack")
        assert result.success is True
        assert result.channel_name == "slack_channel"
        assert result.message == "Sent to Slack"

    def test_create_failure_result(self):
        """Create failed delivery result."""
        error = Exception("Network timeout")
        result = DeliveryResult(
            channel_name="email_channel",
            success=False,
            error=error,
        )
        assert result.success is False
        assert result.error == error


class TestConsoleChannel:
    """Test ConsoleChannel implementation."""

    def test_create_console_channel(self):
        """Create console channel."""
        channel = ConsoleChannel(name="console")
        assert channel.name == "console"
        assert channel.channel_type == ChannelType.CONSOLE

    def test_send_to_console(self, capsys):
        """Send alert to console channel."""
        channel = ConsoleChannel(name="console")
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            source="test",
        )
        
        result = channel.send(alert)
        
        assert result.success is True
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert "Test Alert" in captured.out
        assert "Test message" in captured.out

    def test_console_respects_min_severity(self, capsys):
        """Console channel filters by minimum severity via should_send."""
        channel = ConsoleChannel(
            name="console",
            min_severity=AlertSeverity.ERROR,
        )
        
        # should_send filters INFO alert
        info_alert = Alert(
            severity=AlertSeverity.INFO,
            title="Info",
            message="Info message",
            source="test",
        )
        assert channel.should_send(info_alert) is False
        
        # should_send allows ERROR alert
        error_alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Error",
            message="Error message",
            source="test",
        )
        assert channel.should_send(error_alert) is True
        
        # Actually sending bypasses should_send (caller's responsibility)
        channel.send(error_alert)
        captured = capsys.readouterr()
        assert "Error" in captured.out


class TestAlertChannelProtocol:
    """Test AlertChannel protocol."""

    def test_custom_channel_using_base_class(self):
        """Create custom channel by extending BaseChannel."""
        from spine.framework.alerts.protocol import BaseChannel
        
        class MockChannel(BaseChannel):
            def __init__(self, name: str):
                super().__init__(name, ChannelType.WEBHOOK, min_severity=AlertSeverity.INFO)
                self.sent_alerts = []
            
            def send(self, alert: Alert) -> DeliveryResult:
                if self.should_send(alert):
                    self.sent_alerts.append(alert)
                    return DeliveryResult.ok(self.name, "Sent")
                return DeliveryResult.ok(self.name, "Filtered")
        
        channel = MockChannel("mock_channel")
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test",
            message="Test",
            source="test",
        )
        
        result = channel.send(alert)
        
        assert result.success is True
        assert len(channel.sent_alerts) == 1
