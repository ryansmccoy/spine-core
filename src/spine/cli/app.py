"""
Root Typer application for spine-core CLI.

Sub-commands are lazily registered so that heavy imports
(FastAPI, SQLAlchemy) are only loaded when actually needed.
"""

from __future__ import annotations

import sys

try:
    import typer
    from typer import Typer
except ImportError:  # pragma: no cover
    print("typer is required for the CLI.  Install with:  pip install spine-core[cli]")
    sys.exit(1)

app = Typer(
    name="spine-core",
    help="spine-core — platform primitives for temporal data processing.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# ── Version callback ─────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version as pkg_version

        try:
            v = pkg_version("spine-core")
        except Exception:
            v = "0.4.0"
        typer.echo(f"spine-core {v}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(  # noqa: UP007
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """spine-core CLI — manage workflows, runs, schedules, and database."""


# ── Sub-command registration (lazy imports) ──────────────────────────────

from spine.cli.alerts import app as alerts_app  # noqa: E402
from spine.cli.anomaly import app as anom_app  # noqa: E402
from spine.cli.config import app as config_app  # noqa: E402
from spine.cli.db import app as db_app  # noqa: E402
from spine.cli.deploy import app as deploy_app  # noqa: E402
from spine.cli.devtools import app as devtools_app  # noqa: E402
from spine.cli.dlq import app as dlq_app  # noqa: E402
from spine.cli.events import app as events_app  # noqa: E402
from spine.cli.health import app as health_app  # noqa: E402
from spine.cli.profile import app as profile_app  # noqa: E402
from spine.cli.quality import app as qual_app  # noqa: E402
from spine.cli.runs import app as runs_app  # noqa: E402
from spine.cli.schedule import app as sched_app  # noqa: E402
from spine.cli.serve import app as serve_app  # noqa: E402
from spine.cli.sources import app as sources_app  # noqa: E402
from spine.cli.webhook import app as webhook_app  # noqa: E402
from spine.cli.worker import app as worker_app  # noqa: E402
from spine.cli.workflow import app as wf_app  # noqa: E402

app.add_typer(db_app, name="db", help="Database operations.")
app.add_typer(wf_app, name="workflow", help="Workflow management.")
app.add_typer(runs_app, name="runs", help="Execution run management.")
app.add_typer(sched_app, name="schedule", help="Schedule management.")
app.add_typer(health_app, name="health", help="Health and capabilities.")
app.add_typer(dlq_app, name="dlq", help="Dead-letter queue.")
app.add_typer(anom_app, name="anomaly", help="Anomaly detection results.")
app.add_typer(qual_app, name="quality", help="Quality check results.")
app.add_typer(serve_app, name="serve", help="Start the API server.")
app.add_typer(config_app, name="config", help="Configuration management.")
app.add_typer(profile_app, name="profile", help="Profile management.")
app.add_typer(worker_app, name="worker", help="Background execution worker.")
app.add_typer(webhook_app, name="webhook", help="Webhook triggers.")
app.add_typer(alerts_app, name="alerts", help="Alert channel and delivery management.")
app.add_typer(sources_app, name="sources", help="Data source and fetch management.")
app.add_typer(events_app, name="events", help="Event bus management and diagnostics.")
app.add_typer(deploy_app, name="deploy", help="Deployment, testbed, and service management.")
app.add_typer(devtools_app, name="devtools", help="Developer tools: lint, visualize, dry-run.")
