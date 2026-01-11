# src/market_spine/domains/otc/pipelines.py

"""OTC pipelines - Intermediate version with repository pattern + quality checks."""

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from market_spine.pipelines.base import Pipeline

from market_spine.domains.otc.parser import parse_finra_file
from market_spine.domains.otc.normalizer import normalize_records
from market_spine.domains.otc.calculations import (
    compute_symbol_summaries,
    compute_venue_shares,
)
from market_spine.domains.otc.repository import OTCRepository
from market_spine.domains.otc.quality import OTCQualityChecker


class OTCIngestPipeline(Pipeline):
    """Ingest FINRA file into otc.raw table."""

    name = "otc.ingest"
    description = "Ingest FINRA OTC file"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(params["file_path"])
        batch_id = str(uuid.uuid4())[:8]

        repo = OTCRepository()

        # Parse file
        records = list(parse_finra_file(file_path))

        # Convert to dicts for repo
        record_dicts = [
            {
                "record_hash": r.record_hash,
                "week_ending": r.week_ending,
                "tier": r.tier,
                "symbol": r.symbol,
                "issue_name": r.issue_name,
                "venue_name": r.venue_name,
                "mpid": r.mpid,
                "share_volume": r.share_volume,
                "trade_count": r.trade_count,
                "source_file": str(file_path),
            }
            for r in records
        ]

        # Insert via repository
        inserted, dupes = repo.insert_raw_batch(record_dicts, batch_id)

        return {
            "batch_id": batch_id,
            "records": len(records),
            "inserted": inserted,
            "duplicates": dupes,
        }


class OTCNormalizePipeline(Pipeline):
    """Normalize raw records into venue_volume table."""

    name = "otc.normalize"
    description = "Normalize raw OTC data"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = OTCRepository()

        # Fetch unnormalized raw records
        raw_records = repo.get_unnormalized_raw_records()

        # Normalize
        result = normalize_records(raw_records)

        # Upsert via repository
        if result.records:
            repo.upsert_venue_volume(result.records)

        return {
            "processed": result.processed,
            "accepted": result.accepted,
            "rejected": result.rejected,
        }


class OTCSummarizePipeline(Pipeline):
    """Compute symbol and venue summaries."""

    name = "otc.summarize"
    description = "Compute OTC summaries"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = OTCRepository()

        # Load venue data
        venue_data = repo.get_all_venue_volume()

        # Compute summaries
        symbols = compute_symbol_summaries(venue_data)
        venues = compute_venue_shares(venue_data)

        # Store via repository
        repo.upsert_symbol_summaries(symbols)
        repo.upsert_venue_shares(venues)

        return {
            "symbols": len(symbols),
            "venues": len(venues),
        }


class OTCQualityCheckPipeline(Pipeline):
    """Run quality checks on a week."""

    name = "otc.quality_check"
    description = "Validate data quality for a week"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        week = params.get("week_ending")

        week_date = date.fromisoformat(week) if week else date.today()

        checker = OTCQualityChecker()
        result = checker.check_week(week_date)

        return {
            "week_ending": result.week_ending.isoformat(),
            "grade": result.grade,
            "score": result.score,
            "issues": len(result.issues),
            "issue_details": [
                {"code": i.code, "message": i.message, "severity": i.severity.value}
                for i in result.issues
            ],
        }


# Register pipelines - intermediate uses class-based registry
def register_otc_pipelines(registry):
    """Register OTC pipelines with the registry."""
    registry.register(OTCIngestPipeline)
    registry.register(OTCNormalizePipeline)
    registry.register(OTCSummarizePipeline)
    registry.register(OTCQualityCheckPipeline)
