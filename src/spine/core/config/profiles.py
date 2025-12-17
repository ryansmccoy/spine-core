"""
TOML-based configuration profiles with inheritance.

Profiles live in ``~/.spine/profiles/`` (user scope) or
``<project>/.spine/profiles/`` (project scope).  Project-scoped
profiles take precedence over user-scoped ones.

Example profile (``dev.toml``)::

    [profile]
    name = "dev"
    description = "Local development"
    inherits = ""          # or another profile name

    database_backend = "sqlite"
    scheduler_backend = "thread"

    [database]
    url = "sqlite:///data/spine-dev.db"
    echo = true

    [logging]
    level = "DEBUG"
    format = "console"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Profile:
    """A single configuration profile parsed from a TOML file."""

    name: str
    path: Path
    inherits: str | None = None
    description: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    # ── Factories ────────────────────────────────────────────────

    @classmethod
    def from_toml(cls, path: Path) -> Profile:
        """Load a profile from a ``.toml`` file."""
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        meta = data.pop("profile", {})
        return cls(
            name=meta.get("name", path.stem),
            path=path,
            inherits=meta.get("inherits") or None,
            description=meta.get("description"),
            settings={**{k: v for k, v in meta.items() if k not in ("name", "inherits", "description")}, **data},
        )

    # ── Conversion ───────────────────────────────────────────────

    def to_env_dict(self) -> dict[str, str]:
        """Flatten profile settings into ``SPINE_*`` env-var style.

        Nested sections are joined with ``_``::

            [database]
            pool_size = 10   →   SPINE_DATABASE_POOL_SIZE=10
        """
        result: dict[str, str] = {}
        for key, value in self.settings.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    env_key = f"SPINE_{key}_{subkey}".upper()
                    result[env_key] = _toml_value(subvalue)
            else:
                env_key = f"SPINE_{key}".upper()
                result[env_key] = _toml_value(value)
        return result


def _toml_value(value: Any) -> str:
    """Convert a TOML value to a string suitable for env vars."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        import json
        return json.dumps(value)
    return str(value)


# ── Profile Manager ──────────────────────────────────────────────────────


class ProfileManager:
    """Discover, resolve, and manage TOML profiles.

    Parameters
    ----------
    project_root:
        Project directory containing ``.spine/profiles/``.
    user_dir:
        User-level profile directory (default ``~/.spine/profiles``).
    """

    def __init__(
        self,
        project_root: Path | None = None,
        user_dir: Path | None = None,
    ):
        self._project_root = (project_root or Path.cwd()).resolve()
        self._user_dir = (user_dir or Path.home() / ".spine" / "profiles").resolve()

    @property
    def project_profile_dir(self) -> Path:
        return self._project_root / ".spine" / "profiles"

    @property
    def user_profile_dir(self) -> Path:
        return self._user_dir

    # ── Discovery ────────────────────────────────────────────────

    def list_profiles(self, scope: str = "all") -> list[Profile]:
        """List available profiles.

        Parameters
        ----------
        scope:
            ``"all"`` (default), ``"user"``, or ``"project"``.
        """
        profiles: list[Profile] = []
        seen: set[str] = set()

        if scope in ("all", "project"):
            for p in self._scan_dir(self.project_profile_dir):
                profiles.append(p)
                seen.add(p.name)

        if scope in ("all", "user"):
            for p in self._scan_dir(self.user_profile_dir):
                if p.name not in seen:
                    profiles.append(p)

        return profiles

    def _scan_dir(self, directory: Path) -> list[Profile]:
        """Scan a directory for ``.toml`` profile files."""
        if not directory.is_dir():
            return []
        return [Profile.from_toml(f) for f in sorted(directory.glob("*.toml")) if f.stem != "config"]

    # ── Lookup ───────────────────────────────────────────────────

    def get_profile(self, name: str) -> Profile | None:
        """Get a profile by name.  Project scope wins over user scope."""
        # Project scope first
        path = self.project_profile_dir / f"{name}.toml"
        if path.is_file():
            return Profile.from_toml(path)
        # User scope
        path = self.user_profile_dir / f"{name}.toml"
        if path.is_file():
            return Profile.from_toml(path)
        return None

    def get_active_profile(self) -> str | None:
        """Determine the currently active profile name.

        Resolution order:
        1. ``SPINE_PROFILE`` environment variable
        2. Project-level ``.spine/config.toml`` → ``default_profile``
        3. User-level ``~/.spine/config.toml`` → ``default_profile``
        """
        # 1. Environment variable
        if name := os.environ.get("SPINE_PROFILE"):
            return name

        # 2. Project config.toml
        project_config = self._project_root / ".spine" / "config.toml"
        if project_config.is_file():
            data = tomllib.loads(project_config.read_text(encoding="utf-8"))
            if name := data.get("default_profile"):
                return name

        # 3. User config.toml
        user_config = self._user_dir.parent / "config.toml"
        if user_config.is_file():
            data = tomllib.loads(user_config.read_text(encoding="utf-8"))
            if name := data.get("default_profile"):
                return name

        return None

    # ── Resolution ───────────────────────────────────────────────

    def resolve_profile(self, name: str, _visited: set[str] | None = None) -> dict[str, str]:
        """Resolve a profile down to flat ``SPINE_*`` env vars.

        Handles single- and multi-level inheritance.
        """
        _visited = _visited or set()
        if name in _visited:
            raise ValueError(f"Circular profile inheritance detected: {name}")
        _visited.add(name)

        profile = self.get_profile(name)
        if profile is None:
            raise ValueError(f"Profile not found: {name}")

        # Resolve parent first (base values)
        base: dict[str, str] = {}
        if profile.inherits:
            base = self.resolve_profile(profile.inherits, _visited)

        # Child values override parent
        base.update(profile.to_env_dict())
        return base

    def get_effective_settings(self, name: str) -> dict[str, str]:
        """Resolve profile, then overlay real env vars on top."""
        resolved = self.resolve_profile(name)
        # Real env vars override profile values
        for key in list(resolved):
            if key in os.environ:
                resolved[key] = os.environ[key]
        return resolved

    # ── Mutation ──────────────────────────────────────────────────

    def create_profile(
        self,
        name: str,
        *,
        scope: str = "project",
        inherits: str | None = None,
        description: str = "",
    ) -> Profile:
        """Create an empty profile TOML on disk."""
        directory = self.project_profile_dir if scope == "project" else self.user_profile_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.toml"
        if path.exists():
            raise FileExistsError(f"Profile already exists: {path}")

        content_lines = [
            "[profile]",
            f'name = "{name}"',
        ]
        if inherits:
            content_lines.append(f'inherits = "{inherits}"')
        if description:
            content_lines.append(f'description = "{description}"')
        content_lines.append("")

        path.write_text("\n".join(content_lines) + "\n", encoding="utf-8")
        return Profile.from_toml(path)

    def delete_profile(self, name: str, scope: str = "project") -> bool:
        """Delete a profile file from disk."""
        directory = self.project_profile_dir if scope == "project" else self.user_profile_dir
        path = directory / f"{name}.toml"
        if path.is_file():
            path.unlink()
            return True
        return False

    def set_default_profile(self, name: str, scope: str = "project") -> None:
        """Write the default profile to the scope's ``config.toml``."""
        if scope == "project":
            config_dir = self._project_root / ".spine"
        else:
            config_dir = self._user_dir.parent  # ~/.spine/

        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.toml"

        # Read existing or start fresh
        data: dict[str, Any] = {}
        if config_path.is_file():
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        data["default_profile"] = name

        # Write back (simple TOML serialisation)
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            else:
                lines.append(f"{key} = {value}")
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Module-level convenience ─────────────────────────────────────────────

_manager: ProfileManager | None = None


def get_profile_manager(project_root: Path | None = None) -> ProfileManager:
    """Get (or create) a singleton :class:`ProfileManager`."""
    global _manager
    if _manager is None:
        _manager = ProfileManager(project_root=project_root)
    return _manager


def get_active_profile() -> str | None:
    """Convenience wrapper: return the active profile name or ``None``."""
    return get_profile_manager().get_active_profile()


def list_profiles(scope: str = "all") -> list[Profile]:
    """Convenience wrapper: list available profiles."""
    return get_profile_manager().list_profiles(scope)
