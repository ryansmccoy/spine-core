"""
FINRA OTC Transparency Pipelines - Thin orchestration over core primitives.

Each pipeline is a small orchestrator that:
1. Uses spine.core primitives (manifest, rejects, quality, rolling)
2. Calls domain-specific functions (connector, normalizer, calculations)
3. Writes results to storage

Pipelines do NOT contain business logic - that's in calculations.py.
Pipelines do NOT implement rejects/manifest/etc - that's in spine.core.

Pipeline Registration Names:
- finra.otc_transparency.ingest_week
- finra.otc_transparency.normalize_week
- finra.otc_transparency.aggregate_week
- finra.otc_transparency.compute_rolling
- finra.otc_transparency.backfill_range

IMPORTANT: Pipelines use core infrastructure tables via domain="finra_otc_transparency":
- core_manifest (not otc_week_manifest)
- core_rejects (not otc_rejects)
- core_quality (not otc_quality_checks)
"""

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

from spine.core import (
    IdempotencyHelper,
    QualityRunner,
    Reject,
    RejectSink,
    WeekEnding,
    WorkManifest,
    create_core_tables,  # Ensure tables exist
    new_batch_id,
    new_context,
)
from spine.domains.finra.otc_transparency.calculations import (
    SymbolAggregateRow,
    VenueVolumeRow,
    aggregate_to_symbol_level,
)
from spine.domains.finra.otc_transparency.connector import (
    RawOTCRecord,
    get_file_metadata,
    parse_finra_content,
    parse_finra_file,
    parse_simple_psv,
)
from spine.domains.finra.otc_transparency.normalizer import normalize_records
from spine.domains.finra.otc_transparency.schema import DOMAIN, STAGES, TABLES, Tier
from spine.domains.finra.otc_transparency.sources import (
    IngestionError,
    Payload,
    create_source,
    list_periods,
    list_sources,
    resolve_period,
    resolve_source,
)
from spine.framework.db import get_connection
from spine.framework.logging import bind_context, get_logger, log_step
from spine.framework.params import (
    ParamDef,
    PipelineSpec,
    date_format,
    enum_value,
    file_exists,
    positive_int,
)
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import register_pipeline

# Module logger
log = get_logger(__name__)


def generate_capture_id(week_ending: str, tier: str, captured_at: datetime) -> str:
    """
    Generate deterministic capture_id for a week+tier+timestamp.

    Format: finra.otc_transparency:{tier}:{week}:{timestamp_hash}
    Example: finra.otc_transparency:NMS_TIER_1:2025-12-20:a3f5b2
    """
    content = f"{tier}|{week_ending}|{captured_at.isoformat()}"
    hash_suffix = hashlib.sha256(content.encode()).hexdigest()[:6]
    return f"finra.otc_transparency:{tier}:{week_ending}:{hash_suffix}"


# =============================================================================
# INGEST PIPELINE
# =============================================================================


@register_pipeline("finra.otc_transparency.ingest_week")
class IngestWeekPipeline(Pipeline):
    """
    Ingest raw FINRA OTC transparency data for a single week.

    Supports multiple ingestion sources:
    - File: Provide file_path (tier/week_ending auto-detected from filename)
    - API: Provide tier + week_ending (uses FINRA OTC API or mock)

    Params:
        file_path: Path to PSV file (for file source)
        tier: "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
        week_ending: ISO Friday date (e.g., "2025-12-26")
        source_type: "file" or "api" (auto-detected if not specified)
        force: Re-ingest even if already done (default: False)
    """

    name = "finra.otc_transparency.ingest_week"
    description = "Ingest FINRA OTC transparency data for one week"
    spec = PipelineSpec(
        required_params={},  # All params optional - source determined by what's provided
        optional_params={
            "file_path": ParamDef(
                name="file_path",
                type=Path,
                description="Path to the FINRA OTC transparency PSV file",
                required=False,
                validator=file_exists,
                error_message="File does not exist",
            ),
            "tier": ParamDef(
                name="tier",
                type=str,
                description="Market tier (required for API, auto-detected for file)",
                required=False,
                validator=enum_value(Tier),
                error_message="Must be NMS_TIER_1, NMS_TIER_2, or OTC",
            ),
            "week_ending": ParamDef(
                name="week_ending",
                type=str,
                description="Week ending date in ISO format (required for API, auto-detected for file)",
                required=False,
                validator=date_format,
                error_message="Must be ISO date format (YYYY-MM-DD)",
            ),
            "source_type": ParamDef(
                name="source_type",
                type=str,
                description="Ingestion source: 'file' or 'api' (auto-detected if not specified)",
                required=False,
            ),
            "file_date": ParamDef(
                name="file_date",
                type=str,
                description="File publication date (auto-detected if not provided)",
                required=False,
                validator=date_format,
            ),
            "force": ParamDef(
                name="force",
                type=bool,
                description="Re-ingest even if already ingested",
                required=False,
                default=False,
            ),
            "mock_response": ParamDef(
                name="mock_response",
                type=str,
                description="Mock PSV content for API testing (offline mode)",
                required=False,
            ),
        },
        examples=[
            # File source examples
            "spine run finra.otc_transparency.ingest_week -p file_path=data/week_2025-12-05.psv",
            "spine run finra.otc_transparency.ingest_week -p file_path=data/tier1.psv -p tier=NMS_TIER_1",
            # API source examples
            "spine run finra.otc_transparency.ingest_week -p tier=NMS_TIER_1 -p week_ending=2025-12-05 -p source_type=api",
        ],
        notes=[
            "For file source: tier and week_ending can be auto-detected from filename patterns",
            "For API source: tier and week_ending are required",
            "Use force=True to re-ingest data (will delete existing data for that week/tier)",
            "Use mock_response for offline API testing",
        ],
    )

    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()

        # Ensure core tables exist
        create_core_tables(conn)

        # Parse common params
        force = self.params.get("force", False)
        file_path = self.params.get("file_path")
        tier_param = self.params.get("tier")
        week_ending_param = self.params.get("week_ending")
        source_type_param = self.params.get("source_type", "file")  # Default: file
        mock_response = self.params.get("mock_response")

        # Parse date params
        from datetime import date as date_type

        we_override = None
        fd_override = None
        if week_ending_param:
            if isinstance(week_ending_param, str):
                we_override = date_type.fromisoformat(week_ending_param)
            else:
                we_override = week_ending_param
        file_date_override = self.params.get("file_date")
        if file_date_override:
            if isinstance(file_date_override, str):
                fd_override = date_type.fromisoformat(file_date_override)
            else:
                fd_override = file_date_override

        # Create source via factory (all branching is here)
        try:
            source = create_source(
                source_type=source_type_param,
                file_path=file_path,
                tier=tier_param,
                week_ending=we_override,
                week_ending_override=we_override,
                file_date_override=fd_override,
                mock_content=mock_response,
            )
        except ValueError as e:
            raise ValueError(str(e))

        log.info("ingest.source_created", source_type=source.source_type)

        # Fetch raw content using source abstraction
        # Source returns Payload(content, metadata) - NOT parsed records
        try:
            with log_step("ingest.fetch_content", source_type=source.source_type):
                payload = source.fetch()
        except IngestionError as e:
            raise ValueError(f"Ingestion failed: {e}")

        # Parse content uniformly - all sources go through same parser
        with log_step("ingest.parse_content") as parse_timer:
            records = list(parse_finra_content(payload.content))
            parse_timer.add_metric("rows_parsed", len(records))

        metadata = payload.metadata

        # Validate or infer tier from source metadata
        if tier_param:
            tier = Tier(tier_param)
        elif metadata.tier_hint:
            tier = Tier(metadata.tier_hint)
            log.info("ingest.tier_detected", tier=tier.value, source=metadata.source_type)
        else:
            raise ValueError(
                f"Tier not specified and could not be detected from source: {metadata.source_name}"
            )

        # Use week_ending from metadata
        week = WeekEnding(metadata.week_ending)

        # Log the source resolution for observability
        log.info(
            "ingest.source_resolved",
            file_date=str(metadata.file_date),
            week_ending=str(week),
            source_type=metadata.source_type,
            source_name=metadata.source_name,
            tier=tier.value,
        )

        # Bind context for all logs in this pipeline
        bind_context(domain=DOMAIN, step="ingest", week_ending=str(week), tier=tier.value)
        log.debug("ingest.params", force=force)

        log.info("ingest.fetched", rows=len(records))

        # Create execution context
        ctx = new_context(batch_id=self.params.get("batch_id") or new_batch_id("ingest"))

        # Setup primitives (use domain="finra_otc_transparency" for core tables)
        manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
        idem = IdempotencyHelper(conn)
        key = {"week_ending": str(week), "tier": tier.value}

        # Check idempotency
        if not force and manifest.is_at_least(key, "INGESTED"):
            log.info("ingest.skipped", reason="already_ingested")
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=started,
                completed_at=datetime.now(),
                metrics={"skipped": True, "reason": "Already ingested"},
            )

        # Set capture time and identity (Clock 3)
        captured_at = datetime.now(UTC)
        capture_id = generate_capture_id(str(week), tier.value, captured_at)
        captured_at_iso = captured_at.isoformat()
        ingested_at_iso = captured_at_iso  # Same timestamp for batch

        bind_context(capture_id=capture_id)
        log.debug("ingest.capture_id_generated", capture_id=capture_id)

        # Get existing hashes for dedup WITHIN THIS CAPTURE
        with log_step("ingest.check_existing", level="debug"):
            existing_in_capture = set()
            existing_rows = conn.execute(
                f"""
                SELECT record_hash FROM {TABLES["raw"]}
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, capture_id),
            ).fetchall()
            for row in existing_rows:
                existing_in_capture.add(row["record_hash"])

        # Prepare batch insert data (filter out existing)
        with log_step("ingest.prepare_batch", level="debug") as prep_timer:
            batch_data = []
            for r in records:
                if r.record_hash not in existing_in_capture:
                    batch_data.append(
                        (
                            str(week),  # Use param week_ending, not r.week_ending from file
                            tier.value,
                            r.symbol,
                            r.mpid,
                            r.total_shares,
                            r.total_trades,
                            r.issue_name,
                            r.venue_name,
                            metadata.source_name,  # Source identifier (file path or API URL)
                            str(r.source_last_update_date) if r.source_last_update_date else None,
                            captured_at_iso,
                            capture_id,
                            r.record_hash,
                            ctx.execution_id,
                            ctx.batch_id,
                            ingested_at_iso,
                        )
                    )
            prep_timer.add_metric("rows_to_insert", len(batch_data))

        # Bulk insert with optimized SQLite settings
        if batch_data:
            with log_step("ingest.bulk_insert", table=TABLES["raw"], rows=len(batch_data)):
                conn.execute("PRAGMA synchronous = OFF")
                conn.execute("PRAGMA journal_mode = MEMORY")

                conn.executemany(
                    f"""
                    INSERT INTO {TABLES["raw"]} (
                        week_ending, tier, symbol, mpid, 
                        total_shares, total_trades,
                        issue_name, venue_name, source_file,
                        source_last_update_date,
                        captured_at, capture_id,
                        record_hash, execution_id, batch_id, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    batch_data,
                )

                conn.execute("PRAGMA synchronous = NORMAL")

        inserted = len(batch_data)
        conn.commit()

        # Update manifest
        manifest.advance_to(
            key,
            "INGESTED",
            row_count=len(records),
            execution_id=ctx.execution_id,
            batch_id=ctx.batch_id,
        )
        conn.commit()

        log.info(
            "ingest.completed", rows_in=len(records), rows_inserted=inserted, capture_id=capture_id
        )

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={
                "records": len(records),
                "inserted": inserted,
                "capture_id": capture_id,
                "captured_at": captured_at.isoformat(),
            },
        )


# =============================================================================
# NORMALIZE PIPELINE
# =============================================================================


@register_pipeline("finra.otc_transparency.normalize_week")
class NormalizeWeekPipeline(Pipeline):
    """
    Normalize raw FINRA OTC transparency records for a single week.

    Params:
        week_ending: ISO Friday date
        tier: Tier value
        force: Re-normalize (default: False)
    """

    name = "finra.otc_transparency.normalize_week"
    description = "Normalize raw FINRA OTC transparency data for one week"
    spec = PipelineSpec(
        required_params={
            "week_ending": ParamDef(
                name="week_ending",
                type=str,
                description="Week ending date in ISO format (YYYY-MM-DD)",
                validator=date_format,
                error_message="Must be ISO date format (YYYY-MM-DD)",
            ),
            "tier": ParamDef(
                name="tier",
                type=str,
                description="Market tier",
                validator=enum_value(Tier),
                error_message="Must be NMS_TIER_1, NMS_TIER_2, or OTC",
            ),
        },
        optional_params={
            "force": ParamDef(
                name="force",
                type=bool,
                description="Re-normalize even if already normalized",
                required=False,
                default=False,
            ),
        },
        examples=[
            "spine run finra.otc_transparency.normalize_week -p week_ending=2025-12-05 -p tier=OTC",
        ],
    )

    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()

        # Ensure core tables exist
        create_core_tables(conn)

        week = WeekEnding(self.params["week_ending"])
        tier = Tier(self.params["tier"])
        force = self.params.get("force", False)

        # Bind context for all logs in this pipeline
        bind_context(domain=DOMAIN, step="normalize")
        log.debug("normalize.params", week=str(week), tier=tier.value, force=force)

        ctx = new_context(batch_id=self.params.get("batch_id") or new_batch_id("normalize"))
        key = {"week_ending": str(week), "tier": tier.value}

        # Setup primitives (use domain="finra_otc_transparency" for core tables)
        manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
        rejects = RejectSink(
            conn, domain=DOMAIN, execution_id=ctx.execution_id, batch_id=ctx.batch_id
        )
        idem = IdempotencyHelper(conn)

        # Check idempotency
        if not force and manifest.is_at_least(key, "NORMALIZED"):
            log.info("normalize.skipped", reason="already_normalized")
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=started,
                completed_at=datetime.now(),
                metrics={"skipped": True},
            )

        # NEW: Determine which capture to normalize
        target_capture_id = self.params.get("capture_id")  # Optional: explicit capture

        with log_step("normalize.resolve_capture", level="debug"):
            if target_capture_id is None:
                # Use latest capture for this week+tier
                result = conn.execute(
                    f"""
                    SELECT capture_id, captured_at 
                    FROM {TABLES["raw"]} 
                    WHERE week_ending = ? AND tier = ?
                    ORDER BY captured_at DESC 
                    LIMIT 1
                """,
                    (str(week), tier.value),
                ).fetchone()

                if not result:
                    log.error("normalize.no_raw_data", week=str(week), tier=tier.value)
                    return PipelineResult(
                        status=PipelineStatus.FAILED,
                        started_at=started,
                        completed_at=datetime.now(),
                        metrics={"error": "No raw data found for this week"},
                    )

                target_capture_id = result["capture_id"]
                captured_at = result["captured_at"]
            else:
                # Use specified capture
                result = conn.execute(
                    f"""
                    SELECT captured_at FROM {TABLES["raw"]} 
                    WHERE week_ending = ? AND tier = ? AND capture_id = ?
                    LIMIT 1
                """,
                    (str(week), tier.value, target_capture_id),
                ).fetchone()

                if not result:
                    log.error("normalize.capture_not_found", capture_id=target_capture_id)
                    return PipelineResult(
                        status=PipelineStatus.FAILED,
                        started_at=started,
                        completed_at=datetime.now(),
                        metrics={"error": f"Capture {target_capture_id} not found"},
                    )

                captured_at = result["captured_at"]

        bind_context(capture_id=target_capture_id)
        log.debug("normalize.using_capture", capture_id=target_capture_id, captured_at=captured_at)

        # Idempotency: Delete existing normalized data for THIS capture only
        with log_step("normalize.delete_existing", level="debug"):
            conn.execute(
                f"""
                DELETE FROM {TABLES["venue_volume"]} 
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, target_capture_id),
            )

        # Load raw records for this specific capture
        with log_step("normalize.load_raw") as load_timer:
            rows = conn.execute(
                f"""
                SELECT * FROM {TABLES["raw"]}
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, target_capture_id),
            ).fetchall()
            load_timer.add_metric("rows_loaded", len(rows))

        log.info("normalize.loaded_raw", rows=len(rows))

        with log_step("normalize.build_records", level="debug"):
            raw_records = [
                RawOTCRecord(
                    week_ending=week.value,
                    tier=r["tier"],
                    symbol=r["symbol"],
                    mpid=r["mpid"],
                    total_shares=r["total_shares"],
                    total_trades=r["total_trades"],
                    issue_name=r["issue_name"] or "",
                    venue_name=r["venue_name"] or "",
                    source_line=0,
                    record_hash=r["record_hash"],
                )
                for r in rows
            ]

        # Normalize
        with log_step("normalize.validate", rows_in=len(raw_records)) as norm_timer:
            result = normalize_records(raw_records)
            norm_timer.add_metric("rows_accepted", len(result.valid))
            norm_timer.add_metric("rows_rejected", len(result.rejected))

        log.info(
            "normalize.validated",
            rows_in=len(raw_records),
            rows_out=len(result.valid),
            rows_rejected=len(result.rejected),
        )

        # Prepare batch data for bulk insert
        with log_step("normalize.prepare_batch", level="debug"):
            normalized_at_iso = datetime.now(UTC).isoformat()
            batch_data = [
                (
                    str(rec.week_ending),
                    rec.tier.value,
                    rec.symbol,
                    rec.mpid,
                    rec.total_shares,
                    rec.total_trades,
                    str(rec.total_shares / rec.total_trades) if rec.total_trades > 0 else None,
                    captured_at,
                    target_capture_id,
                    rec.record_hash,
                    ctx.execution_id,
                    ctx.batch_id,
                    normalized_at_iso,
                )
                for rec in result.valid
            ]

        # Bulk insert normalized records
        if batch_data:
            with log_step("normalize.bulk_insert", table=TABLES["venue_volume"], rows=len(batch_data)):
                conn.execute("PRAGMA synchronous = OFF")
                conn.execute("PRAGMA journal_mode = MEMORY")
                conn.executemany(
                    f"""
                    INSERT INTO {TABLES["venue_volume"]} (
                        week_ending, tier, symbol, mpid,
                        total_shares, total_trades, avg_trade_size,
                        captured_at, capture_id,
                        record_hash, execution_id, batch_id, normalized_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    batch_data,
                )
                conn.execute("PRAGMA synchronous = NORMAL")

        # Write rejects (using partition_key parameter)
        if len(result.rejected) > 0:
            with log_step("normalize.write_rejects", level="debug", count=len(result.rejected)):
                for rejected in result.rejected:
                    rejects.write(
                        Reject(
                            domain=DOMAIN,
                            stage="normalize",
                            partition_key=key,
                            record_id=rejected.raw.record_hash,
                            reason="; ".join(rejected.reasons),
                            record_data=str(rejected.raw),
                        )
                    )

        conn.commit()

        # Update manifest
        manifest.advance_to(
            key,
            "NORMALIZED",
            row_count=len(result.valid),
            error_count=len(result.rejected),
            execution_id=ctx.execution_id,
        )
        conn.commit()

        log.info(
            "normalize.completed",
            rows_accepted=len(result.valid),
            rows_rejected=len(result.rejected),
            capture_id=target_capture_id,
        )

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={
                "accepted": len(result.valid),
                "rejected": len(result.rejected),
                "capture_id": target_capture_id,
            },
        )


# =============================================================================
# AGGREGATE PIPELINE
# =============================================================================


@register_pipeline("finra.otc_transparency.aggregate_week")
class AggregateWeekPipeline(Pipeline):
    """
    Compute symbol summaries for one week.

    Params:
        week_ending: ISO Friday date
        tier: Tier value
        force: Re-aggregate (default: False)
    """

    name = "finra.otc_transparency.aggregate_week"
    description = "Compute FINRA OTC transparency aggregates for one week"
    spec = PipelineSpec(
        required_params={
            "week_ending": ParamDef(
                name="week_ending",
                type=str,
                description="ISO Friday date (YYYY-MM-DD)",
                validator=date_format,
                error_message="week_ending must be YYYY-MM-DD format",
            ),
            "tier": ParamDef(
                name="tier",
                type=str,
                description="OTC market tier (Tier1, Tier2, or OTC)",
                validator=enum_value(Tier),
                error_message="tier must be Tier1, Tier2, or OTC",
            ),
        },
        optional_params={
            "force": ParamDef(
                name="force",
                type=bool,
                description="Re-aggregate even if data exists",
                required=False,
                default=False,
            ),
        },
        examples=[
            "spine run finra.otc_transparency.aggregate_week -p week_ending=2024-01-05 tier=Tier1"
        ],
    )

    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()

        # Ensure core tables exist
        create_core_tables(conn)

        week = WeekEnding(self.params["week_ending"])
        tier = Tier(self.params["tier"])
        force = self.params.get("force", False)

        # Bind context for all logs in this pipeline
        bind_context(domain=DOMAIN, step="aggregate")
        log.debug("aggregate.params", week=str(week), tier=tier.value, force=force)

        ctx = new_context(batch_id=self.params.get("batch_id") or new_batch_id("aggregate"))
        key = {"week_ending": str(week), "tier": tier.value}

        # Setup primitives (use domain="finra_otc_transparency" for core tables)
        manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
        idem = IdempotencyHelper(conn)
        quality = QualityRunner(
            conn, domain=DOMAIN, execution_id=ctx.execution_id, batch_id=ctx.batch_id
        )

        # Check idempotency
        if not force and manifest.is_at_least(key, "AGGREGATED"):
            log.info("aggregate.skipped", reason="already_aggregated")
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=started,
                completed_at=datetime.now(),
                metrics={"skipped": True},
            )

        # NEW: Determine which capture to aggregate
        target_capture_id = self.params.get("capture_id")

        with log_step("aggregate.resolve_capture", level="debug"):
            if target_capture_id is None:
                # Use latest capture for this week+tier from normalized data
                result = conn.execute(
                    f"""
                    SELECT capture_id, captured_at 
                    FROM {TABLES["venue_volume"]} 
                    WHERE week_ending = ? AND tier = ?
                    ORDER BY captured_at DESC 
                    LIMIT 1
                """,
                    (str(week), tier.value),
                ).fetchone()

                if not result:
                    log.error("aggregate.no_normalized_data", week=str(week), tier=tier.value)
                    return PipelineResult(
                        status=PipelineStatus.FAILED,
                        started_at=started,
                        completed_at=datetime.now(),
                        metrics={"error": "No normalized data found for this week"},
                    )

                target_capture_id = result["capture_id"]
                captured_at = result["captured_at"]
            else:
                # Use specified capture
                result = conn.execute(
                    f"""
                    SELECT captured_at FROM {TABLES["venue_volume"]} 
                    WHERE week_ending = ? AND tier = ? AND capture_id = ?
                    LIMIT 1
                """,
                    (str(week), tier.value, target_capture_id),
                ).fetchone()

                if not result:
                    log.error("aggregate.capture_not_found", capture_id=target_capture_id)
                    return PipelineResult(
                        status=PipelineStatus.FAILED,
                        started_at=started,
                        completed_at=datetime.now(),
                        metrics={
                            "error": f"Capture {target_capture_id} not found in normalized data"
                        },
                    )

                captured_at = result["captured_at"]

        bind_context(capture_id=target_capture_id)

        # Idempotency: Delete existing aggregates for THIS capture only
        with log_step("aggregate.delete_existing", level="debug"):
            conn.execute(
                f"""
                DELETE FROM {TABLES["symbol_summary"]} 
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, target_capture_id),
            )

        # Load venue volume data for this specific capture
        with log_step("aggregate.load_normalized") as load_timer:
            rows = conn.execute(
                f"""
                SELECT * FROM {TABLES["venue_volume"]}
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, target_capture_id),
            ).fetchall()
            load_timer.add_metric("rows_loaded", len(rows))

        log.info("aggregate.loaded_normalized", rows=len(rows))

        with log_step("aggregate.build_records", level="debug"):
            venue_rows = [
                VenueVolumeRow(
                    week_ending=week.value,
                    tier=tier,
                    symbol=r["symbol"],
                    mpid=r["mpid"],
                    total_shares=r["total_shares"],
                    total_trades=r["total_trades"],
                )
                for r in rows
            ]

        # Compute aggregates (pure functions)
        with log_step("aggregate.compute_summaries") as sum_timer:
            summaries = aggregate_to_symbol_level(venue_rows)
            sum_timer.add_metric("symbols", len(summaries))

        log.info("aggregate.computed", symbols=len(summaries))

        # Write summaries WITH capture identity
        with log_step("aggregate.write_summaries", rows=len(summaries)):
            for s in summaries:
                avg_trade_size = s.total_shares / s.total_trades if s.total_trades > 0 else None
                conn.execute(
                    f"""
                    INSERT INTO {TABLES["symbol_summary"]} (
                        week_ending, tier, symbol,
                        total_volume, total_trades, venue_count, avg_trade_size,
                        captured_at, capture_id,
                        execution_id, batch_id, calculated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(s.week_ending),
                        s.tier.value,
                        s.symbol,
                        s.total_shares,
                        s.total_trades,
                        s.venue_count,
                        str(avg_trade_size) if avg_trade_size else None,
                        captured_at,
                        target_capture_id,  # Propagate capture identity
                        ctx.execution_id,
                        ctx.batch_id,
                        datetime.now(UTC).isoformat(),
                    ),
                )

        conn.commit()

        # Update manifest
        manifest.advance_to(key, "AGGREGATED", execution_id=ctx.execution_id)
        conn.commit()

        log.info("aggregate.completed", symbols=len(summaries), capture_id=target_capture_id)

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"symbols": len(summaries), "capture_id": target_capture_id},
        )


# =============================================================================
# ROLLING PIPELINE
# =============================================================================


@register_pipeline("finra.otc_transparency.compute_rolling")
class ComputeRollingPipeline(Pipeline):
    """
    Compute rolling metrics for all symbols.

    Params:
        week_ending: ISO Friday date (end of window)
        tier: Tier value
        force: Re-compute (default: False)
    """

    name = "finra.otc_transparency.compute_rolling"
    description = "Compute rolling metrics for FINRA OTC transparency"
    spec = PipelineSpec(
        required_params={
            "week_ending": ParamDef(
                name="week_ending",
                type=str,
                description="ISO Friday date (YYYY-MM-DD) - end of rolling window",
                validator=date_format,
                error_message="week_ending must be YYYY-MM-DD format",
            ),
            "tier": ParamDef(
                name="tier",
                type=str,
                description="OTC market tier (Tier1, Tier2, or OTC)",
                validator=enum_value(Tier),
                error_message="tier must be Tier1, Tier2, or OTC",
            ),
        },
        optional_params={
            "force": ParamDef(
                name="force",
                type=bool,
                description="Re-compute even if data exists",
                required=False,
                default=False,
            ),
        },
        examples=[
            "spine run finra.otc_transparency.compute_rolling -p week_ending=2024-01-05 tier=Tier1"
        ],
    )

    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()

        # Ensure core tables exist
        create_core_tables(conn)

        week = WeekEnding(self.params["week_ending"])
        tier = Tier(self.params["tier"])
        force = self.params.get("force", False)

        ctx = new_context(batch_id=self.params.get("batch_id") or new_batch_id("rolling"))
        key = {"week_ending": str(week), "tier": tier.value}

        # Setup primitives (use domain="finra_otc_transparency" for core tables)
        manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
        idem = IdempotencyHelper(conn)

        # Check idempotency
        if not force and manifest.is_at_least(key, "ROLLING"):
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=started,
                completed_at=datetime.now(),
                metrics={"skipped": True},
            )

        # Get latest capture for current week (determines output capture_id)
        current_capture = conn.execute(
            f"""
            SELECT capture_id, captured_at 
            FROM {TABLES["symbol_summary"]} 
            WHERE week_ending = ? AND tier = ?
            ORDER BY captured_at DESC 
            LIMIT 1
        """,
            (str(week), tier.value),
        ).fetchone()

        if not current_capture:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(),
                metrics={"error": "No summary data found for current week"},
            )

        output_capture_id = current_capture["capture_id"]
        output_captured_at = current_capture["captured_at"]

        # Delete existing rolling data for this week+capture
        conn.execute(
            f"""
            DELETE FROM {TABLES["rolling"]} 
            WHERE week_ending = ? AND tier = ? AND capture_id = ?
        """,
            (str(week), tier.value, output_capture_id),
        )

        # Get window weeks
        window_weeks = week.window(6)
        week_strs = [str(w) for w in window_weeks]

        # ROLLING SEMANTICS: Use LATEST capture per historical week
        placeholders = ",".join("?" * len(week_strs))
        rows = conn.execute(
            f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY week_ending, tier, symbol 
                    ORDER BY captured_at DESC
                ) as rn
                FROM {TABLES["symbol_summary"]}
                WHERE tier = ? AND week_ending IN ({placeholders})
            ) WHERE rn = 1
        """,
            (tier.value, *week_strs),
        ).fetchall()

        # Convert to SymbolAggregateRow objects
        summaries = [
            SymbolAggregateRow(
                week_ending=r["week_ending"]
                if isinstance(r["week_ending"], type(week.value))
                else type(week.value).fromisoformat(r["week_ending"]),
                tier=tier,
                symbol=r["symbol"],
                total_shares=r["total_volume"],
                total_trades=r["total_trades"],
                venue_count=r["venue_count"],
            )
            for r in rows
        ]

        # Get unique symbols
        symbols = {s.symbol for s in summaries}

        # Compute rolling for each symbol (simplified for now)
        count = 0
        for symbol in symbols:
            symbol_data = [s for s in summaries if s.symbol == symbol]
            if len(symbol_data) < 2:
                continue

            # Compute basic rolling stats
            avg_volume = sum(s.total_shares for s in symbol_data) / len(symbol_data)
            avg_trades = sum(s.total_trades for s in symbol_data) / len(symbol_data)
            min_volume = min(s.total_shares for s in symbol_data)
            max_volume = max(s.total_shares for s in symbol_data)

            # Trend: compare latest to earliest
            sorted_data = sorted(symbol_data, key=lambda x: x.week_ending)
            first_vol = sorted_data[0].total_shares
            last_vol = sorted_data[-1].total_shares
            trend_pct = ((last_vol - first_vol) / first_vol * 100) if first_vol > 0 else 0
            trend_direction = "UP" if trend_pct > 5 else ("DOWN" if trend_pct < -5 else "FLAT")

            conn.execute(
                f"""
                INSERT INTO {TABLES["rolling"]} (
                    week_ending, tier, symbol,
                    avg_volume, avg_trades, min_volume, max_volume,
                    trend_direction, trend_pct,
                    weeks_in_window, is_complete,
                    captured_at, capture_id,
                    execution_id, batch_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    str(week),
                    tier.value,
                    symbol,
                    str(avg_volume),
                    str(avg_trades),
                    min_volume,
                    max_volume,
                    trend_direction,
                    str(trend_pct),
                    len(symbol_data),
                    1 if len(symbol_data) >= 6 else 0,
                    output_captured_at,
                    output_capture_id,
                    ctx.execution_id,
                    ctx.batch_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
            count += 1

        conn.commit()

        # Update manifest
        manifest.advance_to(key, "ROLLING", execution_id=ctx.execution_id)
        conn.commit()

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"symbols_computed": count, "capture_id": output_capture_id},
        )


# =============================================================================
# BACKFILL PIPELINE (ORCHESTRATOR)
# =============================================================================


@register_pipeline("finra.otc_transparency.backfill_range")
class BackfillRangePipeline(Pipeline):
    """
    Orchestrate multi-week backfill.

    Params:
        tier: Tier value
        weeks_back: Number of weeks to process
        source_dir: Directory containing week files
        force: Force reprocess (default: False)
    """

    name = "finra.otc_transparency.backfill_range"
    description = "Orchestrate multi-week FINRA OTC transparency backfill"
    spec = PipelineSpec(
        required_params={
            "tier": ParamDef(
                name="tier",
                type=str,
                description="OTC market tier (Tier1, Tier2, or OTC)",
                validator=enum_value(Tier),
                error_message="tier must be Tier1, Tier2, or OTC",
            ),
            "weeks_back": ParamDef(
                name="weeks_back",
                type=int,
                description="Number of weeks to backfill (counting backwards from latest Friday)",
                validator=positive_int,
                error_message="weeks_back must be a positive integer",
            ),
            "source_dir": ParamDef(
                name="source_dir",
                type=str,
                description="Directory containing weekly data files",
                validator=file_exists,
                error_message="source_dir must be a valid directory path",
            ),
        },
        optional_params={
            "force": ParamDef(
                name="force",
                type=bool,
                description="Force reprocess even if data exists",
                required=False,
                default=False,
            ),
            "file_pattern": ParamDef(
                name="file_pattern",
                type=str,
                description="Filename pattern (use {week} placeholder)",
                required=False,
                default="week_{week}.psv",
            ),
        },
        examples=[
            "spine run finra.otc_transparency.backfill_range -p tier=Tier1 weeks_back=6 source_dir=data/fixtures/otc"
        ],
        notes=[
            "Files should follow the pattern specified in file_pattern (default: week_YYYY-MM-DD.psv)",
            "Will automatically run ingest → normalize → aggregate → rolling for each week",
        ],
    )

    def run(self) -> PipelineResult:
        started = datetime.now()

        tier = Tier(self.params["tier"])
        weeks_back = int(self.params.get("weeks_back", 6))
        source_dir = Path(self.params.get("source_dir", "data/fixtures/otc"))
        force = self.params.get("force", False)
        file_pattern = self.params.get("file_pattern", "week_{week}.psv")

        # Create batch context
        batch_id = new_batch_id(f"backfill_{tier.value}")

        # Get weeks to process
        weeks = WeekEnding.last_n(weeks_back)
        total_weeks = len(weeks)

        # Bind context for logging
        bind_context(domain=DOMAIN, step="backfill", batch_id=batch_id)
        log.info(
            "backfill.start",
            tier=tier.value,
            weeks_back=weeks_back,
            source_dir=str(source_dir),
            total_weeks=total_weeks,
        )

        processed = 0
        skipped = 0
        errors = []
        phase_results = []

        for week_idx, week in enumerate(weeks, 1):
            week_start = datetime.now()

            # Phase tracking
            log.info(
                "backfill.week.start",
                week=str(week),
                progress=f"{week_idx}/{total_weeks}",
            )

            # Find file
            file_name = file_pattern.replace("{week}", str(week))
            file_path = source_dir / file_name

            if not file_path.exists():
                log.warning("backfill.week.file_not_found", week=str(week), file=str(file_path))
                errors.append(
                    {
                        "week": str(week),
                        "phase": "file_check",
                        "error": f"File not found: {file_path}",
                    }
                )
                phase_results.append(
                    {"week": str(week), "status": "skipped", "reason": "file_not_found"}
                )
                skipped += 1
                continue

            try:
                # Phase 1: Ingest
                log.debug("backfill.phase", week=str(week), phase="ingest")
                ingest = IngestWeekPipeline(
                    {
                        "week_ending": str(week),
                        "tier": tier.value,
                        "file_path": str(file_path),
                        "force": force,
                        "batch_id": batch_id,
                    }
                )
                ingest_result = ingest.run()

                # Phase 2: Normalize
                log.debug("backfill.phase", week=str(week), phase="normalize")
                normalize = NormalizeWeekPipeline(
                    {
                        "week_ending": str(week),
                        "tier": tier.value,
                        "force": force,
                        "batch_id": batch_id,
                    }
                )
                normalize_result = normalize.run()

                # Phase 3: Aggregate
                log.debug("backfill.phase", week=str(week), phase="aggregate")
                aggregate = AggregateWeekPipeline(
                    {
                        "week_ending": str(week),
                        "tier": tier.value,
                        "force": force,
                        "batch_id": batch_id,
                    }
                )
                aggregate_result = aggregate.run()

                week_duration = (datetime.now() - week_start).total_seconds()
                log.info(
                    "backfill.week.complete",
                    week=str(week),
                    duration_seconds=round(week_duration, 2),
                    progress=f"{week_idx}/{total_weeks}",
                )

                phase_results.append(
                    {
                        "week": str(week),
                        "status": "completed",
                        "duration_seconds": round(week_duration, 2),
                        "ingest_rows": ingest_result.metrics.get("rows", 0)
                        if ingest_result.metrics
                        else 0,
                    }
                )
                processed += 1

            except Exception as e:
                log.error("backfill.week.error", week=str(week), error=str(e))
                errors.append({"week": str(week), "phase": "processing", "error": str(e)})
                phase_results.append({"week": str(week), "status": "failed", "error": str(e)})

        # Phase 4: Compute rolling for latest week (if any weeks processed)
        if processed > 0:
            log.info("backfill.phase", phase="rolling", week=str(weeks[-1]))
            try:
                rolling = ComputeRollingPipeline(
                    {
                        "week_ending": str(weeks[-1]),
                        "tier": tier.value,
                        "force": force,
                        "batch_id": batch_id,
                    }
                )
                rolling.run()
            except Exception as e:
                log.error("backfill.rolling.error", error=str(e))
                errors.append({"week": str(weeks[-1]), "phase": "rolling", "error": str(e)})

        # Determine final status
        if errors:
            if processed == 0:
                status = PipelineStatus.FAILED
            else:
                # Partial success - some weeks processed, some failed
                status = PipelineStatus.COMPLETED  # Could add PARTIAL_SUCCESS status
        else:
            status = PipelineStatus.COMPLETED

        total_duration = (datetime.now() - started).total_seconds()

        # Summary logging
        log.info(
            "backfill.complete",
            status=status.value,
            processed=processed,
            skipped=skipped,
            failed=len(errors),
            total=total_weeks,
            duration_seconds=round(total_duration, 2),
        )

        # Build error summary for result
        error_summary = None
        if errors:
            error_summary = "; ".join(
                f"{e['week']}:{e['phase']}:{e['error'][:50]}" for e in errors[:5]
            )
            if len(errors) > 5:
                error_summary += f"... and {len(errors) - 5} more"

        return PipelineResult(
            status=status,
            started_at=started,
            completed_at=datetime.now(),
            error=error_summary,
            metrics={
                "weeks_processed": processed,
                "weeks_skipped": skipped,
                "weeks_failed": len(errors),
                "weeks_total": total_weeks,
                "batch_id": batch_id,
                "duration_seconds": round(total_duration, 2),
                "phase_results": phase_results,
                "errors": errors if errors else None,
            },
        )


# =============================================================================
# VENUE SHARE PIPELINE
# =============================================================================


@register_pipeline("finra.otc_transparency.compute_venue_share")
class ComputeVenueSharePipeline(Pipeline):
    """
    Compute venue market share for one week.

    Aggregates venue_volume data to produce per-venue market share metrics.
    Each venue (MPID) gets a row with its total volume and share of tier.

    Invariant: SUM(market_share_pct) = 1.0 per (week, tier)

    Params:
        week_ending: ISO Friday date
        tier: Tier value
        force: Re-compute (default: False)
    """

    name = "finra.otc_transparency.compute_venue_share"
    description = "Compute FINRA OTC venue market share for one week"
    spec = PipelineSpec(
        required_params={
            "week_ending": ParamDef(
                name="week_ending",
                type=str,
                description="ISO Friday date (YYYY-MM-DD)",
                validator=date_format,
                error_message="week_ending must be YYYY-MM-DD format",
            ),
            "tier": ParamDef(
                name="tier",
                type=str,
                description="OTC market tier (Tier1, Tier2, or OTC)",
                validator=enum_value(Tier),
                error_message="tier must be Tier1, Tier2, or OTC",
            ),
        },
        optional_params={
            "force": ParamDef(
                name="force",
                type=bool,
                description="Re-compute even if data exists",
                required=False,
                default=False,
            ),
        },
        examples=[
            "spine run finra.otc_transparency.compute_venue_share -p week_ending=2024-01-05 tier=Tier1"
        ],
    )

    def run(self) -> PipelineResult:
        from spine.domains.finra.otc_transparency.calculations import (
            VenueShareRow,
            compute_venue_share_v1,
            validate_venue_share_invariants,
        )
        from spine.domains.finra.otc_transparency.schema import get_current_version

        started = datetime.now()
        conn = get_connection()

        # Ensure core tables exist
        create_core_tables(conn)

        week = WeekEnding(self.params["week_ending"])
        tier = Tier(self.params["tier"])
        force = self.params.get("force", False)

        # Bind context for logging
        bind_context(domain=DOMAIN, step="venue_share")
        log.debug("venue_share.params", week=str(week), tier=tier.value, force=force)

        ctx = new_context(batch_id=self.params.get("batch_id") or new_batch_id("venue_share"))
        key = {"week_ending": str(week), "tier": tier.value}

        # Setup primitives
        manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
        quality = QualityRunner(
            conn, domain=DOMAIN, execution_id=ctx.execution_id, batch_id=ctx.batch_id
        )

        # Determine calc version (policy-driven)
        calc_version = get_current_version("venue_share")

        # Resolve target capture from venue_volume
        target_capture_id = self.params.get("capture_id")

        with log_step("venue_share.resolve_capture", level="debug"):
            if target_capture_id is None:
                result = conn.execute(
                    f"""
                    SELECT capture_id, captured_at 
                    FROM {TABLES["venue_volume"]} 
                    WHERE week_ending = ? AND tier = ?
                    ORDER BY captured_at DESC 
                    LIMIT 1
                """,
                    (str(week), tier.value),
                ).fetchone()

                if not result:
                    log.error("venue_share.no_normalized_data", week=str(week), tier=tier.value)
                    return PipelineResult(
                        status=PipelineStatus.FAILED,
                        started_at=started,
                        completed_at=datetime.now(),
                        metrics={"error": "No normalized data found for this week"},
                    )

                target_capture_id = result["capture_id"]
                captured_at = result["captured_at"]
            else:
                result = conn.execute(
                    f"""
                    SELECT captured_at FROM {TABLES["venue_volume"]} 
                    WHERE week_ending = ? AND tier = ? AND capture_id = ?
                    LIMIT 1
                """,
                    (str(week), tier.value, target_capture_id),
                ).fetchone()

                if not result:
                    log.error("venue_share.capture_not_found", capture_id=target_capture_id)
                    return PipelineResult(
                        status=PipelineStatus.FAILED,
                        started_at=started,
                        completed_at=datetime.now(),
                        metrics={"error": f"Capture {target_capture_id} not found"},
                    )

                captured_at = result["captured_at"]

        bind_context(capture_id=target_capture_id)

        # Idempotency: Delete existing data for THIS capture
        with log_step("venue_share.delete_existing", level="debug"):
            conn.execute(
                f"""
                DELETE FROM {TABLES["venue_share"]} 
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, target_capture_id),
            )

        # Load venue volume data
        with log_step("venue_share.load_normalized") as load_timer:
            rows = conn.execute(
                f"""
                SELECT * FROM {TABLES["venue_volume"]}
                WHERE week_ending = ? AND tier = ? AND capture_id = ?
            """,
                (str(week), tier.value, target_capture_id),
            ).fetchall()
            load_timer.add_metric("rows_loaded", len(rows))

        log.info("venue_share.loaded_normalized", rows=len(rows))

        # Build input records
        with log_step("venue_share.build_records", level="debug"):
            venue_rows = [
                VenueVolumeRow(
                    week_ending=week.value,
                    tier=tier,
                    symbol=r["symbol"],
                    mpid=r["mpid"],
                    total_shares=r["total_shares"],
                    total_trades=r["total_trades"],
                )
                for r in rows
            ]

        # Compute venue shares (pure function)
        with log_step("venue_share.compute") as comp_timer:
            shares = compute_venue_share_v1(venue_rows)
            comp_timer.add_metric("venues", len(shares))

        log.info("venue_share.computed", venues=len(shares))

        # Validate invariants
        with log_step("venue_share.validate", level="debug"):
            invariant_errors = validate_venue_share_invariants(shares)
            if invariant_errors:
                for err in invariant_errors:
                    quality.record_fail(
                        partition_key=key,
                        check_name="venue_share_invariant",
                        category="BUSINESS_RULE",
                        message=err,
                    )
                log.warning("venue_share.invariant_violations", count=len(invariant_errors))

        # Write results
        with log_step("venue_share.write", rows=len(shares)):
            for s in shares:
                conn.execute(
                    f"""
                    INSERT INTO {TABLES["venue_share"]} (
                        week_ending, tier, mpid,
                        total_volume, total_trades, symbol_count,
                        market_share_pct, rank,
                        captured_at, capture_id,
                        execution_id, batch_id, calculated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(s.week_ending),
                        s.tier.value,
                        s.mpid,
                        s.total_volume,
                        s.total_trades,
                        s.symbol_count,
                        str(s.market_share_pct),
                        s.rank,
                        captured_at,
                        target_capture_id,
                        ctx.execution_id,
                        ctx.batch_id,
                        datetime.now(UTC).isoformat(),
                    ),
                )

        conn.commit()

        log.info(
            "venue_share.completed",
            venues=len(shares),
            capture_id=target_capture_id,
            calc_version=calc_version,
        )

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={
                "venues": len(shares),
                "capture_id": target_capture_id,
                "calc_version": calc_version,
                "invariant_errors": len(invariant_errors) if invariant_errors else 0,
            },
        )


# =============================================================================
# CROSS-DOMAIN CALCULATION: Volume Per Trading Day
# =============================================================================


@register_pipeline("finra.otc_transparency.compute_volume_per_day")
class ComputeVolumePerDayPipeline(Pipeline):
    """
    Compute volume per trading day (cross-domain calculation).
    
    This pipeline demonstrates hardened cross-domain dependency handling:
    
    Dependencies:
    - finra.otc_transparency: symbol_summary data (same domain)
    - reference.exchange_calendar: holidays data (different domain)
    
    Features:
    1. Year-boundary semantics: Handles weeks spanning year boundaries
    2. Dependency helper: Standardized dependency checking
    3. As-of mode: Pin to specific calendar capture_id for replay
    4. Exchange code: Configurable exchange (XNYS, XNAS, etc.)
    
    Params:
        week_ending: Week to compute (YYYY-MM-DD Friday)
        tier: Market tier (Tier1, Tier2, OTC)
        exchange_code: Exchange calendar to use (default: XNYS)
        calendar_capture_id: Optional specific calendar capture for as-of queries
        force: Recompute even if already done
    """

    name = "finra.otc_transparency.compute_volume_per_day"
    description = "Compute volume per trading day using exchange calendar"
    
    # Explicit dependency declaration
    DEPENDENCIES = [
        {
            "domain": "reference.exchange_calendar",
            "table": "reference_exchange_calendar_holidays",
            "description": "Exchange holiday calendar for the year",
            "required": True,
        },
    ]

    spec = PipelineSpec(
        required_params={
            "week_ending": ParamDef(
                name="week_ending",
                type=str,
                description="Week ending date (YYYY-MM-DD, must be Friday)",
                required=True,
                validator=date_format,
            ),
            "tier": ParamDef(
                name="tier",
                type=str,
                description="Market tier",
                required=True,
                validator=enum_value(Tier),
            ),
        },
        optional_params={
            "exchange_code": ParamDef(
                name="exchange_code",
                type=str,
                description="Exchange calendar to use (default: XNYS)",
                required=False,
                default="XNYS",
            ),
            "calendar_capture_id": ParamDef(
                name="calendar_capture_id",
                type=str,
                description="Specific calendar capture to use (for as-of queries)",
                required=False,
            ),
            "force": ParamDef(
                name="force",
                type=bool,
                description="Force recomputation",
                required=False,
                default=False,
            ),
        },
    )

    def run(self) -> PipelineResult:
        """Execute volume per trading day calculation."""
        from spine.domains.finra.otc_transparency.calculations import (
            DependencyCheckResult,
            DependencyMissingError,
            SymbolAggregateRow,
            VolumePerTradingDayRow,
            check_dependencies,
            compute_volume_per_trading_day,
            get_week_date_range,
            get_years_in_range,
            load_holidays_for_years,
        )
        
        started = datetime.now()
        ctx = new_context()
        conn = get_connection()
        params = self.params
        
        # Parse params
        week_ending_str = params["week_ending"]
        week_ending = date.fromisoformat(week_ending_str)
        tier_str = params["tier"]
        tier = Tier(tier_str)
        exchange_code = params.get("exchange_code", "XNYS")
        calendar_capture_id = params.get("calendar_capture_id")
        force = params.get("force", False)
        
        log.info(
            "volume_per_day.starting",
            week_ending=week_ending_str,
            tier=tier_str,
            exchange_code=exchange_code,
            calendar_capture_id=calendar_capture_id,
        )
        
        # FEATURE #1: Year-boundary semantics
        # Determine which years are touched by this week
        week_start, week_end = get_week_date_range(week_ending)
        years_needed = get_years_in_range(week_start, week_end)
        
        log.debug(
            "volume_per_day.week_range",
            week_start=str(week_start),
            week_end=str(week_end),
            years=years_needed,
        )
        
        # FEATURE #2: Dependency helper
        # Build dependency context
        dependency_context = {
            "years": years_needed,
            "exchange_code": exchange_code,
            "capture_id": calendar_capture_id,
        }
        
        # STEP 1: Check dependencies using standardized helper
        # Note: We're manually checking here instead of using check_dependencies()
        # because the helper needs specific implementation details
        dependency_errors = []
        for year in years_needed:
            if calendar_capture_id:
                count = conn.execute(
                    """
                    SELECT COUNT(*) FROM reference_exchange_calendar_holidays
                    WHERE year = ? AND exchange_code = ? AND capture_id = ?
                    """,
                    (year, exchange_code, calendar_capture_id),
                ).fetchone()[0]
            else:
                count = conn.execute(
                    """
                    SELECT COUNT(*) FROM reference_exchange_calendar_holidays
                    WHERE year = ? AND exchange_code = ?
                    """,
                    (year, exchange_code),
                ).fetchone()[0]
            
            if count == 0:
                dependency_errors.append(
                    f"Exchange calendar {exchange_code} for {year} not loaded. "
                    f"Run: spine run reference.exchange_calendar.ingest_year --year {year}"
                )
        
        if dependency_errors:
            log.error(
                "volume_per_day.dependency_missing",
                errors=dependency_errors,
            )
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(),
                error=dependency_errors[0],
                metrics={"dependency_errors": dependency_errors},
            )
        
        # STEP 2: Load dependencies explicitly
        # FEATURE #3: As-of mode support
        try:
            holidays, capture_id_used = load_holidays_for_years(
                conn,
                years_needed,
                exchange_code,
                calendar_capture_id,
            )
        except DependencyMissingError as e:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(),
                error=str(e),
            )
        
        log.debug(
            "volume_per_day.calendar_loaded",
            years=years_needed,
            holidays=len(holidays),
            capture_id=capture_id_used,
        )
        
        # STEP 3: Load FINRA symbol summary data
        rows = conn.execute(
            f"""
            SELECT week_ending, tier, symbol, total_volume, total_trades, venue_count
            FROM {TABLES["symbol_summary"]}
            WHERE week_ending = ? AND tier = ?
            ORDER BY captured_at DESC
            """,
            (week_ending_str, tier_str),
        ).fetchall()
        
        if not rows:
            log.warning(
                "volume_per_day.no_data",
                week_ending=week_ending_str,
                tier=tier_str,
            )
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=started,
                completed_at=datetime.now(),
                metrics={"reason": "No symbol summary data for week/tier"},
            )
        
        # Convert to dataclass (using latest capture per symbol)
        seen_symbols: set[str] = set()
        symbol_rows: list[SymbolAggregateRow] = []
        
        for r in rows:
            symbol = r[2]
            if symbol not in seen_symbols:
                seen_symbols.add(symbol)
                symbol_rows.append(SymbolAggregateRow(
                    week_ending=week_ending,
                    tier=tier,
                    symbol=symbol,
                    total_shares=r[3],
                    total_trades=r[4],
                    venue_count=r[5],
                ))
        
        log.debug("volume_per_day.symbols_loaded", count=len(symbol_rows))
        
        # STEP 4: Compute cross-domain calculation (pure function)
        # FEATURE #4: Exchange code is already parameterized in the pure function
        results = compute_volume_per_trading_day(
            symbol_rows,
            holidays,
            exchange_code,
            capture_id_used,
        )
        
        log.info(
            "volume_per_day.completed",
            symbols=len(results),
            trading_days=results[0].trading_days if results else 0,
            years_touched=years_needed,
            capture_id=capture_id_used,
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={
                "symbols": len(results),
                "trading_days": results[0].trading_days if results else 0,
                "exchange_code": exchange_code,
                "calendar_years": years_needed,
                "calendar_capture_id": capture_id_used,
            },
        )
