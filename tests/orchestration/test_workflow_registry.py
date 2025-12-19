"""Tests for the workflow registry — register, lookup, listing, clear.

Covers register_workflow (instance + factory decorator), get_workflow,
list_workflows with domain filter, workflow_exists, clear, and error
handling (WorkflowNotFoundError, duplicate registration, bad type).
"""

from __future__ import annotations

import pytest

from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_registry import (
    WorkflowNotFoundError,
    clear_workflow_registry,
    get_workflow,
    get_workflow_registry_stats,
    list_workflows,
    register_workflow,
    workflow_exists,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure every test starts and ends with a clean registry."""
    clear_workflow_registry()
    yield
    clear_workflow_registry()


def _make_wf(name: str, domain: str | None = None) -> Workflow:
    return Workflow(name=name, steps=[], domain=domain)


# ---------------------------------------------------------------------------
# register_workflow
# ---------------------------------------------------------------------------


class TestRegisterWorkflow:
    def test_register_instance(self):
        wf = _make_wf("my.wf")
        result = register_workflow(wf)
        assert result is wf
        assert workflow_exists("my.wf")

    def test_register_factory(self):
        @register_workflow
        def create_wf():
            return Workflow(name="factory.wf", steps=[])

        # register_workflow returns the Workflow, not the function
        assert isinstance(create_wf, Workflow)
        assert workflow_exists("factory.wf")

    def test_duplicate_raises(self):
        register_workflow(_make_wf("dup"))
        with pytest.raises(ValueError, match="already registered"):
            register_workflow(_make_wf("dup"))

    def test_bad_type_raises(self):
        with pytest.raises(TypeError, match="Expected Workflow"):
            register_workflow("not a workflow")  # type: ignore[arg-type]

    def test_factory_returning_non_workflow_raises(self):
        with pytest.raises(TypeError, match="Expected Workflow"):
            register_workflow(lambda: "not a workflow")


# ---------------------------------------------------------------------------
# get_workflow
# ---------------------------------------------------------------------------


class TestGetWorkflow:
    def test_found(self):
        wf = _make_wf("lookup.wf")
        register_workflow(wf)
        assert get_workflow("lookup.wf") is wf

    def test_not_found_raises(self):
        with pytest.raises(WorkflowNotFoundError) as exc_info:
            get_workflow("no.such.wf")
        assert exc_info.value.workflow_name == "no.such.wf"
        assert "not found" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# list_workflows
# ---------------------------------------------------------------------------


class TestListWorkflows:
    def test_empty(self):
        assert list_workflows() == []

    def test_all(self):
        register_workflow(_make_wf("b.wf"))
        register_workflow(_make_wf("a.wf"))
        names = list_workflows()
        assert names == ["a.wf", "b.wf"]  # sorted

    def test_filter_by_domain(self):
        register_workflow(_make_wf("finra.ingest", domain="finra"))
        register_workflow(_make_wf("finra.score", domain="finra"))
        register_workflow(_make_wf("sec.ingest", domain="sec"))
        assert list_workflows(domain="finra") == ["finra.ingest", "finra.score"]
        assert list_workflows(domain="sec") == ["sec.ingest"]
        assert list_workflows(domain="none") == []


# ---------------------------------------------------------------------------
# workflow_exists
# ---------------------------------------------------------------------------


class TestWorkflowExists:
    def test_exists(self):
        register_workflow(_make_wf("yes"))
        assert workflow_exists("yes") is True

    def test_not_exists(self):
        assert workflow_exists("no") is False


# ---------------------------------------------------------------------------
# clear_workflow_registry
# ---------------------------------------------------------------------------


class TestClearRegistry:
    def test_clear(self):
        register_workflow(_make_wf("temp"))
        clear_workflow_registry()
        assert workflow_exists("temp") is False
        assert list_workflows() == []


# ---------------------------------------------------------------------------
# get_workflow_registry_stats
# ---------------------------------------------------------------------------


class TestRegistryStats:
    def test_empty(self):
        stats = get_workflow_registry_stats()
        assert stats["total_workflows"] == 0

    def test_with_workflows(self):
        register_workflow(_make_wf("a.wf", domain="alpha"))
        register_workflow(_make_wf("b.wf", domain="alpha"))
        register_workflow(_make_wf("c.wf", domain="beta"))
        stats = get_workflow_registry_stats()
        assert stats["total_workflows"] == 3
        assert stats["workflows_by_domain"]["alpha"] == 2
        assert stats["workflows_by_domain"]["beta"] == 1


# ---------------------------------------------------------------------------
# WorkflowNotFoundError
# ---------------------------------------------------------------------------


class TestWorkflowNotFoundError:
    def test_attributes(self):
        register_workflow(_make_wf("kept"))
        try:
            get_workflow("missing")
        except WorkflowNotFoundError as e:
            assert e.workflow_name == "missing"
            assert "kept" in str(e)  # available list includes registered
