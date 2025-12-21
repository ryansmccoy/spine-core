"""Export the OpenAPI JSON schema from the spine-core API.

Usage:
    uv run python scripts/export_openapi.py
    uv run python scripts/export_openapi.py --output docs/generated/openapi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export spine-core OpenAPI schema")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/generated/openapi.json"),
        help="Output path for the JSON file (default: docs/generated/openapi.json)",
    )
    args = parser.parse_args()

    from spine.api.app import create_app

    app = create_app()
    schema = app.openapi()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(schema, indent=2, default=str))
    print(f"OpenAPI schema exported to {args.output}")
    print(f"  Title: {schema.get('info', {}).get('title', 'N/A')}")
    print(f"  Version: {schema.get('info', {}).get('version', 'N/A')}")
    print(f"  Paths: {len(schema.get('paths', {}))}")
    print(f"  Schemas: {len(schema.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    sys.exit(main() or 0)
