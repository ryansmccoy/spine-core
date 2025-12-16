"""Mock FeedSpine API for spine-core examples.

Provides realistic FeedSpine behavior without requiring
the feedspine package or external feed connections.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import MockAPIBase, MockResponse
from .fixtures import MOCK_FEED_RECORDS


class MockFeedSpine(MockAPIBase):
    """Mock FeedSpine that mimics real feed collection behavior.
    
    Features:
    - Simulated feed collection with deduplication
    - Tracks collected record IDs across calls
    - Realistic collection statistics
    
    Example:
        >>> api = MockFeedSpine()
        >>> result = await api.collect("sec_filings")
        >>> result.data["new"]  # First call gets all records
        3
        >>> result = await api.collect("sec_filings")
        >>> result.data["duplicates"]  # Second call sees duplicates
        3
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collected_ids: dict[str, set[str]] = {}
    
    async def collect(self, feed_name: str) -> MockResponse:
        """Collect records from a mock feed.
        
        Simulates FeedSpine collection with deduplication:
        - First collection returns all records as new
        - Subsequent collections show duplicates
        
        Args:
            feed_name: Name of feed to collect from
            
        Returns:
            MockResponse with collection statistics
        """
        await self._simulate_latency()
        
        if self._should_fail():
            return MockResponse(data=None, success=False, error="Feed unavailable")
        
        # Get mock records for this feed
        records = MOCK_FEED_RECORDS.get(feed_name, [])
        
        # Initialize tracking set for this feed
        if feed_name not in self._collected_ids:
            self._collected_ids[feed_name] = set()
        
        collected = self._collected_ids[feed_name]
        new_records = []
        duplicates = 0
        
        for record in records:
            record_id = record.get("id", str(hash(str(record))))
            if record_id in collected:
                duplicates += 1
            else:
                collected.add(record_id)
                new_records.append(record)
        
        return MockResponse(
            data={
                "feed_name": feed_name,
                "total_processed": len(records),
                "new": len(new_records),
                "duplicates": duplicates,
                "records": new_records,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
            success=True,
        )
    
    async def collect_all(self) -> MockResponse:
        """Collect from all available feeds.
        
        Returns:
            MockResponse with aggregated statistics
        """
        await self._simulate_latency()
        
        total_processed = 0
        total_new = 0
        total_duplicates = 0
        feed_results = {}
        
        for feed_name in MOCK_FEED_RECORDS.keys():
            result = await self.collect(feed_name)
            if result.success:
                data = result.data
                total_processed += data["total_processed"]
                total_new += data["new"]
                total_duplicates += data["duplicates"]
                feed_results[feed_name] = {
                    "processed": data["total_processed"],
                    "new": data["new"],
                    "duplicates": data["duplicates"],
                }
        
        return MockResponse(
            data={
                "total_processed": total_processed,
                "total_new": total_new,
                "total_duplicates": total_duplicates,
                "feeds": feed_results,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
            success=True,
        )
    
    async def get_records(
        self, 
        feed_name: str, 
        limit: int = 100,
        since: datetime | None = None,
    ) -> MockResponse:
        """Get records from a feed.
        
        Args:
            feed_name: Name of feed
            limit: Maximum records to return
            since: Only return records after this timestamp
            
        Returns:
            MockResponse with list of records
        """
        await self._simulate_latency()
        
        records = MOCK_FEED_RECORDS.get(feed_name, [])
        return MockResponse(data=records[:limit], success=True)
    
    async def list_feeds(self) -> MockResponse:
        """List all available feeds.
        
        Returns:
            MockResponse with feed names and stats
        """
        await self._simulate_latency()
        
        feeds = []
        for feed_name, records in MOCK_FEED_RECORDS.items():
            feeds.append({
                "name": feed_name,
                "record_count": len(records),
                "last_collected": self._collected_ids.get(feed_name) is not None,
            })
        
        return MockResponse(data=feeds, success=True)
    
    def reset(self) -> None:
        """Reset all state including collected IDs."""
        super().reset()
        self._collected_ids.clear()
