"""Shared database setup and run-recording for spine-core examples.

Provides:

- ``get_example_connection()`` — dialect/raw-SQL connection (SqliteConnection)
- ``get_orm_connection()``     — SQLAlchemy ORM connection (SpineSession bridge)
- ``record_example_run()``     — stores an Execution + stdout events per example
- ``load_env()``               — reads ``examples/.env`` (zero-dep)

Environment Variables
---------------------
``SPINE_EXAMPLES_DB``
    Controls the dialect storage mode:

    - ``memory``   — (default) in-memory SQLite, data lost on exit
    - ``file``     — SQLite file at ``examples/results/dialect_examples.db``
    - ``postgres`` — PostgreSQL via Docker (port 10432)
    - Any path     — custom SQLite file path

``SPINE_EXAMPLES_ORM_DB``
    Controls ORM comparison database:

    - ``file``     — SQLite file at ``examples/results/orm_examples.db``
    - ``off``      — skip ORM database entirely (default)

``SPINE_EXAMPLES_RESET``
    If ``1``, deletes SQLite files before creating new connections.

``SPINE_EXAMPLES_TAG``
    If ``1``, enables execution recording with metadata tags.

Usage::

    from _db import get_example_connection, load_env, record_example_run

    load_env()
    conn, info = get_example_connection()
    record_example_run(conn, "01_core", 1, "result_pattern", "Result", "PASS", [...])
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from spine.core.connection import ConnectionInfo, create_connection

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_EXAMPLES_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _EXAMPLES_DIR / "results"
_DIALECT_DB_PATH = _RESULTS_DIR / "dialect_examples.db"
_ORM_DB_PATH = _RESULTS_DIR / "orm_examples.db"
_ENV_FILE = _EXAMPLES_DIR / ".env"
_DEFAULT_POSTGRES_URL = "postgresql://spine:spine@localhost:10432/spine"


# ---------------------------------------------------------------------------
# Simple .env loader (zero-dependency)
# ---------------------------------------------------------------------------


def load_env(path: Path | None = None) -> dict[str, str]:
    """Read a .env file and set values in ``os.environ``.

    Only sets variables that are NOT already in the environment
    (real env vars take precedence).  Returns the parsed dict.
    """
    env_path = path or _ENV_FILE
    parsed: dict[str, str] = {}

    if not env_path.exists():
        return parsed

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        parsed[key] = value
        if key not in os.environ:
            os.environ[key] = value

    return parsed


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _ensure_results_dir() -> Path:
    """Create the results/ directory if needed."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return _RESULTS_DIR


def _maybe_reset(path: Path) -> None:
    """Delete the SQLite file if SPINE_EXAMPLES_RESET=1."""
    if os.environ.get("SPINE_EXAMPLES_RESET", "").strip() == "1":
        if path.exists():
            path.unlink()


def get_example_connection(
    *,
    db: str | None = None,
    apply_schema: bool = True,
) -> tuple[Any, ConnectionInfo]:
    """Get a dialect-layer database connection for examples.

    Parameters
    ----------
    db:
        Override the database mode.  If ``None``, reads from the
        ``SPINE_EXAMPLES_DB`` environment variable (default: ``memory``).
    apply_schema:
        If ``True`` (default), applies all spine-core schemas.

    Returns
    -------
    tuple[Connection, ConnectionInfo]
        A ``SqliteConnection`` or ``SAConnectionBridge``, plus metadata.
    """
    mode = db or os.environ.get("SPINE_EXAMPLES_DB", "memory").strip()

    if mode == "file":
        _ensure_results_dir()
        _maybe_reset(_DIALECT_DB_PATH)
        mode = str(_DIALECT_DB_PATH)
    elif mode == "postgres":
        mode = _DEFAULT_POSTGRES_URL
    elif mode not in ("memory", ":memory:") and not mode.startswith(
        ("sqlite", "postgresql", "postgres")
    ):
        _maybe_reset(Path(mode))

    conn, info = create_connection(mode, init_schema=apply_schema)
    return conn, info


def get_orm_connection(
    *,
    db: str | None = None,
) -> tuple[Any, Any, ConnectionInfo] | None:
    """Get an ORM-layer database connection (SQLAlchemy).

    Returns ``(bridge, engine, info)`` or ``None`` if ORM is disabled
    or SQLAlchemy is not available.
    """
    mode = db or os.environ.get("SPINE_EXAMPLES_ORM_DB", "off").strip()

    if mode == "off":
        return None

    try:
        from spine.core.orm import SpineBase, create_spine_engine
        from spine.core.orm.session import SAConnectionBridge, SpineSession
    except ImportError:
        return None

    if mode == "file":
        _ensure_results_dir()
        _maybe_reset(_ORM_DB_PATH)
        url = f"sqlite:///{_ORM_DB_PATH}"
    elif mode == "postgres":
        url = _DEFAULT_POSTGRES_URL
    else:
        url = mode if "://" in mode else f"sqlite:///{mode}"

    engine = create_spine_engine(url, echo=False)
    SpineBase.metadata.create_all(engine)

    session = SpineSession(bind=engine)
    bridge = SAConnectionBridge(session)

    # The ORM models use `workflow` column names.  The raw SQL schema
    # files still use `pipeline` in some tables, so we skip
    # apply_all_schemas() here — SpineBase.metadata.create_all() has
    # already created every table we need.
    #
    # For the core_executions / core_execution_events tables that the
    # ExecutionLedger needs, we create them via the dialect DDL so they
    # match the ledger's SQL queries (which use `workflow`).
    from spine.core.schema import create_core_tables

    create_core_tables(bridge)

    info = ConnectionInfo(
        backend="sqlite" if "sqlite" in url else "postgresql",
        persistent=True,
        url=url,
        resolved_path=str(_ORM_DB_PATH) if "sqlite" in url else None,
    )
    return bridge, engine, info


# ---------------------------------------------------------------------------
# Run recording
# ---------------------------------------------------------------------------


def record_example_run(
    conn: Any,
    category: str,
    number: int,
    name: str,
    title: str,
    status: str,
    stdout_lines: list[str],
    duration_seconds: float = 0.0,
) -> str | None:
    """Record an example run as an Execution with stdout events.

    Parameters
    ----------
    conn:
        Database connection (dialect or ORM bridge).
    category:
        Example category, e.g. ``"01_core"``.
    number:
        Example number within the category.
    name:
        Example stem name, e.g. ``"result_pattern"``.
    title:
        Human-readable title from docstring.
    status:
        ``"PASS"`` or ``"FAIL"``.
    stdout_lines:
        Captured stdout lines from the example run.
    duration_seconds:
        Wall-clock execution time.

    Returns
    -------
    str | None
        The execution_id, or None if recording failed.
    """
    if os.environ.get("SPINE_EXAMPLES_TAG", "").strip() != "1":
        return None

    try:
        import uuid
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        execution_id = str(uuid.uuid4())
        workflow_name = f"example.{category}.{number:02d}_{name}"
        params = json.dumps({
            "example_category": category,
            "example_number": number,
            "example_name": name,
            "example_title": title,
            "duration_seconds": round(duration_seconds, 3),
        })
        exec_status = "completed" if status == "PASS" else "failed"
        result_json = json.dumps({
            "status": status,
            "stdout_lines": len(stdout_lines),
            "duration_seconds": round(duration_seconds, 3),
        }) if status == "PASS" else None
        error_msg = (
            f"Example failed. Last output: {stdout_lines[-5:] if stdout_lines else []}"
            if status != "PASS" else None
        )

        # Insert execution (uses Connection protocol — execute + commit)
        conn.execute(
            """
            INSERT INTO core_executions (
                id, workflow, params, status, lane, trigger_source,
                parent_execution_id, created_at, started_at, completed_at,
                result, error, retry_count, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id, workflow_name, params, exec_status,
                "default", "cli", None, now, now, now,
                result_json, error_msg, 0, None,
            ),
        )
        conn.commit()

        # Insert lifecycle events
        _insert_event(conn, execution_id, "created", now,
                       json.dumps({"workflow": workflow_name}))
        _insert_event(conn, execution_id, "started", now, "{}")

        # Store stdout as chunked events
        chunk_size = 50
        for i in range(0, len(stdout_lines), chunk_size):
            chunk = stdout_lines[i : i + chunk_size]
            _insert_event(conn, execution_id, "stdout", now,
                           json.dumps({
                               "chunk_index": i // chunk_size,
                               "lines": chunk,
                               "line_count": len(chunk),
                           }))

        # Final status event
        final_type = "completed" if status == "PASS" else "failed"
        _insert_event(conn, execution_id, final_type, now,
                       json.dumps({"result": result_json, "error": error_msg}))

        conn.commit()
        return execution_id

    except Exception as e:
        print(f"  [warn] Failed to record run: {e}")
        return None


def _insert_event(
    conn: Any,
    execution_id: str,
    event_type: str,
    timestamp: str,
    data: str,
) -> None:
    """Insert a single execution event row."""
    import uuid

    conn.execute(
        """
        INSERT INTO core_execution_events (
            id, execution_id, event_type, timestamp, data
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), execution_id, event_type, timestamp, data),
    )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def print_db_info(conn: Any, info: ConnectionInfo | None = None) -> None:
    """Print database mode and table summary."""
    if info:
        if info.is_postgres:
            backend = "PostgreSQL"
        elif info.persistent:
            backend = f"SQLite ({info.resolved_path or info.url})"
        else:
            backend = "SQLite (in-memory)"
    else:
        backend = "SQLite (in-memory)"

    print(f"  Database : {backend}")

    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'core_%' ORDER BY name"
        ).fetchall()
        print(f"  Tables   : {len(rows)} core tables")
    except Exception:
        pass


def print_table_counts(conn: Any, *, prefix: str = "core_") -> None:
    """Print row counts for all tables matching prefix."""
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            f"AND name LIKE '{prefix}%' ORDER BY name"
        ).fetchall()
    except Exception:
        print("  (table count not available for this backend)")
        return

    if not rows:
        print("  (no matching tables)")
        return

    non_empty = []
    for row in rows:
        name = row[0] if isinstance(row, (tuple, list)) else row["name"]
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            if count > 0:
                non_empty.append((name, count))
        except Exception:
            pass

    if non_empty:
        max_name = max(len(n) for n, _ in non_empty)
        for name, count in non_empty:
            print(f"    {name:<{max_name}}  {count:>6} rows")
    else:
        print("  (all tables empty)")
