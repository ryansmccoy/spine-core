"""
Tests for spine.core.idempotency module.

Tests cover:
- IdempotencyLevel enum
- IdempotencyHelper methods
- LogicalKey construction and usage
"""

import pytest
from unittest.mock import MagicMock

from spine.core.idempotency import (
    IdempotencyLevel,
    IdempotencyHelper,
    LogicalKey,
)


class TestIdempotencyLevel:
    """Tests for IdempotencyLevel enum."""

    def test_level_values(self):
        """Test that levels have correct integer values."""
        assert IdempotencyLevel.L1_APPEND == 1
        assert IdempotencyLevel.L2_INPUT == 2
        assert IdempotencyLevel.L3_STATE == 3

    def test_level_ordering(self):
        """Test that levels can be compared."""
        assert IdempotencyLevel.L1_APPEND < IdempotencyLevel.L2_INPUT
        assert IdempotencyLevel.L2_INPUT < IdempotencyLevel.L3_STATE


class TestLogicalKey:
    """Tests for LogicalKey class."""

    def test_logical_key_creation(self):
        """Test creating a LogicalKey."""
        key = LogicalKey(week_ending="2025-12-26", tier="NMS_TIER_1")
        
        assert key is not None

    def test_where_clause(self):
        """Test SQL WHERE clause generation."""
        key = LogicalKey(week_ending="2025-12-26", tier="NMS_TIER_1")
        
        where = key.where_clause()
        
        assert "week_ending = ?" in where
        assert "tier = ?" in where
        assert " AND " in where

    def test_where_clause_single_part(self):
        """Test WHERE clause with single key part."""
        key = LogicalKey(id="123")
        
        where = key.where_clause()
        
        assert where == "id = ?"

    def test_values(self):
        """Test parameter values extraction."""
        key = LogicalKey(week_ending="2025-12-26", tier="NMS_TIER_1")
        
        values = key.values()
        
        assert isinstance(values, tuple)
        assert "2025-12-26" in values
        assert "NMS_TIER_1" in values

    def test_values_order_matches_where(self):
        """Test that values order matches WHERE clause order."""
        # Note: dict ordering is preserved in Python 3.7+
        key = LogicalKey(a="val_a", b="val_b", c="val_c")
        
        where = key.where_clause()
        values = key.values()
        
        # Values should be in same order as they appear in WHERE
        assert values == ("val_a", "val_b", "val_c")

    def test_as_dict(self):
        """Test dictionary representation."""
        key = LogicalKey(week_ending="2025-12-26", tier="NMS_TIER_1")
        
        d = key.as_dict()
        
        assert d == {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}

    def test_repr(self):
        """Test string representation."""
        key = LogicalKey(week_ending="2025-12-26")
        
        repr_str = repr(key)
        
        assert "LogicalKey" in repr_str
        assert "week_ending" in repr_str
        assert "2025-12-26" in repr_str


class TestIdempotencyHelper:
    """Tests for IdempotencyHelper class."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock database connection."""
        conn = MagicMock()
        return conn

    @pytest.fixture
    def helper(self, mock_conn):
        """Create an IdempotencyHelper with mock connection."""
        return IdempotencyHelper(mock_conn)

    def test_hash_exists_true(self, helper, mock_conn):
        """Test hash_exists returns True when hash found."""
        mock_conn.execute.return_value.fetchone.return_value = (1,)
        
        result = helper.hash_exists("otc_raw", "record_hash", "abc123")
        
        assert result is True
        mock_conn.execute.assert_called_once()

    def test_hash_exists_false(self, helper, mock_conn):
        """Test hash_exists returns False when hash not found."""
        mock_conn.execute.return_value.fetchone.return_value = None
        
        result = helper.hash_exists("otc_raw", "record_hash", "missing")
        
        assert result is False

    def test_hash_exists_query_format(self, helper, mock_conn):
        """Test hash_exists uses correct SQL."""
        mock_conn.execute.return_value.fetchone.return_value = None
        
        helper.hash_exists("my_table", "my_hash_col", "hash_value")
        
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        assert "my_table" in sql
        assert "my_hash_col" in sql
        assert "LIMIT 1" in sql
        assert params == ("hash_value",)

    def test_get_existing_hashes(self, helper, mock_conn):
        """Test getting all existing hashes."""
        mock_conn.execute.return_value.fetchall.return_value = [
            ("hash1",), ("hash2",), ("hash3",)
        ]
        
        result = helper.get_existing_hashes("table", "hash_col")
        
        assert result == {"hash1", "hash2", "hash3"}

    def test_get_existing_hashes_empty(self, helper, mock_conn):
        """Test getting hashes from empty table."""
        mock_conn.execute.return_value.fetchall.return_value = []
        
        result = helper.get_existing_hashes("table", "hash_col")
        
        assert result == set()

    def test_delete_for_key(self, helper, mock_conn):
        """Test delete_for_key method."""
        mock_conn.execute.return_value.rowcount = 5
        
        key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
        result = helper.delete_for_key("otc_data", key)
        
        assert result == 5

    def test_delete_for_key_query_format(self, helper, mock_conn):
        """Test delete_for_key uses correct SQL."""
        mock_conn.execute.return_value.rowcount = 0
        
        helper.delete_for_key("my_table", {"col1": "val1", "col2": "val2"})
        
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        assert "DELETE FROM my_table WHERE" in sql
        assert "col1 = ?" in sql
        assert "col2 = ?" in sql
        assert " AND " in sql
        assert params == ("val1", "val2")

    def test_delete_and_count_alias(self, helper, mock_conn):
        """Test that delete_and_count is an alias for delete_for_key."""
        mock_conn.execute.return_value.rowcount = 3
        
        result = helper.delete_and_count("table", {"key": "value"})
        
        assert result == 3
