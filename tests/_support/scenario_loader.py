"""
Scenario loader — single source of truth for all test layers.

Loads scenario fixtures from ``scenarios/scenarios.json`` and provides
typed helpers for each test layer to interpret them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios"
SCENARIOS_FILE = SCENARIOS_DIR / "scenarios.json"


@dataclass
class FaultInjection:
    step: str = ""
    error_type: str = ""
    error_message: str = ""
    delay_ms: int = 0


@dataclass
class Scenario:
    """Single test scenario — used across all test layers."""

    id: str
    name: str
    description: str = ""
    category: str = ""
    kind: str | None = None
    workflow: str | None = None

    # Submission payloads
    submit: dict[str, Any] | None = None
    trigger_workflow: dict[str, Any] | None = None
    lookup_run_id: str | None = None
    schedule: dict[str, Any] | None = None
    endpoints: list[dict[str, Any]] = field(default_factory=list)

    # Actions
    actions: list[str] = field(default_factory=list)
    pre_actions: list[str] = field(default_factory=list)
    duplicate_submit: bool = False
    setup_runs: int = 0

    # Fault injection
    fault_injection: FaultInjection | None = None

    # Expectations
    expected: dict[str, Any] = field(default_factory=dict)
    ui: dict[str, Any] = field(default_factory=dict)

    @property
    def is_submit(self) -> bool:
        return self.submit is not None

    @property
    def is_workflow_trigger(self) -> bool:
        return self.trigger_workflow is not None

    @property
    def is_schedule(self) -> bool:
        return self.schedule is not None

    @property
    def is_contract_test(self) -> bool:
        return len(self.endpoints) > 0


def load_scenarios(path: Path | None = None) -> list[Scenario]:
    """Load all scenarios from the JSON fixtures file."""
    p = path or SCENARIOS_FILE
    if not p.exists():
        raise FileNotFoundError(f"Scenarios file not found: {p}")

    raw = json.loads(p.read_text(encoding="utf-8"))
    scenarios: list[Scenario] = []

    for item in raw:
        fi = None
        if item.get("fault_injection"):
            fi = FaultInjection(**item["fault_injection"])

        scenarios.append(
            Scenario(
                id=item["id"],
                name=item["name"],
                description=item.get("description", ""),
                category=item.get("category", ""),
                kind=item.get("kind"),
                workflow=item.get("workflow"),
                submit=item.get("submit"),
                trigger_workflow=item.get("trigger_workflow"),
                lookup_run_id=item.get("lookup_run_id"),
                schedule=item.get("schedule"),
                endpoints=item.get("endpoints", []),
                actions=item.get("actions", []),
                pre_actions=item.get("pre_actions", []),
                duplicate_submit=item.get("duplicate_submit", False),
                setup_runs=item.get("setup_runs", 0),
                fault_injection=fi,
                expected=item.get("expected", {}),
                ui=item.get("ui", {}),
            )
        )

    return scenarios


def get_scenario(scenario_id: str) -> Scenario:
    """Load a single scenario by ID."""
    for s in load_scenarios():
        if s.id == scenario_id:
            return s
    raise KeyError(f"Scenario '{scenario_id}' not found")


def scenarios_by_category(category: str) -> list[Scenario]:
    """Filter scenarios by category (happy_path, error, edge_case, etc.)."""
    return [s for s in load_scenarios() if s.category == category]
