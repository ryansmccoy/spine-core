"""
Test support utilities for spine-core tests.

This module provides helper functions and utilities that don't fit
as pytest fixtures but are useful across multiple test files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_yaml_fixture(fixtures_dir: Path, *path_parts: str) -> dict[str, Any]:
    """
    Load a YAML fixture file.
    
    Args:
        fixtures_dir: Base fixtures directory path
        *path_parts: Path components relative to fixtures_dir
        
    Returns:
        Parsed YAML as dictionary
        
    Raises:
        FileNotFoundError: If fixture file doesn't exist
    """
    fixture_path = fixtures_dir.joinpath(*path_parts)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json_fixture(fixtures_dir: Path, *path_parts: str) -> dict[str, Any]:
    """
    Load a JSON fixture file.
    
    Args:
        fixtures_dir: Base fixtures directory path
        *path_parts: Path components relative to fixtures_dir
        
    Returns:
        Parsed JSON as dictionary
    """
    fixture_path = fixtures_dir.joinpath(*path_parts)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_temp_yaml(temp_dir: Path, name: str, content: dict[str, Any]) -> Path:
    """
    Write a dictionary to a temporary YAML file.
    
    Args:
        temp_dir: Temporary directory path
        name: Filename (without extension)
        content: Dictionary to serialize
        
    Returns:
        Path to created file
    """
    file_path = temp_dir / f"{name}.yaml"
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(content, f, default_flow_style=False)
    return file_path


def assert_dict_subset(actual: dict, expected: dict, path: str = "") -> None:
    """
    Assert that expected is a subset of actual (recursive).
    
    Useful for partial matching in golden tests where not all
    fields need to be checked.
    
    Args:
        actual: The full dictionary
        expected: The expected subset
        path: Current path (for error messages)
    """
    for key, expected_value in expected.items():
        current_path = f"{path}.{key}" if path else key
        
        assert key in actual, f"Missing key at {current_path}"
        actual_value = actual[key]
        
        if isinstance(expected_value, dict) and isinstance(actual_value, dict):
            assert_dict_subset(actual_value, expected_value, current_path)
        elif isinstance(expected_value, list) and isinstance(actual_value, list):
            assert len(actual_value) >= len(expected_value), (
                f"List at {current_path} too short: "
                f"expected at least {len(expected_value)}, got {len(actual_value)}"
            )
            for i, (exp_item, act_item) in enumerate(zip(expected_value, actual_value)):
                if isinstance(exp_item, dict) and isinstance(act_item, dict):
                    assert_dict_subset(act_item, exp_item, f"{current_path}[{i}]")
                else:
                    assert act_item == exp_item, (
                        f"Mismatch at {current_path}[{i}]: "
                        f"expected {exp_item!r}, got {act_item!r}"
                    )
        else:
            assert actual_value == expected_value, (
                f"Mismatch at {current_path}: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )


class StepOrderValidator:
    """
    Validates topological ordering of pipeline steps.
    
    Usage:
        validator = StepOrderValidator(plan.steps)
        validator.assert_before("ingest", "normalize")
        validator.assert_order(["ingest", "normalize", "aggregate"])
    """
    
    def __init__(self, steps: list) -> None:
        self.step_names = [s.step_name for s in steps]
        self._index = {name: i for i, name in enumerate(self.step_names)}
    
    def get_index(self, step_name: str) -> int:
        """Get the index of a step in the execution order."""
        if step_name not in self._index:
            raise ValueError(f"Step '{step_name}' not found in plan")
        return self._index[step_name]
    
    def assert_before(self, first: str, second: str) -> None:
        """Assert that first step comes before second step."""
        first_idx = self.get_index(first)
        second_idx = self.get_index(second)
        assert first_idx < second_idx, (
            f"Expected '{first}' (index {first_idx}) before "
            f"'{second}' (index {second_idx}), order: {self.step_names}"
        )
    
    def assert_order(self, expected: list[str]) -> None:
        """Assert that steps appear in the expected order."""
        indices = [self.get_index(name) for name in expected]
        assert indices == sorted(indices), (
            f"Steps not in expected order: expected {expected}, "
            f"but indices are {indices}, full order: {self.step_names}"
        )
    
    def assert_exact_order(self, expected: list[str]) -> None:
        """Assert that the step order matches exactly."""
        assert self.step_names == expected, (
            f"Step order mismatch:\n"
            f"  Expected: {expected}\n"
            f"  Actual:   {self.step_names}"
        )
