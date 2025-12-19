"""Tests for framework/db.py (0% → ~100%) and framework/alerts/protocol.py (47% → ~75%)."""
from __future__ import annotations

import pytest

# =============================================================================
# framework/db.py tests
# =============================================================================


class TestConnectionProvider:
    """Test db module connection provider functions."""

    def setup_method(self):
        from spine.framework.db import clear_connection_provider

        clear_connection_provider()

    def teardown_method(self):
        from spine.framework.db import clear_connection_provider

        clear_connection_provider()

    def test_no_provider_raises(self):
        from spine.framework.db import get_connection

        with pytest.raises(RuntimeError, match="No connection provider configured"):
            get_connection()

    def test_set_and_get_provider(self):
        from spine.framework.db import get_connection, set_connection_provider

        class FakeConn:
            def execute(self, sql, params=()):
                return None

            def executemany(self, sql, params):
                return None

            def commit(self):
                pass

        conn = FakeConn()
        set_connection_provider(lambda: conn)
        result = get_connection()
        assert result is conn

    def test_clear_provider(self):
        from spine.framework.db import clear_connection_provider, get_connection, set_connection_provider

        set_connection_provider(lambda: None)
        clear_connection_provider()
        with pytest.raises(RuntimeError):
            get_connection()

    def test_connection_protocol_check(self):
        from spine.framework.db import Connection

        class GoodConn:
            def execute(self, sql, params=()):
                return None

            def executemany(self, sql, params):
                return None

            def fetchone(self):
                return None

            def fetchall(self):
                return []

            def commit(self):
                pass

            def rollback(self):
                pass

        assert isinstance(GoodConn(), Connection)


# =============================================================================
# framework/alerts/protocol.py tests
# =============================================================================


class TestAlertSeverity:
    """Test AlertSeverity ordering."""

    def test_severity_ordering(self):
        from spine.framework.alerts.protocol import AlertSeverity

        assert AlertSeverity.INFO < AlertSeverity.WARNING
        assert AlertSeverity.WARNING < AlertSeverity.ERROR
        assert AlertSeverity.ERROR < AlertSeverity.CRITICAL
        assert AlertSeverity.CRITICAL >= AlertSeverity.ERROR
        assert AlertSeverity.ERROR <= AlertSeverity.CRITICAL
        assert AlertSeverity.CRITICAL > AlertSeverity.WARNING

    def test_severity_equality(self):
        from spine.framework.alerts.protocol import AlertSeverity

        assert AlertSeverity.INFO <= AlertSeverity.INFO
        assert AlertSeverity.INFO >= AlertSeverity.INFO


class TestAlert:
    """Test Alert dataclass."""

    def test_auto_fingerprint(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity

        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test",
            message="msg",
            source="src",
            domain="dom",
        )
        assert alert.fingerprint == "ERROR|src|Test|dom"

    def test_fingerprint_no_domain(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity

        alert = Alert(
            severity=AlertSeverity.WARNING,
            title="T",
            message="m",
            source="s",
        )
        assert alert.fingerprint == "WARNING|s|T"

    def test_custom_fingerprint(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity

        alert = Alert(
            severity=AlertSeverity.INFO,
            title="T",
            message="m",
            source="s",
            fingerprint="custom",
        )
        assert alert.fingerprint == "custom"

    def test_to_dict(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity

        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Fail",
            message="Pipeline failed",
            source="ingest",
            domain="finra",
            execution_id="e1",
            run_id="r1",
            metadata={"key": "val"},
        )
        d = alert.to_dict()
        assert d["severity"] == "ERROR"
        assert d["title"] == "Fail"
        assert d["domain"] == "finra"
        assert d["execution_id"] == "e1"
        assert d["run_id"] == "r1"
        assert d["metadata"] == {"key": "val"}

    def test_to_dict_minimal(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity

        alert = Alert(
            severity=AlertSeverity.INFO,
            title="T",
            message="m",
            source="s",
        )
        d = alert.to_dict()
        assert "domain" not in d
        assert "execution_id" not in d

    def test_to_dict_with_error(self):
        from spine.core.errors import SpineError
        from spine.framework.alerts.protocol import Alert, AlertSeverity

        err = SpineError("test error")
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="T",
            message="m",
            source="s",
            error=err,
        )
        d = alert.to_dict()
        assert "error" in d


class TestDeliveryResult:
    """Test DeliveryResult factories."""

    def test_ok(self):
        from spine.framework.alerts.protocol import DeliveryResult

        r = DeliveryResult.ok("ch1", message="sent")
        assert r.success
        assert r.channel_name == "ch1"
        assert r.message == "sent"

    def test_fail(self):
        from spine.framework.alerts.protocol import DeliveryResult

        err = ValueError("bad")
        r = DeliveryResult.fail("ch1", error=err, attempt=2)
        assert not r.success
        assert r.error is err
        assert r.attempt == 2
        assert r.message == "bad"


class TestConsoleChannel:
    """Test ConsoleChannel."""

    def test_send(self, capsys):
        from spine.framework.alerts.protocol import Alert, AlertSeverity, ConsoleChannel

        ch = ConsoleChannel("test", min_severity=AlertSeverity.INFO, color=False)
        alert = Alert(
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Something happened",
            source="test",
            domain="test.domain",
        )
        result = ch.send(alert)
        assert result.success
        captured = capsys.readouterr()
        assert "Test Alert" in captured.out
        assert "test.domain" in captured.out

    def test_send_with_color(self, capsys):
        from spine.framework.alerts.protocol import Alert, AlertSeverity, ConsoleChannel

        ch = ConsoleChannel("test", color=True)
        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            title="Critical",
            message="msg",
            source="src",
        )
        result = ch.send(alert)
        assert result.success

    def test_properties(self):
        from spine.framework.alerts.protocol import AlertSeverity, ChannelType, ConsoleChannel

        ch = ConsoleChannel("test", min_severity=AlertSeverity.WARNING)
        assert ch.name == "test"
        assert ch.channel_type == ChannelType.CONSOLE
        assert ch.min_severity == AlertSeverity.WARNING
        assert ch.enabled


class TestBaseChannel:
    """Test BaseChannel common behavior."""

    def test_should_send_disabled(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity, ConsoleChannel

        ch = ConsoleChannel("test", enabled=False)
        alert = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s")
        assert not ch.should_send(alert)

    def test_should_send_severity_filter(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity, ConsoleChannel

        ch = ConsoleChannel("test", min_severity=AlertSeverity.ERROR)
        info_alert = Alert(severity=AlertSeverity.INFO, title="T", message="m", source="s")
        error_alert = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s")
        assert not ch.should_send(info_alert)
        assert ch.should_send(error_alert)

    def test_should_send_domain_filter_exact(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity, ConsoleChannel

        ch = ConsoleChannel("test", min_severity=AlertSeverity.INFO, domains=["finra"])
        yes = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s", domain="finra")
        no = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s", domain="sec")
        assert ch.should_send(yes)
        assert not ch.should_send(no)

    def test_should_send_domain_filter_wildcard(self):
        from spine.framework.alerts.protocol import Alert, AlertSeverity, ConsoleChannel

        ch = ConsoleChannel("test", min_severity=AlertSeverity.INFO, domains=["finra.*"])
        yes = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s", domain="finra.otc")
        no = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s", domain="sec.filing")
        assert ch.should_send(yes)
        assert not ch.should_send(no)

    def test_enable_disable(self):
        from spine.framework.alerts.protocol import ConsoleChannel

        ch = ConsoleChannel("test")
        assert ch.enabled
        ch.disable()
        assert not ch.enabled
        ch.enable()
        assert ch.enabled


class TestAlertRegistry:
    """Test AlertRegistry."""

    def test_register_and_get(self):
        from spine.framework.alerts.protocol import AlertRegistry, ConsoleChannel

        reg = AlertRegistry()
        ch = ConsoleChannel("test")
        reg.register(ch)
        assert reg.get("test") is ch

    def test_unregister(self):
        from spine.framework.alerts.protocol import AlertRegistry, ConsoleChannel

        reg = AlertRegistry()
        reg.register(ConsoleChannel("test"))
        reg.unregister("test")
        assert reg.get("test") is None
        # Unregister nonexistent is no-op
        reg.unregister("test")

    def test_list_channels(self):
        from spine.framework.alerts.protocol import AlertRegistry, ConsoleChannel

        reg = AlertRegistry()
        reg.register(ConsoleChannel("b"))
        reg.register(ConsoleChannel("a"))
        assert reg.list_channels() == ["a", "b"]

    def test_list_by_type(self):
        from spine.framework.alerts.protocol import AlertRegistry, ChannelType, ConsoleChannel

        reg = AlertRegistry()
        reg.register(ConsoleChannel("c1"))
        reg.register(ConsoleChannel("c2"))
        assert len(reg.list_by_type(ChannelType.CONSOLE)) == 2
        assert len(reg.list_by_type(ChannelType.SLACK)) == 0

    def test_send_to_specific_channel(self, capsys):
        from spine.framework.alerts.protocol import Alert, AlertRegistry, AlertSeverity, ConsoleChannel

        reg = AlertRegistry()
        reg.register(ConsoleChannel("out", min_severity=AlertSeverity.INFO, color=False))
        alert = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s")
        result = reg.send(alert, "out")
        assert result.success

    def test_send_to_missing_channel(self):
        from spine.framework.alerts.protocol import Alert, AlertRegistry, AlertSeverity

        reg = AlertRegistry()
        alert = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s")
        result = reg.send(alert, "missing")
        assert not result.success

    def test_send_filtered(self, capsys):
        from spine.framework.alerts.protocol import Alert, AlertRegistry, AlertSeverity, ConsoleChannel

        reg = AlertRegistry()
        reg.register(ConsoleChannel("high", min_severity=AlertSeverity.CRITICAL, color=False))
        alert = Alert(severity=AlertSeverity.INFO, title="T", message="m", source="s")
        result = reg.send(alert, "high")
        assert result.success
        assert "Filtered" in (result.message or "")

    def test_send_to_all(self, capsys):
        from spine.framework.alerts.protocol import Alert, AlertRegistry, AlertSeverity, ConsoleChannel

        reg = AlertRegistry()
        reg.register(ConsoleChannel("c1", min_severity=AlertSeverity.INFO, color=False))
        reg.register(ConsoleChannel("c2", min_severity=AlertSeverity.INFO, color=False))
        alert = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s")
        results = reg.send_to_all(alert)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_send_to_type(self, capsys):
        from spine.framework.alerts.protocol import (
            Alert,
            AlertRegistry,
            AlertSeverity,
            ChannelType,
            ConsoleChannel,
        )

        reg = AlertRegistry()
        reg.register(ConsoleChannel("c1", min_severity=AlertSeverity.INFO, color=False))
        alert = Alert(severity=AlertSeverity.ERROR, title="T", message="m", source="s")
        results = reg.send_to_type(alert, ChannelType.CONSOLE)
        assert len(results) == 1


class TestSendAlertConvenience:
    """Test the send_alert convenience function."""

    def test_send_alert(self, capsys):
        from spine.framework.alerts.protocol import (
            AlertSeverity,
            ConsoleChannel,
            alert_registry,
            send_alert,
        )

        # Register a console channel for testing
        alert_registry.register(ConsoleChannel("test_global", min_severity=AlertSeverity.INFO, color=False))
        try:
            results = send_alert(
                AlertSeverity.ERROR,
                "Test",
                "Test message",
                source="test",
            )
            assert len(results) >= 1
        finally:
            alert_registry.unregister("test_global")
