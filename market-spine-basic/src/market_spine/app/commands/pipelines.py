"""
Pipeline discovery and description commands.

These commands provide pipeline listing and introspection capabilities
for both CLI and API consumers.
"""

from dataclasses import dataclass, field

from market_spine.app.models import (
    CommandError,
    ErrorCode,
    ParameterDef,
    PipelineDetail,
    PipelineSummary,
    Result,
)
from market_spine.app.services.ingest import IngestResolver
from market_spine.app.services.tier import TierNormalizer
from spine.framework.registry import get_pipeline, list_pipelines

# =============================================================================
# List Pipelines Command
# =============================================================================


@dataclass
class ListPipelinesRequest:
    """Input for listing pipelines."""

    prefix: str | None = None


@dataclass
class ListPipelinesResult(Result):
    """Output from listing pipelines."""

    pipelines: list[PipelineSummary] = field(default_factory=list)
    total_count: int = 0
    filtered: bool = False


class ListPipelinesCommand:
    """
    List available pipelines with optional prefix filtering.

    Example:
        command = ListPipelinesCommand()
        result = command.execute(ListPipelinesRequest(prefix="finra.otc"))
        for p in result.pipelines:
            print(f"{p.name}: {p.description}")
    """

    def execute(self, request: ListPipelinesRequest) -> ListPipelinesResult:
        """
        Execute the list pipelines command.

        Args:
            request: Request with optional prefix filter

        Returns:
            Result containing list of pipeline summaries
        """
        try:
            all_names = list_pipelines()
            total_count = len(all_names)

            # Apply prefix filter if provided
            if request.prefix:
                filtered_names = [n for n in all_names if n.startswith(request.prefix)]
                filtered = True
            else:
                filtered_names = all_names
                filtered = False

            # Build summaries
            pipelines = []
            for name in filtered_names:
                try:
                    pipeline_cls = get_pipeline(name)
                    description = getattr(pipeline_cls, "description", "") or ""
                    pipelines.append(PipelineSummary(name=name, description=description))
                except Exception:
                    # Skip pipelines that fail to load
                    pipelines.append(PipelineSummary(name=name, description=""))

            return ListPipelinesResult(
                success=True,
                pipelines=pipelines,
                total_count=total_count,
                filtered=filtered,
            )

        except Exception as e:
            return ListPipelinesResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to list pipelines: {e}",
                ),
            )


# =============================================================================
# Describe Pipeline Command
# =============================================================================


@dataclass
class DescribePipelineRequest:
    """Input for describing a pipeline."""

    name: str


@dataclass
class DescribePipelineResult(Result):
    """Output from describing a pipeline."""

    pipeline: PipelineDetail | None = None


class DescribePipelineCommand:
    """
    Get detailed information about a specific pipeline.

    Example:
        command = DescribePipelineCommand()
        result = command.execute(
            DescribePipelineRequest(name="finra.otc_transparency.ingest_week")
        )
        if result.success:
            print(f"Required params: {result.pipeline.required_params}")
    """

    def __init__(
        self,
        tier_normalizer: TierNormalizer | None = None,
        ingest_resolver: IngestResolver | None = None,
    ) -> None:
        """Initialize with optional service overrides."""
        self._tier_normalizer = tier_normalizer or TierNormalizer()
        self._ingest_resolver = ingest_resolver or IngestResolver()

    def execute(self, request: DescribePipelineRequest) -> DescribePipelineResult:
        """
        Execute the describe pipeline command.

        Args:
            request: Request with pipeline name

        Returns:
            Result containing pipeline details or error
        """
        try:
            pipeline_cls = get_pipeline(request.name)
        except KeyError:
            return DescribePipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.PIPELINE_NOT_FOUND,
                    message=f"Pipeline '{request.name}' not found.",
                    details={"pipeline": request.name},
                ),
            )
        except Exception as e:
            return DescribePipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to load pipeline: {e}",
                ),
            )

        try:
            spec = pipeline_cls.spec
            description = getattr(pipeline_cls, "description", "") or ""

            # Build required params list
            required_params = []
            for name, param in spec.required_params.items():
                param_def = ParameterDef(
                    name=name,
                    type=param.type.__name__ if hasattr(param, "type") else "str",
                    description=param.description or "",
                    required=True,
                )
                # Add tier choices if this is the tier param (delegate to service)
                if name == "tier":
                    param_def.choices = self._tier_normalizer.get_valid_values()
                required_params.append(param_def)

            # Build optional params list
            optional_params = []
            for name, param in spec.optional_params.items():
                optional_params.append(
                    ParameterDef(
                        name=name,
                        type=param.type.__name__ if hasattr(param, "type") else "str",
                        description=param.description or "",
                        default=param.default,
                        required=False,
                    )
                )

            # Check if this is an ingest pipeline (delegate to service)
            is_ingest = self._ingest_resolver.is_ingest_pipeline(request.name)

            pipeline_detail = PipelineDetail(
                name=request.name,
                description=description,
                required_params=required_params,
                optional_params=optional_params,
                is_ingest=is_ingest,
            )

            return DescribePipelineResult(
                success=True,
                pipeline=pipeline_detail,
            )

        except Exception as e:
            return DescribePipelineResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to describe pipeline: {e}",
                ),
            )
