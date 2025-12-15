"""
Tests for spine.core.hashing module.

Tests cover:
- Deterministic hash computation
- Record hash generation
- Hash length options
- Content vs natural key hashing
"""

import pytest

from spine.core.hashing import (
    compute_hash,
    compute_record_hash,
)


class TestComputeHash:
    """Tests for compute_hash function."""

    def test_hash_single_value(self):
        """Test hashing a single value."""
        result = compute_hash("test_value")
        
        assert isinstance(result, str)
        assert len(result) == 32  # Default length

    def test_hash_multiple_values(self):
        """Test hashing multiple values."""
        result = compute_hash("value1", "value2", "value3")
        
        assert isinstance(result, str)
        assert len(result) == 32

    def test_hash_deterministic(self):
        """Test that same inputs produce same hash."""
        hash1 = compute_hash("a", "b", "c")
        hash2 = compute_hash("a", "b", "c")
        
        assert hash1 == hash2

    def test_hash_different_inputs_different_hashes(self):
        """Test that different inputs produce different hashes."""
        hash1 = compute_hash("a", "b", "c")
        hash2 = compute_hash("a", "b", "d")  # Changed last value
        
        assert hash1 != hash2

    def test_hash_order_matters(self):
        """Test that value order affects the hash."""
        hash1 = compute_hash("a", "b", "c")
        hash2 = compute_hash("c", "b", "a")
        
        assert hash1 != hash2

    def test_hash_custom_length(self):
        """Test hash with custom length."""
        result = compute_hash("value", length=16)
        assert len(result) == 16
        
        result = compute_hash("value", length=64)
        assert len(result) == 64

    def test_hash_handles_integers(self):
        """Test hashing integer values."""
        result = compute_hash("date", 12345, 67890)
        
        assert isinstance(result, str)
        assert len(result) == 32

    def test_hash_handles_mixed_types(self):
        """Test hashing mixed types."""
        result = compute_hash("string", 123, 45.67, True, None)
        
        assert isinstance(result, str)
        assert len(result) == 32

    def test_hash_consistent_across_calls(self):
        """Test hash consistency across multiple calls."""
        values = ("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        
        hashes = [compute_hash(*values) for _ in range(100)]
        
        assert len(set(hashes)) == 1  # All hashes should be identical


class TestComputeRecordHash:
    """Tests for compute_record_hash function."""

    def test_natural_key_hash(self):
        """Test hash with natural key only (no volume data)."""
        result = compute_record_hash(
            week_ending="2025-12-26",
            tier="NMS_TIER_1",
            symbol="AAPL",
            mpid="NITE",
        )
        
        assert isinstance(result, str)
        assert len(result) == 32

    def test_natural_key_hash_deterministic(self):
        """Test that natural key hash is deterministic."""
        hash1 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        hash2 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        
        assert hash1 == hash2

    def test_content_hash_with_volume(self):
        """Test hash including volume data."""
        result = compute_record_hash(
            week_ending="2025-12-26",
            tier="NMS_TIER_1",
            symbol="AAPL",
            mpid="NITE",
            total_shares=1000000,
            total_trades=5000,
        )
        
        assert isinstance(result, str)
        assert len(result) == 32

    def test_content_hash_differs_from_natural_key(self):
        """Test that content hash differs from natural key hash."""
        natural_hash = compute_record_hash(
            week_ending="2025-12-26",
            tier="NMS_TIER_1",
            symbol="AAPL",
            mpid="NITE",
        )
        
        content_hash = compute_record_hash(
            week_ending="2025-12-26",
            tier="NMS_TIER_1",
            symbol="AAPL",
            mpid="NITE",
            total_shares=1000000,
            total_trades=5000,
        )
        
        assert natural_hash != content_hash

    def test_different_volumes_different_hashes(self):
        """Test that different volume data produces different hashes."""
        hash1 = compute_record_hash(
            "2025-12-26", "NMS_TIER_1", "AAPL", "NITE",
            total_shares=1000000, total_trades=5000,
        )
        
        hash2 = compute_record_hash(
            "2025-12-26", "NMS_TIER_1", "AAPL", "NITE",
            total_shares=2000000, total_trades=5000,  # Different shares
        )
        
        assert hash1 != hash2

    def test_different_keys_different_hashes(self):
        """Test that different natural keys produce different hashes."""
        hash_aapl = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        hash_msft = compute_record_hash("2025-12-26", "NMS_TIER_1", "MSFT", "NITE")
        
        assert hash_aapl != hash_msft

    def test_different_dates_different_hashes(self):
        """Test that different dates produce different hashes."""
        hash1 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        hash2 = compute_record_hash("2025-12-27", "NMS_TIER_1", "AAPL", "NITE")
        
        assert hash1 != hash2

    def test_partial_volume_uses_natural_key(self):
        """Test that partial volume data falls back to natural key hash."""
        # Only total_shares, no total_trades
        hash_partial = compute_record_hash(
            "2025-12-26", "NMS_TIER_1", "AAPL", "NITE",
            total_shares=1000000,
            total_trades=None,
        )
        
        hash_natural = compute_record_hash(
            "2025-12-26", "NMS_TIER_1", "AAPL", "NITE",
        )
        
        # With partial volume data (None), should use natural key
        assert hash_partial == hash_natural
