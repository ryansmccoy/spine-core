"""
YAML Loader for Pipeline Groups.

Loads group definitions from YAML files with schema validation.

Phase 1: Basic YAML loading with minimal validation
Phase 2+: Full JSON Schema validation, file watching, error recovery

File Format (YAML):
    apiVersion: spine.io/v1
    kind: PipelineGroup
    metadata:
      name: finra.weekly_refresh
      domain: finra.otc_transparency
      version: 1
    spec:
      defaults:
        tier: "{{ params.tier }}"
      pipelines:
        - name: ingest
          pipeline: finra.otc_transparency.ingest_week
        - name: normalize
          pipeline: finra.otc_transparency.normalize_week
          depends_on: [ingest]
      policy:
        execution: sequential
        on_failure: stop
"""

from pathlib import Path
from typing import Any

import structlog

from spine.orchestration.exceptions import InvalidGroupSpecError
from spine.orchestration.models import PipelineGroup

logger = structlog.get_logger()

# Supported API versions
SUPPORTED_API_VERSIONS = {"spine.io/v1"}


def load_group_from_yaml(path: Path | str) -> PipelineGroup:
    """
    Load a single PipelineGroup from a YAML file.

    Args:
        path: Path to YAML file

    Returns:
        Parsed PipelineGroup

    Raises:
        FileNotFoundError: If file doesn't exist
        InvalidGroupSpecError: If YAML is invalid or doesn't match schema
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Group file not found: {path}")

    # Import yaml lazily (optional dependency)
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML loading. Install with: pip install pyyaml"
        )

    logger.debug("loader.load_yaml", path=str(path))

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise InvalidGroupSpecError(f"Invalid YAML in {path}: {e}")

    if not isinstance(data, dict):
        raise InvalidGroupSpecError(f"Expected dict, got {type(data).__name__}", field="root")

    # Validate apiVersion
    api_version = data.get("apiVersion")
    if api_version and api_version not in SUPPORTED_API_VERSIONS:
        raise InvalidGroupSpecError(
            f"Unsupported apiVersion: {api_version}. Supported: {SUPPORTED_API_VERSIONS}",
            field="apiVersion",
        )

    # Validate kind
    kind = data.get("kind")
    if kind and kind != "PipelineGroup":
        raise InvalidGroupSpecError(
            f"Expected kind 'PipelineGroup', got '{kind}'",
            field="kind",
        )

    # Parse the group
    try:
        group = PipelineGroup.from_dict(data)
    except (KeyError, ValueError, TypeError) as e:
        raise InvalidGroupSpecError(f"Failed to parse group from {path}: {e}")

    logger.info(
        "loader.loaded",
        path=str(path),
        group=group.name,
        step_count=len(group.steps),
    )

    return group


def load_groups_from_directory(
    directory: Path | str,
    pattern: str = "**/*.yaml",
    ignore_errors: bool = False,
) -> list[PipelineGroup]:
    """
    Load all PipelineGroups from a directory.

    Args:
        directory: Directory to scan
        pattern: Glob pattern for YAML files
        ignore_errors: If True, skip invalid files instead of raising

    Returns:
        List of parsed PipelineGroups
    """
    directory = Path(directory)

    if not directory.exists():
        logger.warning("loader.directory_not_found", path=str(directory))
        return []

    groups = []
    errors = []

    for path in directory.glob(pattern):
        if path.is_file():
            try:
                group = load_group_from_yaml(path)
                groups.append(group)
            except Exception as e:
                if ignore_errors:
                    logger.warning("loader.file_error", path=str(path), error=str(e))
                    errors.append((path, e))
                else:
                    raise

    logger.info(
        "loader.directory_loaded",
        directory=str(directory),
        loaded=len(groups),
        errors=len(errors),
    )

    return groups


def group_to_yaml(group: PipelineGroup) -> str:
    """
    Convert a PipelineGroup to YAML format.

    Args:
        group: The group to serialize

    Returns:
        YAML string in standard format
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML serialization. Install with: pip install pyyaml"
        )

    # Build YAML structure
    data = {
        "apiVersion": "spine.io/v1",
        "kind": "PipelineGroup",
        "metadata": {
            "name": group.name,
            "domain": group.domain,
            "version": group.version,
        },
        "spec": {
            "pipelines": [s.to_dict() for s in group.steps],
            "policy": {
                "execution": group.policy.mode.value,
                "max_concurrency": group.policy.max_concurrency,
                "on_failure": group.policy.on_failure.value,
            },
        },
    }

    if group.description:
        data["metadata"]["description"] = group.description

    if group.tags:
        data["metadata"]["tags"] = group.tags

    if group.defaults:
        data["spec"]["defaults"] = group.defaults

    if group.policy.timeout_minutes:
        data["spec"]["policy"]["timeout_minutes"] = group.policy.timeout_minutes

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def validate_yaml_schema(data: dict[str, Any]) -> list[str]:
    """
    Validate YAML data against group schema.

    Returns list of error messages (empty if valid).

    Phase 1: Basic structural validation
    Phase 2+: Full JSON Schema validation
    """
    errors = []

    # Check required fields
    if "metadata" in data:
        metadata = data["metadata"]
        if "name" not in metadata:
            errors.append("metadata.name is required")
        spec = data.get("spec", {})
        if "pipelines" not in spec:
            errors.append("spec.pipelines is required")
        else:
            for i, step in enumerate(spec["pipelines"]):
                if "name" not in step:
                    errors.append(f"spec.pipelines[{i}].name is required")
                if "pipeline" not in step:
                    errors.append(f"spec.pipelines[{i}].pipeline is required")
    else:
        # Flat format
        if "name" not in data:
            errors.append("name is required")
        if "steps" not in data and "pipelines" not in data:
            errors.append("steps or pipelines is required")

    return errors
