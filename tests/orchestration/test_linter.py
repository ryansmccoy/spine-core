"""Tests for Workflow Linter — static analysis for workflows.

Covers:
- LintDiagnostic creation and string representation
- LintResult aggregation, filtering, summary
- All built-in rules (E001–E004, W001–W004, I001–I002)
- Custom rule registration and execution
- Edge cases (empty, single-step, large workflows)
"""

from __future__ import annotations

import pytest

from spine.orchestration import Step, StepResult, Workflow
from spine.orchestration.linter import (
    LintDiagnostic,
    LintResult,
    Severity,
    clear_custom_rules,
    lint_workflow,
    list_lint_rules,
    register_lint_rule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(ctx, config):
    return StepResult.ok()


def _cond_true(ctx):
    return True


def _make_clean_workflow(name="test.clean"):
    """A workflow that should pass all lint rules cleanly."""
    return Workflow(
        name=name,
        steps=[
            Step.operation("ingest", "domain.ingest"),
            Step.lambda_("validate", _noop),
            Step.operation("store", "domain.store"),
        ],
    )


# ---------------------------------------------------------------------------
# LintDiagnostic
# ---------------------------------------------------------------------------

class TestLintDiagnostic:
    def test_creation(self):
        d = LintDiagnostic(
            code="E001",
            severity=Severity.ERROR,
            message="No steps.",
        )
        assert d.code == "E001"
        assert d.severity == Severity.ERROR
        assert d.message == "No steps."
        assert d.step_name is None
        assert d.suggestion is None

    def test_creation_with_all_fields(self):
        d = LintDiagnostic(
            code="W002",
            severity=Severity.WARNING,
            message="Unreachable.",
            step_name="orphan",
            suggestion="Remove it.",
        )
        assert d.step_name == "orphan"
        assert d.suggestion == "Remove it."

    def test_str_no_step(self):
        d = LintDiagnostic(code="E001", severity=Severity.ERROR, message="Empty.")
        s = str(d)
        assert "[E001]" in s
        assert "ERROR" in s
        assert "Empty." in s

    def test_str_with_step_and_suggestion(self):
        d = LintDiagnostic(
            code="W001", severity=Severity.WARNING,
            message="Missing else.", step_name="route",
            suggestion="Add else_step.",
        )
        s = str(d)
        assert "route" in s
        assert "Add else_step." in s

    def test_frozen(self):
        d = LintDiagnostic(code="E001", severity=Severity.ERROR, message="x")
        with pytest.raises(AttributeError):
            d.code = "E002"


# ---------------------------------------------------------------------------
# LintResult
# ---------------------------------------------------------------------------

class TestLintResult:
    def test_empty_result_passes(self):
        r = LintResult(workflow_name="test")
        assert r.passed is True
        assert r.errors == []
        assert r.warnings == []
        assert r.infos == []

    def test_with_errors_fails(self):
        r = LintResult(
            workflow_name="test",
            diagnostics=[
                LintDiagnostic(code="E001", severity=Severity.ERROR, message="bad"),
            ],
        )
        assert r.passed is False
        assert len(r.errors) == 1

    def test_warnings_only_passes(self):
        r = LintResult(
            workflow_name="test",
            diagnostics=[
                LintDiagnostic(code="W001", severity=Severity.WARNING, message="meh"),
            ],
        )
        assert r.passed is True
        assert len(r.warnings) == 1

    def test_filtering(self):
        r = LintResult(
            workflow_name="test",
            diagnostics=[
                LintDiagnostic(code="E001", severity=Severity.ERROR, message="a"),
                LintDiagnostic(code="W001", severity=Severity.WARNING, message="b"),
                LintDiagnostic(code="I001", severity=Severity.INFO, message="c"),
                LintDiagnostic(code="E002", severity=Severity.ERROR, message="d"),
            ],
        )
        assert len(r.errors) == 2
        assert len(r.warnings) == 1
        assert len(r.infos) == 1

    def test_summary_pass(self):
        r = LintResult(workflow_name="my.wf")
        s = r.summary()
        assert "PASS" in s
        assert "my.wf" in s

    def test_summary_fail(self):
        r = LintResult(
            workflow_name="bad.wf",
            diagnostics=[
                LintDiagnostic(code="E001", severity=Severity.ERROR, message="x"),
            ],
        )
        s = r.summary()
        assert "FAIL" in s
        assert "1 errors" in s

    def test_str_includes_diagnostics(self):
        r = LintResult(
            workflow_name="x",
            diagnostics=[
                LintDiagnostic(code="E001", severity=Severity.ERROR, message="empty"),
            ],
        )
        output = str(r)
        assert "[E001]" in output
        assert "empty" in output


# ---------------------------------------------------------------------------
# Built-in Rules
# ---------------------------------------------------------------------------

class TestCheckEmptyWorkflow:
    """E001: Workflow has no steps."""

    def test_triggers_on_empty(self):
        # Workflow.__post_init__ doesn't block empty steps, but let's
        # build one carefully to avoid other validation.
        wf = Workflow.__new__(Workflow)
        wf.name = "empty"
        wf.steps = []
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        from spine.orchestration.workflow import WorkflowExecutionPolicy
        wf.execution_policy = WorkflowExecutionPolicy()

        result = lint_workflow(wf)
        codes = [d.code for d in result.diagnostics]
        assert "E001" in codes

    def test_clean_workflow_no_e001(self):
        wf = _make_clean_workflow()
        result = lint_workflow(wf)
        codes = [d.code for d in result.diagnostics]
        assert "E001" not in codes


class TestCheckMissingHandlers:
    """E002: Lambda step has no handler."""

    def test_triggers_on_none_handler(self):
        # Build step with handler=None
        step = Step.lambda_("bad_step", _noop)
        step.handler = None  # Simulate missing handler
        wf = Workflow(name="test.missing_handler", steps=[step])

        result = lint_workflow(wf)
        e002 = [d for d in result.diagnostics if d.code == "E002"]
        assert len(e002) == 1
        assert e002[0].step_name == "bad_step"

    def test_valid_handler_no_e002(self):
        wf = _make_clean_workflow()
        result = lint_workflow(wf)
        codes = [d.code for d in result.diagnostics]
        assert "E002" not in codes


class TestCheckChoiceCompleteness:
    """W001: Choice step missing else_step."""

    def test_missing_else_triggers_w001(self):
        wf = Workflow(
            name="test.choice",
            steps=[
                Step.choice("decide", condition=_cond_true, then_step="do_it"),
                Step.lambda_("do_it", _noop),
            ],
        )
        result = lint_workflow(wf)
        w001 = [d for d in result.diagnostics if d.code == "W001"]
        assert len(w001) == 1

    def test_complete_choice_no_w001(self):
        wf = Workflow(
            name="test.choice_ok",
            steps=[
                Step.choice("decide", condition=_cond_true, then_step="a", else_step="b"),
                Step.lambda_("a", _noop),
                Step.lambda_("b", _noop),
            ],
        )
        result = lint_workflow(wf)
        w001 = [d for d in result.diagnostics if d.code == "W001"]
        assert len(w001) == 0


class TestCheckDeepChains:
    """W003: Workflow exceeds step depth threshold."""

    def test_triggers_on_deep_chain(self):
        steps = [Step.lambda_(f"step_{i}", _noop) for i in range(25)]
        wf = Workflow(name="test.deep", steps=steps)

        result = lint_workflow(wf)
        w003 = [d for d in result.diagnostics if d.code == "W003"]
        assert len(w003) == 1
        assert "25" in w003[0].message

    def test_short_chain_no_w003(self):
        wf = _make_clean_workflow()
        result = lint_workflow(wf)
        codes = [d.code for d in result.diagnostics]
        assert "W003" not in codes


class TestCheckOperationNaming:
    """I001: Operation name doesn't use dotted convention."""

    def test_undotted_name_triggers_i001(self):
        wf = Workflow(
            name="test.naming",
            steps=[Step.operation("fetch", "fetch_data")],
        )
        result = lint_workflow(wf)
        i001 = [d for d in result.diagnostics if d.code == "I001"]
        assert len(i001) == 1
        assert "fetch_data" in i001[0].message

    def test_dotted_name_no_i001(self):
        wf = Workflow(
            name="test.naming_ok",
            steps=[Step.operation("fetch", "finra.fetch_data")],
        )
        result = lint_workflow(wf)
        i001 = [d for d in result.diagnostics if d.code == "I001"]
        assert len(i001) == 0

    def test_infos_suppressed(self):
        wf = Workflow(
            name="test.naming",
            steps=[Step.operation("fetch", "fetch_data")],
        )
        result = lint_workflow(wf, include_infos=False)
        assert not any(d.severity == Severity.INFO for d in result.diagnostics)


class TestCheckSimilarNames:
    """W004: Step names are suspiciously similar."""

    def test_similar_names_trigger_w004(self):
        wf = Workflow(
            name="test.similar",
            steps=[
                Step.lambda_("validate_data", _noop),
                Step.lambda_("validate_date", _noop),
            ],
        )
        result = lint_workflow(wf)
        w004 = [d for d in result.diagnostics if d.code == "W004"]
        assert len(w004) == 1

    def test_distinct_names_no_w004(self):
        wf = _make_clean_workflow()
        result = lint_workflow(wf)
        codes = [d.code for d in result.diagnostics]
        assert "W004" not in codes


class TestCheckMissingOperationName:
    """E004: Operation step has no operation_name."""

    def test_triggers_on_empty_operation_name(self):
        step = Step.operation("fetch", "placeholder")
        step.operation_name = ""  # Simulate empty operation name
        wf = Workflow(name="test.no_pipe", steps=[step])

        result = lint_workflow(wf)
        e004 = [d for d in result.diagnostics if d.code == "E004"]
        assert len(e004) == 1


class TestCheckSingleStepWorkflow:
    """I002: Workflow has only one step."""

    def test_single_step_triggers_i002(self):
        wf = Workflow(
            name="test.single",
            steps=[Step.operation("only", "domain.action")],
        )
        result = lint_workflow(wf)
        i002 = [d for d in result.diagnostics if d.code == "I002"]
        assert len(i002) == 1

    def test_multi_step_no_i002(self):
        wf = _make_clean_workflow()
        result = lint_workflow(wf)
        codes = [d.code for d in result.diagnostics]
        assert "I002" not in codes


# ---------------------------------------------------------------------------
# Custom Rules
# ---------------------------------------------------------------------------

class TestCustomRules:
    def setup_method(self):
        clear_custom_rules()

    def teardown_method(self):
        clear_custom_rules()

    def test_register_and_run_custom_rule(self):
        def custom_rule(workflow):
            if "test" in workflow.name:
                return [LintDiagnostic(code="C001", severity=Severity.WARNING, message="Has 'test' in name")]
            return []

        register_lint_rule("custom_test_check", custom_rule)

        wf = _make_clean_workflow(name="test.my_workflow")
        result = lint_workflow(wf)
        c001 = [d for d in result.diagnostics if d.code == "C001"]
        assert len(c001) == 1

    def test_list_rules_includes_custom(self):
        register_lint_rule("my_rule", lambda wf: [])
        rules = list_lint_rules()
        assert "my_rule" in rules

    def test_clear_custom_rules(self):
        register_lint_rule("temp", lambda wf: [])
        clear_custom_rules()
        rules = list_lint_rules()
        assert "temp" not in rules

    def test_extra_rules_parameter(self):
        def one_shot(workflow):
            return [LintDiagnostic(code="Z001", severity=Severity.INFO, message="one-shot")]

        wf = _make_clean_workflow()
        result = lint_workflow(wf, extra_rules=[one_shot])
        z001 = [d for d in result.diagnostics if d.code == "Z001"]
        assert len(z001) == 1

    def test_failing_rule_doesnt_crash(self):
        def bad_rule(workflow):
            raise RuntimeError("kaboom")

        register_lint_rule("bad_rule", bad_rule)
        wf = _make_clean_workflow()
        result = lint_workflow(wf)
        x001 = [d for d in result.diagnostics if d.code == "X001"]
        assert len(x001) == 1
        assert "bad_rule" in x001[0].message


# ---------------------------------------------------------------------------
# Clean workflow — no false positives
# ---------------------------------------------------------------------------

class TestCleanWorkflow:
    def test_clean_workflow_passes(self):
        wf = _make_clean_workflow()
        result = lint_workflow(wf, include_infos=False)
        assert result.passed
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_lint_workflow_returns_correct_name(self):
        wf = _make_clean_workflow(name="finra.daily")
        result = lint_workflow(wf)
        assert result.workflow_name == "finra.daily"


# ---------------------------------------------------------------------------
# Rule listing
# ---------------------------------------------------------------------------

class TestRuleListing:
    def test_built_in_rules_present(self):
        rules = list_lint_rules()
        assert "check_empty_workflow" in rules
        assert "check_missing_handlers" in rules
        assert "check_operation_naming" in rules
        assert len(rules) >= 9  # At least the 9 built-in rules
