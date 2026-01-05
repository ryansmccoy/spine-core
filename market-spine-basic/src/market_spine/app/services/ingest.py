"""
Ingest file path resolution service.

Resolves ingest file paths either from explicit user input or
by deriving from week_ending and tier parameters.

This service encapsulates the file path derivation logic used
by ingest pipelines, making it available to both CLI and API.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class IngestResolution:
    """
    Result of ingest source resolution.

    Attributes:
        source_type: "explicit" if user provided path, "derived" if calculated
        file_path: The resolved file path
        derivation_logic: Explanation of how path was derived (if derived)
        exists: Whether the file exists (optional check)
    """

    source_type: str  # "explicit" | "derived"
    file_path: str
    derivation_logic: str | None = None
    exists: bool | None = None


class IngestResolver:
    """
    Resolve ingest file paths for pipelines.

    This service determines the source file for ingest operations,
    either from explicit user input or by deriving from parameters.

    Example:
        resolver = IngestResolver()

        # Explicit file
        result = resolver.resolve("ingest_week", {"file_path": "data/my.csv"})
        # result.source_type == "explicit"

        # Derived file
        result = resolver.resolve("ingest_week", {"week_ending": "2025-12-19", "tier": "OTC"})
        # result.source_type == "derived"
        # result.file_path == "data/finra/finra_otc_weekly_otc_20251219.csv"
    """

    # Tier to filename component mapping
    TIER_FILE_MAP = {
        "OTC": "otc",
        "NMS_TIER_1": "tier1",
        "NMS_TIER_2": "tier2",
    }

    # Base directory for FINRA data files
    DEFAULT_DATA_DIR = "data/finra"

    def resolve(
        self,
        pipeline: str,
        params: dict[str, Any],
        check_exists: bool = False,
    ) -> IngestResolution | None:
        """
        Resolve the ingest source for a pipeline.

        Args:
            pipeline: Pipeline name (used to check if it's an ingest pipeline)
            params: Pipeline parameters
            check_exists: Whether to check if the file exists

        Returns:
            IngestResolution with file path info, or None if not an ingest pipeline
        """
        if not self.is_ingest_pipeline(pipeline):
            return None

        # Check for explicit file path
        file_path = params.get("file_path")
        if file_path:
            resolution = IngestResolution(
                source_type="explicit",
                file_path=str(file_path),
                derivation_logic=None,
            )
        else:
            # Derive from week_ending and tier
            resolution = self._derive_file_path(params)

        # Optionally check if file exists
        if check_exists and resolution:
            resolution.exists = Path(resolution.file_path).exists()

        return resolution

    def is_ingest_pipeline(self, pipeline: str) -> bool:
        """Check if a pipeline is a FINRA ingest pipeline that needs file resolution."""
        # Only apply to FINRA ingest pipelines - other domains handle their own source resolution
        return "finra" in pipeline.lower() and "ingest" in pipeline.lower()

    def _derive_file_path(self, params: dict[str, Any]) -> IngestResolution:
        """
        Derive file path from week_ending and tier parameters.

        Args:
            params: Must contain 'week_ending' and 'tier'

        Returns:
            IngestResolution with derived path

        Raises:
            ValueError: If required parameters are missing
        """
        week_ending = params.get("week_ending")
        tier = params.get("tier")

        if not week_ending:
            raise ValueError("Cannot derive file path: 'week_ending' parameter required")
        if not tier:
            raise ValueError("Cannot derive file path: 'tier' parameter required")

        # Convert tier to filename component
        tier_str = self.TIER_FILE_MAP.get(tier, tier.lower())

        # Convert date to filename format (remove hyphens)
        date_str = str(week_ending).replace("-", "")

        # Build the derived path
        file_path = f"{self.DEFAULT_DATA_DIR}/finra_otc_weekly_{tier_str}_{date_str}.csv"

        return IngestResolution(
            source_type="derived",
            file_path=file_path,
            derivation_logic=(
                f"Pattern: {self.DEFAULT_DATA_DIR}/finra_otc_weekly_{{tier}}_{{date}}.csv\n"
                f"tier={tier} → {tier_str}, week_ending={week_ending} → {date_str}"
            ),
        )

    def derive_file_path_preview(
        self,
        week_ending: str | None,
        tier: str | None,
    ) -> str | None:
        """
        Preview what file path would be derived (for dry-run display).

        Args:
            week_ending: Week ending date (YYYY-MM-DD)
            tier: Canonical tier value

        Returns:
            Derived file path, or None if parameters are missing
        """
        if not week_ending or not tier:
            return None

        tier_str = self.TIER_FILE_MAP.get(tier, tier.lower())
        date_str = str(week_ending).replace("-", "")

        return f"{self.DEFAULT_DATA_DIR}/finra_otc_weekly_{tier_str}_{date_str}.csv"
