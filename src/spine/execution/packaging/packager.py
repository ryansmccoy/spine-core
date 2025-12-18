"""WorkflowPackager — bundle workflows into executable .pyz archives.

Creates PEP 441-compliant zip archives that embed:

1. A ``workflow.json`` manifest with the serialized workflow definition
2. Extracted handler source files for lambda steps (when possible)
3. A ``__main__.py`` entry point that loads and runs the workflow

The resulting ``.pyz`` can be executed with ``python workflow.pyz``
on any machine that has ``spine-core`` installed (pipeline steps
resolve at runtime via the registry).

Limitations:
- Inline lambdas / closures cannot be extracted → warning emitted
- Pipeline steps require the target pipelines installed at runtime
- Choice step conditions are functions → same limitation as lambdas
- Dependencies (numpy, pandas, etc.) are NOT bundled (unlike shiv)
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import tempfile
import textwrap
import zipapp
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spine.core.logging import get_logger

from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

MANIFEST_VERSION = 1
SPINE_PACKAGER_AGENT = "spine-core/packaging"


@dataclass(frozen=True)
class PackageWarning:
    """Warning emitted during packaging (non-fatal)."""

    step_name: str
    message: str
    category: str = "serialization"

    def __str__(self) -> str:
        return f"[{self.category}] step '{self.step_name}': {self.message}"


@dataclass(frozen=True)
class PackageManifest:
    """Metadata about a packaged workflow archive.

    Written as ``workflow.json`` inside the ``.pyz`` and returned
    by :meth:`WorkflowPackager.inspect`.
    """

    workflow_name: str
    workflow_version: int
    step_count: int
    packaged_at: str
    packager_version: int = MANIFEST_VERSION
    handler_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    python_version: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "workflow_name": self.workflow_name,
            "workflow_version": self.workflow_version,
            "step_count": self.step_count,
            "packaged_at": self.packaged_at,
            "packager_version": self.packager_version,
            "handler_files": self.handler_files,
            "warnings": self.warnings,
            "python_version": self.python_version,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackageManifest:
        """Deserialize from dict."""
        return cls(
            workflow_name=data["workflow_name"],
            workflow_version=data["workflow_version"],
            step_count=data["step_count"],
            packaged_at=data["packaged_at"],
            packager_version=data.get("packager_version", 1),
            handler_files=data.get("handler_files", []),
            warnings=data.get("warnings", []),
            python_version=data.get("python_version", ""),
            tags=data.get("tags", []),
        )


# ---------------------------------------------------------------------------
# Handler source extraction
# ---------------------------------------------------------------------------


def _extract_handler_source(handler: Any, step_name: str) -> tuple[str | None, str | None, PackageWarning | None]:
    """Try to extract source code for a callable handler.

    Returns
    -------
    (relative_filename, source_code, warning)
        * If extraction succeeded: (filename, source, None)
        * If extraction failed: (None, None, PackageWarning)
    """
    if handler is None:
        return None, None, None

    # Unwrap functools.wraps / adapt_function wrappers
    unwrapped = inspect.unwrap(handler)

    # Check if it's a real named function (not a lambda expression)
    if getattr(unwrapped, "__name__", "<lambda>") == "<lambda>":
        return None, None, PackageWarning(
            step_name=step_name,
            message="Lambda expression cannot be serialized — step will be skipped at runtime",
        )

    try:
        source = inspect.getsource(unwrapped)
    except (OSError, TypeError):
        return None, None, PackageWarning(
            step_name=step_name,
            message=f"Cannot extract source for {getattr(unwrapped, '__qualname__', '?')} — built-in or C extension",
        )

    # Use the function's qualified name for the filename
    module = getattr(unwrapped, "__module__", "unknown")
    qualname = getattr(unwrapped, "__qualname__", unwrapped.__name__)
    filename = f"handlers/{module.replace('.', '/')}/{qualname.replace('.', '_')}.py"

    return filename, source, None


def _extract_condition_source(condition: Any, step_name: str) -> tuple[str | None, str | None, PackageWarning | None]:
    """Try to extract source for a choice-step condition function."""
    if condition is None:
        return None, None, PackageWarning(
            step_name=step_name,
            message="Choice step has no condition — cannot package",
            category="missing",
        )
    return _extract_handler_source(condition, step_name)


# ---------------------------------------------------------------------------
# __main__.py template
# ---------------------------------------------------------------------------

_MAIN_TEMPLATE = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Auto-generated entry point for packaged workflow: {workflow_name}.

    Execute with:  python {archive_name}
    \"\"\"
    from __future__ import annotations

    import json
    import sys
    from pathlib import Path

    def main() -> int:
        \"\"\"Load and execute the packaged workflow.\"\"\"
        # Load manifest
        manifest_path = Path(__file__).parent / "workflow.json"
        if not manifest_path.exists():
            print("ERROR: workflow.json not found in archive", file=sys.stderr)
            return 1

        data = json.loads(manifest_path.read_text())
        workflow_def = data["workflow"]

        try:
            from spine.orchestration.workflow import Workflow
            from spine.orchestration.workflow_runner import WorkflowRunner
        except ImportError:
            print(
                "ERROR: spine-core is not installed. "
                "Install with: pip install spine-core",
                file=sys.stderr,
            )
            return 1

        # Reconstruct workflow from serialized definition
        workflow = Workflow.from_dict(workflow_def)

        # Parse CLI params (simple key=value pairs)
        params: dict[str, str] = {{}}
        for arg in sys.argv[1:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                params[k] = v

        print(f"Running workflow: {{workflow.name}} v{{workflow.version}}")
        print(f"  Steps: {{len(workflow.steps)}}")
        if params:
            print(f"  Params: {{params}}")
        print()

        runner = WorkflowRunner()
        result = runner.execute(workflow, params=params)

        print(f"\\nWorkflow status: {{result.status.value}}")
        if hasattr(result, "error") and result.error:
            print(f"Error: {{result.error}}", file=sys.stderr)
            return 1

        return 0

    if __name__ == "__main__":
        sys.exit(main())
""")


# ---------------------------------------------------------------------------
# WorkflowPackager
# ---------------------------------------------------------------------------


class WorkflowPackager:
    """Bundle a Workflow into a self-contained .pyz archive.

    The packager serializes a workflow definition, extracts handler
    source code where possible, and uses ``zipapp.create_archive()``
    to produce an executable Python zip archive.

    Example::

        packager = WorkflowPackager()
        path = packager.package(workflow, "output.pyz")
        # Execute: python output.pyz tier=NMS_TIER_1

    Parameters
    ----------
    interpreter : str or None
        Python interpreter shebang for the archive.
        Defaults to ``"/usr/bin/env python3"``.
        Set to ``None`` for no shebang (Windows-friendly).
    """

    def __init__(self, *, interpreter: str | None = "/usr/bin/env python3") -> None:
        self._interpreter = interpreter

    # -- public API ----------------------------------------------------------

    def package(
        self,
        workflow: Workflow,
        output: str | Path,
        *,
        compressed: bool = False,
    ) -> tuple[Path, PackageManifest]:
        """Package a workflow into a .pyz archive.

        Parameters
        ----------
        workflow:
            The workflow to package.
        output:
            Output file path.  ``.pyz`` extension is added if missing.
        compressed:
            If True, use ZIP compression (smaller but slightly slower).

        Returns
        -------
        (path, manifest)
            Path to the created archive and its manifest.

        Raises
        ------
        ValueError
            If the workflow has no steps.
        """
        if not workflow.steps:
            raise ValueError(f"Cannot package workflow '{workflow.name}' — it has no steps")

        output_path = Path(output)
        if output_path.suffix != ".pyz":
            output_path = output_path.with_suffix(".pyz")

        warnings: list[PackageWarning] = []
        handler_files: list[str] = []

        # Serialize workflow
        workflow_dict = workflow.to_dict()

        # Extract handler sources for lambda steps
        handler_sources: dict[str, str] = {}
        for step in workflow.steps:
            if step.step_type == StepType.LAMBDA and step.handler:
                filename, source, warning = _extract_handler_source(step.handler, step.name)
                if warning:
                    warnings.append(warning)
                if filename and source:
                    handler_sources[filename] = source
                    handler_files.append(filename)
            elif step.step_type == StepType.CHOICE and step.condition:
                filename, source, warning = _extract_condition_source(step.condition, step.name)
                if warning:
                    warnings.append(warning)
                if filename and source:
                    handler_sources[filename] = source
                    handler_files.append(filename)

        # Build manifest
        import platform

        manifest = PackageManifest(
            workflow_name=workflow.name,
            workflow_version=workflow.version,
            step_count=len(workflow.steps),
            packaged_at=datetime.now(UTC).isoformat(),
            handler_files=handler_files,
            warnings=[str(w) for w in warnings],
            python_version=platform.python_version(),
            tags=list(workflow.tags),
        )

        # Write archive contents to temp dir
        tmpdir = tempfile.mkdtemp(prefix="spine_pkg_")
        try:
            self._write_archive_contents(tmpdir, workflow_dict, manifest, handler_sources, workflow.name, output_path.name)

            # Create .pyz via zipapp
            zipapp.create_archive(
                tmpdir,
                target=str(output_path),
                interpreter=self._interpreter,
                compressed=compressed,
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        log = logger.bind(
            workflow=workflow.name,
            output=str(output_path),
            size_bytes=output_path.stat().st_size,
            steps=len(workflow.steps),
            handlers=len(handler_files),
            warnings=len(warnings),
        )
        log.info("workflow.packaged")

        return output_path, manifest

    def inspect(self, archive: str | Path) -> PackageManifest:
        """Read the manifest from an existing .pyz archive.

        Parameters
        ----------
        archive:
            Path to the .pyz file to inspect.

        Returns
        -------
        PackageManifest

        Raises
        ------
        FileNotFoundError
            If the archive doesn't exist.
        ValueError
            If the archive doesn't contain a valid manifest.
        """
        import zipfile

        archive_path = Path(archive)
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        with zipfile.ZipFile(archive_path, "r") as zf:
            try:
                raw = zf.read("workflow.json")
            except KeyError:
                raise ValueError(f"No workflow.json in archive: {archive_path}") from None

        data = json.loads(raw)
        return PackageManifest.from_dict(data["manifest"])

    def unpack(self, archive: str | Path, destination: str | Path) -> Path:
        """Extract a .pyz archive to a directory.

        Parameters
        ----------
        archive:
            Path to the .pyz file.
        destination:
            Directory to extract into (created if needed).

        Returns
        -------
        Path to the extraction directory.
        """
        import zipfile

        archive_path = Path(archive)
        dest_path = Path(destination)
        dest_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dest_path)

        logger.info("workflow.unpacked", archive=str(archive_path), destination=str(dest_path))
        return dest_path

    # -- internal helpers ----------------------------------------------------

    def _write_archive_contents(
        self,
        tmpdir: str,
        workflow_dict: dict[str, Any],
        manifest: PackageManifest,
        handler_sources: dict[str, str],
        workflow_name: str,
        archive_name: str,
    ) -> None:
        """Write all files into the temp directory for zipapp."""
        base = Path(tmpdir)

        # 1. workflow.json — contains both manifest and workflow definition
        payload = {
            "manifest": manifest.to_dict(),
            "workflow": workflow_dict,
        }
        (base / "workflow.json").write_text(json.dumps(payload, indent=2, default=str))

        # 2. __main__.py — entry point
        main_content = _MAIN_TEMPLATE.format(
            workflow_name=workflow_name,
            archive_name=archive_name,
        )
        (base / "__main__.py").write_text(main_content)

        # 3. Handler source files
        for rel_path, source in handler_sources.items():
            handler_path = base / rel_path
            handler_path.parent.mkdir(parents=True, exist_ok=True)
            handler_path.write_text(source)

    # -- class helpers -------------------------------------------------------

    @staticmethod
    def can_package_step(step: Step) -> tuple[bool, str]:
        """Check whether a step can be packaged.

        Returns
        -------
        (can_package, reason)
        """
        if step.step_type == StepType.PIPELINE:
            return True, "pipeline steps are resolved by name at runtime"

        if step.step_type == StepType.WAIT:
            return True, "wait steps are fully serializable"

        if step.step_type == StepType.LAMBDA:
            if step.handler is None:
                return False, "lambda step has no handler"
            unwrapped = inspect.unwrap(step.handler)
            if getattr(unwrapped, "__name__", "<lambda>") == "<lambda>":
                return False, "inline lambda expressions cannot be serialized"
            try:
                inspect.getsource(unwrapped)
                return True, "handler source can be extracted"
            except (OSError, TypeError):
                return False, "handler source cannot be extracted (built-in or C extension)"

        if step.step_type == StepType.CHOICE:
            if step.condition is None:
                return False, "choice step has no condition function"
            unwrapped = inspect.unwrap(step.condition)
            if getattr(unwrapped, "__name__", "<lambda>") == "<lambda>":
                return False, "inline lambda condition cannot be serialized"
            try:
                inspect.getsource(unwrapped)
                return True, "condition source can be extracted"
            except (OSError, TypeError):
                return False, "condition source cannot be extracted"

        if step.step_type == StepType.MAP:
            return True, "map steps are serializable (iterator_workflow may need separate packaging)"

        return False, f"unknown step type: {step.step_type}"
