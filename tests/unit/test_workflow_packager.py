"""Tests for WorkflowPackager — .pyz archive creation + inspection."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow

from spine.execution.packaging.packager import (
    PackageManifest,
    PackageWarning,
    WorkflowPackager,
    _extract_handler_source,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _sample_handler(ctx: Any, config: dict[str, Any]) -> StepResult:
    """A named handler that can be extracted by inspect.getsource()."""
    return StepResult.ok(output={"processed": True})


def _another_handler(ctx: Any, config: dict[str, Any]) -> StepResult:
    """Second named handler for multi-step tests."""
    return StepResult.ok(output={"step": "two"})


def _make_operation_workflow() -> Workflow:
    """Workflow with only operation steps — fully serializable."""
    return Workflow(
        name="test.operation_only",
        steps=[
            Step.operation("ingest", "data.ingest"),
            Step.operation("transform", "data.transform"),
            Step.operation("load", "data.load"),
        ],
        domain="testing",
        description="A test workflow with operation steps",
        tags=["test", "packager"],
    )


def _make_lambda_workflow() -> Workflow:
    """Workflow with named lambda steps — source extractable."""
    return Workflow(
        name="test.lambda_steps",
        steps=[
            Step.lambda_("process", _sample_handler),
            Step.lambda_("validate", _another_handler),
        ],
    )


def _make_mixed_workflow() -> Workflow:
    """Workflow mixing operation and lambda steps."""
    return Workflow(
        name="test.mixed",
        steps=[
            Step.operation("ingest", "data.ingest"),
            Step.lambda_("validate", _sample_handler),
            Step.operation("load", "data.load"),
        ],
    )


def _make_inline_lambda_workflow() -> Workflow:
    """Workflow with inline lambda — cannot be serialized."""
    return Workflow(
        name="test.inline_lambda",
        steps=[
            Step.lambda_("bad_step", lambda ctx, cfg: StepResult.ok()),
        ],
    )


# ---------------------------------------------------------------------------
# PackageWarning
# ---------------------------------------------------------------------------


class TestPackageWarning:
    """Tests for PackageWarning dataclass."""

    def test_str_representation(self) -> None:
        w = PackageWarning(step_name="my_step", message="cannot serialize")
        assert "[serialization] step 'my_step': cannot serialize" == str(w)

    def test_custom_category(self) -> None:
        w = PackageWarning(step_name="s1", message="oops", category="runtime")
        assert "[runtime]" in str(w)

    def test_frozen(self) -> None:
        w = PackageWarning(step_name="s", message="m")
        with pytest.raises(AttributeError):
            w.step_name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PackageManifest
# ---------------------------------------------------------------------------


class TestPackageManifest:
    """Tests for PackageManifest serialization."""

    def test_roundtrip(self) -> None:
        m = PackageManifest(
            workflow_name="test.wf",
            workflow_version=2,
            step_count=3,
            packaged_at="2025-01-01T00:00:00+00:00",
            handler_files=["handlers/mod/fn.py"],
            warnings=["warn1"],
            python_version="3.14.0",
            tags=["alpha"],
        )
        d = m.to_dict()
        restored = PackageManifest.from_dict(d)
        assert restored.workflow_name == "test.wf"
        assert restored.workflow_version == 2
        assert restored.step_count == 3
        assert restored.handler_files == ["handlers/mod/fn.py"]
        assert restored.warnings == ["warn1"]
        assert restored.tags == ["alpha"]

    def test_from_dict_defaults(self) -> None:
        d = {
            "workflow_name": "x",
            "workflow_version": 1,
            "step_count": 0,
            "packaged_at": "2025-01-01",
        }
        m = PackageManifest.from_dict(d)
        assert m.handler_files == []
        assert m.warnings == []
        assert m.python_version == ""

    def test_json_serializable(self) -> None:
        m = PackageManifest(
            workflow_name="x",
            workflow_version=1,
            step_count=1,
            packaged_at="now",
        )
        text = json.dumps(m.to_dict())
        assert "x" in text


# ---------------------------------------------------------------------------
# _extract_handler_source
# ---------------------------------------------------------------------------


class TestExtractHandlerSource:
    """Tests for handler source extraction."""

    def test_named_function_extracts(self) -> None:
        filename, source, warning = _extract_handler_source(_sample_handler, "step1")
        assert filename is not None
        assert "def _sample_handler" in source
        assert warning is None

    def test_lambda_emits_warning(self) -> None:
        fn = lambda ctx, cfg: None  # noqa: E731
        filename, source, warning = _extract_handler_source(fn, "step2")
        assert filename is None
        assert source is None
        assert warning is not None
        assert "Lambda expression" in warning.message

    def test_none_handler(self) -> None:
        filename, source, warning = _extract_handler_source(None, "step3")
        assert filename is None
        assert source is None
        assert warning is None

    def test_builtin_emits_warning(self) -> None:
        # Built-in functions can't have source extracted
        filename, source, warning = _extract_handler_source(len, "step4")
        assert filename is None
        assert source is None
        assert warning is not None
        assert "Cannot extract source" in warning.message


# ---------------------------------------------------------------------------
# WorkflowPackager.can_package_step
# ---------------------------------------------------------------------------


class TestCanPackageStep:
    """Tests for the can_package_step static helper."""

    def test_operation_step(self) -> None:
        step = Step.operation("s", "my.operation")
        ok, reason = WorkflowPackager.can_package_step(step)
        assert ok is True
        assert "name at runtime" in reason

    def test_wait_step(self) -> None:
        step = Step.wait("pause", 10)
        ok, reason = WorkflowPackager.can_package_step(step)
        assert ok is True

    def test_named_lambda_step(self) -> None:
        step = Step.lambda_("s", _sample_handler)
        ok, reason = WorkflowPackager.can_package_step(step)
        assert ok is True
        assert "extracted" in reason

    def test_inline_lambda_step(self) -> None:
        step = Step.lambda_("s", lambda ctx, cfg: StepResult.ok())
        ok, reason = WorkflowPackager.can_package_step(step)
        assert ok is False
        assert "inline lambda" in reason

    def test_lambda_step_no_handler(self) -> None:
        step = Step(name="s", step_type=StepType.LAMBDA)
        ok, reason = WorkflowPackager.can_package_step(step)
        assert ok is False
        assert "no handler" in reason


# ---------------------------------------------------------------------------
# WorkflowPackager.package — archive creation
# ---------------------------------------------------------------------------


class TestPackageOperationWorkflow:
    """Tests for packaging operation-only workflows."""

    def test_creates_pyz_file(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, manifest = packager.package(wf, tmp_path / "out.pyz")

        assert output.exists()
        assert output.suffix == ".pyz"
        assert output.stat().st_size > 0

    def test_manifest_fields(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        _, manifest = packager.package(wf, tmp_path / "out.pyz")

        assert manifest.workflow_name == "test.operation_only"
        assert manifest.step_count == 3
        assert manifest.handler_files == []
        assert manifest.warnings == []
        assert manifest.tags == ["test", "packager"]

    def test_archive_contains_expected_files(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, _ = packager.package(wf, tmp_path / "out.pyz")

        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert "__main__.py" in names
            assert "workflow.json" in names

    def test_workflow_json_contents(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, _ = packager.package(wf, tmp_path / "out.pyz")

        with zipfile.ZipFile(output) as zf:
            data = json.loads(zf.read("workflow.json"))

        assert "manifest" in data
        assert "workflow" in data
        assert data["workflow"]["name"] == "test.operation_only"
        assert len(data["workflow"]["steps"]) == 3

    def test_main_py_content(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, _ = packager.package(wf, tmp_path / "out.pyz")

        with zipfile.ZipFile(output) as zf:
            main = zf.read("__main__.py").decode()

        assert "workflow.json" in main
        assert "Workflow.from_dict" in main
        assert "WorkflowRunner" in main

    def test_adds_pyz_extension(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, _ = packager.package(wf, tmp_path / "out")

        assert output.suffix == ".pyz"

    def test_empty_workflow_raises(self, tmp_path: Path) -> None:
        wf = Workflow(name="empty", steps=[])
        packager = WorkflowPackager(interpreter=None)

        with pytest.raises(ValueError, match="no steps"):
            packager.package(wf, tmp_path / "out.pyz")


class TestPackageLambdaWorkflow:
    """Tests for packaging workflows with lambda steps."""

    def test_handler_files_extracted(self, tmp_path: Path) -> None:
        wf = _make_lambda_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, manifest = packager.package(wf, tmp_path / "out.pyz")

        # Named handlers should be extracted
        assert len(manifest.handler_files) == 2
        assert manifest.warnings == []

    def test_handler_source_in_archive(self, tmp_path: Path) -> None:
        wf = _make_lambda_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, manifest = packager.package(wf, tmp_path / "out.pyz")

        with zipfile.ZipFile(output) as zf:
            # Check that handler files exist in the archive
            for handler_file in manifest.handler_files:
                source = zf.read(handler_file).decode()
                assert "def " in source

    def test_inline_lambda_produces_warning(self, tmp_path: Path) -> None:
        wf = _make_inline_lambda_workflow()
        packager = WorkflowPackager(interpreter=None)
        _, manifest = packager.package(wf, tmp_path / "out.pyz")

        assert len(manifest.warnings) == 1
        assert "Lambda expression" in manifest.warnings[0]
        assert manifest.handler_files == []


class TestPackageMixedWorkflow:
    """Tests for workflows mixing operation and lambda steps."""

    def test_mixed_workflow_packages(self, tmp_path: Path) -> None:
        wf = _make_mixed_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, manifest = packager.package(wf, tmp_path / "out.pyz")

        assert output.exists()
        assert manifest.step_count == 3
        # One lambda handler extracted, no warnings
        assert len(manifest.handler_files) == 1
        assert manifest.warnings == []


# ---------------------------------------------------------------------------
# WorkflowPackager.inspect
# ---------------------------------------------------------------------------


class TestInspect:
    """Tests for inspecting existing archives."""

    def test_inspect_roundtrip(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, original = packager.package(wf, tmp_path / "out.pyz")

        inspected = packager.inspect(output)
        assert inspected.workflow_name == original.workflow_name
        assert inspected.workflow_version == original.workflow_version
        assert inspected.step_count == original.step_count

    def test_inspect_nonexistent_raises(self, tmp_path: Path) -> None:
        packager = WorkflowPackager(interpreter=None)
        with pytest.raises(FileNotFoundError):
            packager.inspect(tmp_path / "does_not_exist.pyz")

    def test_inspect_invalid_archive_raises(self, tmp_path: Path) -> None:
        # Create a zip without workflow.json
        bad = tmp_path / "bad.pyz"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("other.txt", "hello")

        packager = WorkflowPackager(interpreter=None)
        with pytest.raises(ValueError, match="No workflow.json"):
            packager.inspect(bad)


# ---------------------------------------------------------------------------
# WorkflowPackager.unpack
# ---------------------------------------------------------------------------


class TestUnpack:
    """Tests for extracting archives."""

    def test_unpack_creates_files(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, _ = packager.package(wf, tmp_path / "out.pyz")

        dest = tmp_path / "unpacked"
        packager.unpack(output, dest)

        assert (dest / "__main__.py").exists()
        assert (dest / "workflow.json").exists()

    def test_unpack_handler_files(self, tmp_path: Path) -> None:
        wf = _make_lambda_workflow()
        packager = WorkflowPackager(interpreter=None)
        output, manifest = packager.package(wf, tmp_path / "out.pyz")

        dest = tmp_path / "unpacked"
        packager.unpack(output, dest)

        for handler_file in manifest.handler_files:
            assert (dest / handler_file).exists()


# ---------------------------------------------------------------------------
# Compressed archive
# ---------------------------------------------------------------------------


class TestCompression:
    """Tests for compressed archives."""

    def test_compressed_flag(self, tmp_path: Path) -> None:
        wf = _make_operation_workflow()
        packager = WorkflowPackager(interpreter=None)

        _, m_plain = packager.package(wf, tmp_path / "plain.pyz", compressed=False)
        _, m_comp = packager.package(wf, tmp_path / "comp.pyz", compressed=True)

        # Both should produce valid archives
        plain_size = (tmp_path / "plain.pyz").stat().st_size
        comp_size = (tmp_path / "comp.pyz").stat().st_size

        # Compressed should be <= plain (may be equal for small files)
        assert comp_size <= plain_size + 50  # small tolerance


# ---------------------------------------------------------------------------
# Interpreter shebang
# ---------------------------------------------------------------------------


class TestInterpreter:
    """Tests for interpreter shebang handling."""

    def test_default_interpreter(self) -> None:
        p = WorkflowPackager()
        assert p._interpreter == "/usr/bin/env python3"

    def test_none_interpreter(self) -> None:
        p = WorkflowPackager(interpreter=None)
        assert p._interpreter is None

    def test_custom_interpreter(self) -> None:
        p = WorkflowPackager(interpreter="/usr/bin/python3.14")
        assert p._interpreter == "/usr/bin/python3.14"
