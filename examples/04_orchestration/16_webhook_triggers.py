"""Webhook Triggers — HTTP-triggered workflow and pipeline execution.

WHY WEBHOOK TRIGGERS
────────────────────
Pipelines shouldn’t only run on a schedule.  GitHub pushes, Slack
commands, monitoring alerts, and partner callbacks all need to trigger
work.  The webhook router exposes HTTP POST endpoints so any external
system can kick off spine workflows and pipelines without custom
integration code.

ARCHITECTURE
────────────
    External System              Spine API
    ───────────────              ─────────
    GitHub / Slack /  ── POST ─▶ /api/v1/webhooks/trigger/{name}
    cron / alert                     │
                                     ▼
                              ┌──────────────────┐
                              │ Webhook Registry │
                              │  name → kind     │
                              └────────┬─────────┘
                                       │ dispatch
                                       ▼
                              ┌──────────────────┐
                              │ EventDispatcher  │
                              │  (from app.state)│
                              └──────────────────┘

WEBHOOK API
───────────
    Endpoint                              Method  Purpose
    ────────────────────────────────────── ─────── ─────────────────
    /api/v1/webhooks/                      GET     List all targets
    /api/v1/webhooks/trigger/{name}        POST    Fire webhook
    register_webhook(name, kind, desc)     code    Register target

    kind: "workflow" or "pipeline"
    trigger body: JSON params passed to dispatcher

BEST PRACTICES
──────────────
• Wire app.state.dispatcher in production for real execution.
• Use descriptive webhook names: "sec.daily_ingest", not "hook1".
• Add authentication middleware before exposing webhooks publicly.
• Return 202 Accepted with a run_id for async status polling.

Run: python examples/04_orchestration/16_webhook_triggers.py

See Also:
    01_workflow_basics — what webhooks trigger
    08_tracked_runner — persistent tracking of triggered runs
"""

import sys

try:
    from fastapi.testclient import TestClient
except ImportError:
    print("SKIP: fastapi not installed (pip install fastapi)")
    sys.exit(0)

from fastapi import FastAPI

from spine.api.routers.webhooks import (
    clear_webhooks,
    register_webhook,
    router as webhook_router,
)


def main():
    print("=" * 60)
    print("Webhook Triggers — HTTP-Triggered Execution")
    print("=" * 60)

    # Clean slate
    clear_webhooks()

    # === 1. Register webhook targets ===
    print("\n[1] Registering Webhook Targets")

    register_webhook(
        "sec.daily_ingest",
        kind="workflow",
        description="Daily SEC filing ingest pipeline",
    )
    register_webhook(
        "finra.otc_download",
        kind="pipeline",
        description="Download FINRA OTC transparency data",
    )
    register_webhook(
        "market.price_refresh",
        kind="pipeline",
        description="Refresh market price cache",
    )

    print("  Registered 3 webhook targets")

    # === 2. Create a FastAPI app with the webhook router ===
    print("\n[2] Mounting Webhook Router")

    app = FastAPI(title="Spine Webhook Demo")
    app.include_router(webhook_router, prefix="/api/v1", tags=["webhooks"])

    print("  Router mounted at /api/v1/webhooks")

    # === 3. List webhooks via API ===
    print("\n[3] Listing Webhooks (GET /api/v1/webhooks/)")

    client = TestClient(app)
    resp = client.get("/api/v1/webhooks/")
    assert resp.status_code == 200

    webhooks = resp.json()
    print(f"  Found {len(webhooks)} webhook targets:")
    for wh in webhooks:
        print(f"    [{wh['kind']}] {wh['name']}: {wh['description']}")

    # === 4. Trigger a webhook (without dispatcher — expect 503) ===
    print("\n[4] Trigger Webhook (no dispatcher → 503)")

    resp = client.post(
        "/api/v1/webhooks/trigger/sec.daily_ingest",
        json={"date": "2026-01-15"},
    )
    print(f"  Status: {resp.status_code}")
    print(f"  Detail: {resp.json()['detail']}")
    print("  → This is expected: no EventDispatcher wired to app.state")

    # === 5. Trigger unknown webhook (404) ===
    print("\n[5] Trigger Unknown Webhook (404)")

    resp = client.post("/api/v1/webhooks/trigger/nonexistent")
    print(f"  Status: {resp.status_code}")
    print(f"  Detail: {resp.json()['detail']}")

    # === 6. Integration guide ===
    print("\n[6] Production Integration Guide")
    print()
    print("  In production, wire the dispatcher to app.state:")
    print()
    print("    from spine.execution.dispatcher import EventDispatcher")
    print("    from spine.execution.executors import MemoryExecutor")
    print()
    print("    dispatcher = EventDispatcher(executor=MemoryExecutor(...))")
    print("    app.state.dispatcher = dispatcher")
    print()
    print("  Then POST /webhooks/trigger/{name} will submit work via")
    print("  EventDispatcher and return a run_id for tracking.")
    print()
    print("  Example curl:")
    print('    curl -X POST http://localhost:8000/api/v1/webhooks/trigger/sec.daily_ingest \\')
    print('         -H "Content-Type: application/json" \\')
    print('         -d \'{"date": "2026-01-15"}\'')

    # Clean up
    clear_webhooks()

    print("\n" + "=" * 60)
    print("[OK] Webhook Triggers Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
