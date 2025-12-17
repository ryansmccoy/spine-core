"""Tests for spine.core.config.loader — env file discovery and parsing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from spine.core.config.loader import (
    _parse_env_file,
    discover_env_files,
    find_project_root,
    get_effective_env,
    load_env_files,
)


# ── find_project_root ────────────────────────────────────────────────────


class TestFindProjectRoot:
    def test_finds_pyproject_toml(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").touch()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert find_project_root(sub) == tmp_path

    def test_finds_git_dir(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        assert find_project_root(tmp_path) == tmp_path

    def test_finds_setup_py(self, tmp_path: Path):
        (tmp_path / "setup.py").touch()
        assert find_project_root(tmp_path) == tmp_path

    def test_fallback_to_start(self, tmp_path: Path):
        """No markers found → return start directory."""
        sub = tmp_path / "nomarkers"
        sub.mkdir()
        result = find_project_root(sub)
        assert result == sub


# ── discover_env_files ───────────────────────────────────────────────────


class TestDiscoverEnvFiles:
    def test_empty_directory(self, tmp_path: Path):
        assert discover_env_files(tmp_path) == []

    def test_base_only(self, tmp_path: Path):
        (tmp_path / ".env.base").write_text("X=1")
        files = discover_env_files(tmp_path)
        assert files == [tmp_path / ".env.base"]

    def test_tier_files(self, tmp_path: Path):
        (tmp_path / ".env.base").write_text("X=1")
        (tmp_path / ".env.minimal").write_text("Y=2")
        files = discover_env_files(tmp_path, tier="minimal")
        assert len(files) == 2
        assert files[0].name == ".env.base"
        assert files[1].name == ".env.minimal"

    def test_full_cascade(self, tmp_path: Path):
        for name in [".env.base", ".env.standard", ".env.local", ".env"]:
            (tmp_path / name).write_text(f"FROM={name}")
        files = discover_env_files(tmp_path, tier="standard")
        names = [f.name for f in files]
        assert names == [".env.base", ".env.standard", ".env.local", ".env"]

    def test_tier_from_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / ".env.full").write_text("X=1")
        monkeypatch.setenv("SPINE_TIER", "full")
        files = discover_env_files(tmp_path)
        assert any(f.name == ".env.full" for f in files)


# ── _parse_env_file ─────────────────────────────────────────────────────


class TestParseEnvFile:
    def test_simple_key_value(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("KEY=value\n")
        assert _parse_env_file(f) == {"KEY": "value"}

    def test_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("# comment\n\nKEY=value\n")
        assert _parse_env_file(f) == {"KEY": "value"}

    def test_double_quoted(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text('KEY="hello world"\n')
        assert _parse_env_file(f) == {"KEY": "hello world"}

    def test_single_quoted(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("KEY='hello world'\n")
        assert _parse_env_file(f) == {"KEY": "hello world"}

    def test_export_prefix(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("export KEY=value\n")
        assert _parse_env_file(f) == {"KEY": "value"}

    def test_inline_comment(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("KEY=value # comment\n")
        assert _parse_env_file(f) == {"KEY": "value"}

    def test_equals_in_value(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("URL=postgres://user:pass@host:5432/db\n")
        result = _parse_env_file(f)
        assert result["URL"] == "postgres://user:pass@host:5432/db"

    def test_whitespace_around_equals(self, tmp_path: Path):
        f = tmp_path / ".env"
        f.write_text("KEY = value\n")
        assert _parse_env_file(f) == {"KEY": "value"}


# ── load_env_files ──────────────────────────────────────────────────────


class TestLoadEnvFiles:
    def test_merge_override(self, tmp_path: Path):
        """Later files override earlier values."""
        f1 = tmp_path / ".env.base"
        f2 = tmp_path / ".env.local"
        f1.write_text("A=1\nB=base")
        f2.write_text("B=local\nC=3")
        result = load_env_files([f1, f2])
        assert result == {"A": "1", "B": "local", "C": "3"}


# ── get_effective_env ────────────────────────────────────────────────────


class TestGetEffectiveEnv:
    def test_env_vars_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / ".env.base").write_text("SPINE_LOG_LEVEL=INFO")
        monkeypatch.setenv("SPINE_LOG_LEVEL", "DEBUG")
        result = get_effective_env(tmp_path)
        assert result["SPINE_LOG_LEVEL"] == "DEBUG"
