"""
Exchange Calendar Pipelines — Thin orchestration over core primitives.

Pipelines:
- reference.exchange_calendar.ingest_year: Ingest holiday data for a year
- reference.exchange_calendar.compute_trading_days: Calculate monthly trading days

These pipelines follow the same pattern as FINRA:
1. Use spine.core primitives (manifest, quality)
2. Call domain-specific functions (calculations)
3. Write results to storage

Parameters are domain-specific:
- year: Calendar year (e.g., 2025)
- exchange_code: MIC code (e.g., "XNYS")
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from spine.core import (
    QualityRunner,
    WorkManifest,
    new_batch_id,
    new_context,
)
from spine.domains.reference.exchange_calendar.calculations import (
    Holiday,
    compute_monthly_trading_days,
    holidays_to_set,
    parse_holidays,
)
from spine.domains.reference.exchange_calendar.schema import (
    DOMAIN,
    Exchange,
    Stage,
    TABLES,
    partition_key,
)
from spine.domains.reference.exchange_calendar.sources import (
    IngestionError,
    create_source,
)
from spine.framework.db import get_connection
from spine.framework.logging import get_logger
from spine.framework.params import (
    ParamDef,
    PipelineSpec,
    enum_value,
    file_exists,
    positive_int,
)
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import register_pipeline

log = get_logger(__name__)


def generate_capture_id(year: int, exchange_code: str, captured_at: datetime) -> str:
    """Generate deterministic capture_id for a year+exchange+timestamp."""
    content = f"{exchange_code}|{year}|{captured_at.isoformat()}"
    hash_suffix = hashlib.sha256(content.encode()).hexdigest()[:6]
    return f"reference.exchange_calendar:{exchange_code}:{year}:{hash_suffix}"


# =============================================================================
# INGEST PIPELINE
# =============================================================================


@register_pipeline("reference.exchange_calendar.ingest_year")
class IngestYearPipeline(Pipeline):
    """
    Ingest exchange calendar data for a year.
    
    Reads holiday data from JSON file and stores in database.
    
    Params:
        file_path: Path to JSON file with holiday data
        year: Calendar year (optional, extracted from file if not provided)
        exchange_code: Exchange MIC code (optional, extracted from file)
        force: Re-ingest even if already done (default: False)
    """

    name = "reference.exchange_calendar.ingest_year"
    description = "Ingest exchange calendar data for one year"
    spec = PipelineSpec(
        required_params={},
        optional_params={
            "file_path": ParamDef(
                name="file_path",
                type=Path,
                description="Path to JSON file with holiday data",
                required=False,
                validator=file_exists,
                error_message="File does not exist",
            ),
            "year": ParamDef(
                name="year",
                type=int,
                description="Calendar year (e.g., 2025)",
                required=False,
            ),
            "exchange_code": ParamDef(
                name="exchange_code",
                type=str,
                description="Exchange MIC code (e.g., XNYS)",
                required=False,
                validator=enum_value(Exchange),
                error_message=f"Must be one of: {', '.join(Exchange.values())}",
            ),
            "force": ParamDef(
                name="force",
                type=bool,
                description="Force re-ingestion",
                required=False,
            ),
        },
    )

    def run(self) -> PipelineResult:
        """Execute ingestion pipeline."""
        params = self.params
        ctx = new_context()
        batch_id = new_batch_id()
        captured_at = datetime.now(UTC)
        
        # Get parameters
        file_path = params.get("file_path")
        year = params.get("year")
        exchange_code = params.get("exchange_code")
        force = params.get("force", False)
        
        if not file_path:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                message="file_path is required",
                error="Missing required parameter: file_path",
            )
        
        try:
            # Fetch data
            source = create_source(
                source_type="json",
                file_path=file_path,
                year=year,
                exchange_code=exchange_code,
            )
            payload = source.fetch()
            
            year = payload.metadata.year
            exchange_code = payload.metadata.exchange_code
            
            log.info(
                "ingesting_calendar",
                year=year,
                exchange_code=exchange_code,
                source=str(file_path),
            )
            
            # Parse holidays
            holidays = parse_holidays(payload.content)
            
            # Generate capture ID
            capture_id = generate_capture_id(year, exchange_code, captured_at)
            
            # Check idempotency
            conn = get_connection()
            pk = partition_key(year, exchange_code)
            
            manifest = WorkManifest(conn, DOMAIN, stages=[s.value for s in Stage])
            existing = manifest.has_stage(pk, Stage.RAW.value)
            
            if existing and not force:
                log.info(
                    "already_ingested",
                    year=year,
                    exchange_code=exchange_code,
                )
                return PipelineResult(
                    status=PipelineStatus.COMPLETED,
                    started_at=captured_at,
                    completed_at=datetime.now(UTC),
                    metrics={"message": f"Year {year} for {exchange_code} already ingested", "rows_affected": 0},
                )
            
            # Insert holidays
            table = TABLES["holidays"]
            for h in holidays:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {table}
                    (year, exchange_code, holiday_date, holiday_name,
                     execution_id, batch_id, capture_id, captured_at, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        h.year,
                        h.exchange_code,
                        h.date.isoformat(),
                        h.name,
                        ctx.execution_id,
                        batch_id,
                        capture_id,
                        captured_at.isoformat(),
                    ),
                )
            
            conn.commit()
            
            # Update manifest
            manifest.advance_to(
                pk,
                Stage.RAW.value,
                row_count=len(holidays),
                execution_id=ctx.execution_id,
                batch_id=batch_id,
            )
            
            log.info(
                "ingestion_complete",
                year=year,
                exchange_code=exchange_code,
                holidays=len(holidays),
            )
            
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=captured_at,
                completed_at=datetime.now(UTC),
                metrics={"rows_affected": len(holidays)},
            )
            
        except IngestionError as e:
            log.error("ingestion_failed", error=str(e))
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=captured_at,
                completed_at=datetime.now(UTC),
                error=str(e),
            )


# =============================================================================
# COMPUTE TRADING DAYS PIPELINE
# =============================================================================


@register_pipeline("reference.exchange_calendar.compute_trading_days")
class ComputeTradingDaysPipeline(Pipeline):
    """
    Compute monthly trading day counts for a year.
    
    Reads holiday data from database and computes:
    - Trading days per month
    - Calendar days per month
    - Holidays per month
    
    Params:
        year: Calendar year to compute
        exchange_code: Exchange MIC code
        force: Recompute even if already done
    """

    name = "reference.exchange_calendar.compute_trading_days"
    description = "Compute monthly trading day counts"
    spec = PipelineSpec(
        required_params={
            "year": ParamDef(
                name="year",
                type=int,
                description="Calendar year (e.g., 2025)",
                required=True,
            ),
            "exchange_code": ParamDef(
                name="exchange_code",
                type=str,
                description="Exchange MIC code",
                required=True,
                validator=enum_value(Exchange),
                error_message=f"Must be one of: {', '.join(Exchange.values())}",
            ),
        },
        optional_params={
            "force": ParamDef(
                name="force",
                type=bool,
                description="Force recomputation",
                required=False,
            ),
        },
    )

    def run(self, params: dict) -> PipelineResult:
        """Execute computation pipeline."""
        ctx = new_context()
        batch_id = new_batch_id()
        captured_at = datetime.now(UTC)
        
        year = params["year"]
        exchange_code = params["exchange_code"]
        force = params.get("force", False)
        
        log.info(
            "computing_trading_days",
            year=year,
            exchange_code=exchange_code,
        )
        
        conn = get_connection()
        pk = partition_key(year, exchange_code)
        manifest = WorkManifest(conn, DOMAIN, stages=[s.value for s in Stage])
        
        # Check if computation already done
        existing = manifest.has_stage(pk, Stage.COMPUTED.value)
        if existing and not force:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                metrics={"message": f"Trading days for {exchange_code} {year} already computed", "rows_affected": 0},
            )
        
        # Load holidays from database
        holidays_table = TABLES["holidays"]
        rows = conn.execute(
            f"""
            SELECT holiday_date FROM {holidays_table}
            WHERE year = ? AND exchange_code = ?
            """,
            (year, exchange_code),
        ).fetchall()
        
        if not rows:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                message=f"No holiday data found for {exchange_code} {year}",
                error="Holiday data must be ingested first",
            )
        
        # Convert to set of dates
        from datetime import date as dt_date
        holidays = {dt_date.fromisoformat(r[0]) for r in rows}
        
        # Compute monthly trading days
        monthly_results = compute_monthly_trading_days(year, exchange_code, holidays)
        
        # Generate capture ID
        capture_id = generate_capture_id(year, exchange_code, captured_at)
        
        # Insert results
        table = TABLES["trading_days"]
        for m in monthly_results:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {table}
                (year, exchange_code, month, trading_days, calendar_days, holidays,
                 calc_name, calc_version, execution_id, batch_id, capture_id,
                 captured_at, calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    m.year,
                    m.exchange_code,
                    m.month,
                    m.trading_days,
                    m.calendar_days,
                    m.holidays,
                    m.calc_name,
                    m.calc_version,
                    ctx.execution_id,
                    batch_id,
                    capture_id,
                    captured_at.isoformat(),
                ),
            )
        
        conn.commit()
        
        # Update manifest
        manifest.advance_to(
            pk,
            Stage.COMPUTED.value,
            row_count=len(monthly_results),
            execution_id=ctx.execution_id,
            batch_id=batch_id,
        )
        
        log.info(
            "computation_complete",
            year=year,
            exchange_code=exchange_code,
            months=len(monthly_results),
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics={"message": f"Computed trading days for {exchange_code} {year}: 12 months", "rows_affected": 12},
        )
