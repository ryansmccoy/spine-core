"""Tests for spine.core.config.profiles — TOML profiles with inheritance."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from spine.core.config.profiles import Profile, ProfileManager, _toml_value


# ── _toml_value helper ──────────────────────────────────────────────────


class TestTomlValue:
    def test_bool_true(self):
        assert _toml_value(True) == "true"

    def test_bool_false(self):
        assert _toml_value(False) == "false"

    def test_int(self):
        assert _toml_value(42) == "42"

    def test_string(self):
        assert _toml_value("hello") == "hello"

    def test_list(self):
        assert _toml_value(["a", "b"]) == '["a", "b"]'


# ── Profile dataclass ───────────────────────────────────────────────────


class TestProfile:
    def test_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "test.toml"
        toml_file.write_text(
            '[profile]\nname = "test"\ndescription = "A test"\n\n'
            "database_backend = \"sqlite\"\n\n"
            "[database]\nurl = \"sqlite:///test.db\"\necho = true\n"
        )
        profile = Profile.from_toml(toml_file)
        assert profile.name == "test"
        assert profile.description == "A test"
        assert profile.inherits is None
        assert profile.settings["database_backend"] == "sqlite"
        assert profile.settings["database"]["url"] == "sqlite:///test.db"

    def test_from_toml_with_inherits(self, tmp_path: Path):
        toml_file = tmp_path / "child.toml"
        toml_file.write_text('[profile]\nname = "child"\ninherits = "parent"\n')
        profile = Profile.from_toml(toml_file)
        assert profile.inherits == "parent"

    def test_to_env_dict_flat(self, tmp_path: Path):
        p = Profile(name="test", path=tmp_path / "test.toml", settings={"database_backend": "sqlite"})
        env = p.to_env_dict()
        assert env == {"SPINE_DATABASE_BACKEND": "sqlite"}

    def test_to_env_dict_nested(self, tmp_path: Path):
        p = Profile(
            name="test",
            path=tmp_path / "test.toml",
            settings={"database": {"url": "sqlite:///x.db", "echo": True}},
        )
        env = p.to_env_dict()
        assert env["SPINE_DATABASE_URL"] == "sqlite:///x.db"
        assert env["SPINE_DATABASE_ECHO"] == "true"


# ── ProfileManager ──────────────────────────────────────────────────────


@pytest.fixture
def profile_dirs(tmp_path: Path):
    """Create project and user profile directories with sample profiles."""
    project_dir = tmp_path / "project" / ".spine" / "profiles"
    user_dir = tmp_path / "user" / "profiles"
    project_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)

    # Project profiles
    (project_dir / "dev.toml").write_text(
        '[profile]\nname = "dev"\ndescription = "Development"\n\n'
        'database_backend = "sqlite"\n'
    )
    (project_dir / "staging.toml").write_text(
        '[profile]\nname = "staging"\ninherits = "dev"\ndescription = "Staging"\n\n'
        'database_backend = "postgres"\n'
    )

    # User profile
    (user_dir / "global.toml").write_text(
        '[profile]\nname = "global"\ndescription = "Global user profile"\n\n'
        '[logging]\nlevel = "WARNING"\n'
    )

    return tmp_path / "project", user_dir


class TestProfileManager:
    def test_list_profiles_all(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        profiles = mgr.list_profiles()
        names = {p.name for p in profiles}
        assert names == {"dev", "staging", "global"}

    def test_list_profiles_project(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        profiles = mgr.list_profiles(scope="project")
        names = {p.name for p in profiles}
        assert names == {"dev", "staging"}

    def test_list_profiles_user(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        profiles = mgr.list_profiles(scope="user")
        names = {p.name for p in profiles}
        assert names == {"global"}

    def test_get_profile_project_wins(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        p = mgr.get_profile("dev")
        assert p is not None
        assert p.name == "dev"

    def test_get_profile_user_fallback(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        p = mgr.get_profile("global")
        assert p is not None
        assert p.name == "global"

    def test_get_profile_not_found(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        assert mgr.get_profile("nonexistent") is None

    def test_resolve_profile_simple(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        env = mgr.resolve_profile("dev")
        assert env["SPINE_DATABASE_BACKEND"] == "sqlite"

    def test_resolve_profile_inheritance(self, profile_dirs):
        project_root, user_dir = profile_dirs
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        env = mgr.resolve_profile("staging")
        # staging inherits from dev but overrides database_backend
        assert env["SPINE_DATABASE_BACKEND"] == "postgres"

    def test_resolve_circular_inheritance_raises(self, tmp_path: Path):
        profiles_dir = tmp_path / ".spine" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "a.toml").write_text('[profile]\nname = "a"\ninherits = "b"\n')
        (profiles_dir / "b.toml").write_text('[profile]\nname = "b"\ninherits = "a"\n')
        mgr = ProfileManager(project_root=tmp_path)
        with pytest.raises(ValueError, match="Circular"):
            mgr.resolve_profile("a")

    def test_resolve_not_found_raises(self, tmp_path: Path):
        mgr = ProfileManager(project_root=tmp_path)
        with pytest.raises(ValueError, match="not found"):
            mgr.resolve_profile("nonexistent")


class TestProfileManagerMutation:
    def test_create_profile(self, tmp_path: Path):
        mgr = ProfileManager(project_root=tmp_path)
        p = mgr.create_profile("new-profile", description="Test")
        assert p.name == "new-profile"
        assert p.path.exists()

    def test_create_profile_duplicate_raises(self, tmp_path: Path):
        mgr = ProfileManager(project_root=tmp_path)
        mgr.create_profile("dup")
        with pytest.raises(FileExistsError):
            mgr.create_profile("dup")

    def test_delete_profile(self, tmp_path: Path):
        mgr = ProfileManager(project_root=tmp_path)
        mgr.create_profile("to-delete")
        assert mgr.delete_profile("to-delete") is True
        assert mgr.get_profile("to-delete") is None

    def test_delete_profile_not_found(self, tmp_path: Path):
        mgr = ProfileManager(project_root=tmp_path)
        assert mgr.delete_profile("ghost") is False

    def test_set_default_profile(self, tmp_path: Path):
        mgr = ProfileManager(project_root=tmp_path)
        mgr.create_profile("default-test")
        mgr.set_default_profile("default-test", scope="project")

        config_path = tmp_path / ".spine" / "config.toml"
        assert config_path.exists()
        assert 'default-test' in config_path.read_text()


class TestGetActiveProfile:
    def test_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_PROFILE", "from-env")
        mgr = ProfileManager(project_root=tmp_path)
        assert mgr.get_active_profile() == "from-env"

    def test_project_config(self, tmp_path: Path):
        config_dir = tmp_path / ".spine"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text('default_profile = "staging"\n')
        mgr = ProfileManager(project_root=tmp_path)
        assert mgr.get_active_profile() == "staging"

    def test_no_active(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPINE_PROFILE", raising=False)
        mgr = ProfileManager(project_root=tmp_path)
        assert mgr.get_active_profile() is None


class TestGetEffectiveSettings:
    def test_env_overrides_profile(self, profile_dirs, monkeypatch: pytest.MonkeyPatch):
        project_root, user_dir = profile_dirs
        monkeypatch.setenv("SPINE_DATABASE_BACKEND", "overridden")
        mgr = ProfileManager(project_root=project_root, user_dir=user_dir)
        resolved = mgr.get_effective_settings("dev")
        assert resolved["SPINE_DATABASE_BACKEND"] == "overridden"
