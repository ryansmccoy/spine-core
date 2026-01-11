#!/usr/bin/env python3
"""
Schema Build Script - Combines modular schema files into single operational artifact.

This script:
1. Reads schema module files from spine-core and spine-domains packages
2. Combines them in deterministic order
3. Writes to market-spine-basic/migrations/schema.sql

OWNERSHIP MODEL:
- packages/spine-core/src/spine/core/schema/         → Core framework tables
- packages/spine-domains/src/spine/domains/**/schema/ → Domain-specific tables

USAGE:
    python scripts/build_schema.py

OUTPUT:
    market-spine-basic/migrations/schema.sql (GENERATED - DO NOT EDIT)
"""

import sys
from pathlib import Path
from datetime import datetime

# Project root (scripts/ -> project root)
PROJECT_ROOT = Path(__file__).parent.parent
CORE_SCHEMA_DIR = PROJECT_ROOT / "packages/spine-core/src/spine/core/schema"
DOMAINS_SCHEMA_DIR = PROJECT_ROOT / "packages/spine-domains/src/spine/domains"
OUTPUT_FILE = PROJECT_ROOT / "market-spine-basic/migrations/schema.sql"


# Schema modules in deterministic order
SCHEMA_MODULES = [
    # Core framework (must come first - domain tables reference core tables)
    ("Core Framework", CORE_SCHEMA_DIR / "00_core.sql"),
    
    # FINRA OTC Transparency domain
    ("FINRA OTC Transparency - Tables", DOMAINS_SCHEMA_DIR / "finra/otc_transparency/schema/00_tables.sql"),
    ("FINRA OTC Transparency - Indexes", DOMAINS_SCHEMA_DIR / "finra/otc_transparency/schema/01_indexes.sql"),
    ("FINRA OTC Transparency - Views", DOMAINS_SCHEMA_DIR / "finra/otc_transparency/schema/02_views.sql"),
    
    # Reference: Exchange Calendar domain
    ("Reference: Exchange Calendar - Tables", DOMAINS_SCHEMA_DIR / "reference/exchange_calendar/schema/00_tables.sql"),
    ("Reference: Exchange Calendar - Indexes", DOMAINS_SCHEMA_DIR / "reference/exchange_calendar/schema/01_indexes.sql"),
]


def generate_header():
    """Generate schema file header with build metadata."""
    return f"""-- =============================================================================
-- MARKET SPINE SCHEMA - COMBINED OPERATIONAL ARTIFACT
-- =============================================================================
-- 
-- ⚠️  THIS FILE IS GENERATED - DO NOT EDIT DIRECTLY ⚠️
--
-- To modify the schema:
--   1. Edit the source module files in:
--      - packages/spine-core/src/spine/core/schema/
--      - packages/spine-domains/src/spine/domains/{{domain}}/schema/
--   2. Run: python scripts/build_schema.py
--   3. Commit both module files AND this generated file
--
-- Generated: {datetime.now().isoformat()}
-- Build script: scripts/build_schema.py
--
-- OWNERSHIP MODEL:
-- - Core framework tables: spine-core package
-- - Domain-specific tables: spine-domains package (by domain)
--
-- MODULES INCLUDED (in order):
{chr(10).join(f"--   - {label}" for label, _ in SCHEMA_MODULES)}
--
-- =============================================================================


"""


def read_module(module_path: Path) -> str:
    """Read a schema module file, returning its content."""
    if not module_path.exists():
        raise FileNotFoundError(f"Schema module not found: {module_path}")
    
    return module_path.read_text(encoding='utf-8')


def build_schema():
    """Combine schema modules into single output file."""
    print(f"Building schema from {len(SCHEMA_MODULES)} modules...")
    
    # Start with header
    content_parts = [generate_header()]
    
    # Add each module
    for label, module_path in SCHEMA_MODULES:
        print(f"  Including: {label} ({module_path.relative_to(PROJECT_ROOT)})")
        
        # Section separator
        content_parts.append(f"\n-- ===========================================================================\n")
        content_parts.append(f"-- MODULE: {label}\n")
        content_parts.append(f"-- Source: {module_path.relative_to(PROJECT_ROOT)}\n")
        content_parts.append(f"-- ===========================================================================\n\n")
        
        # Module content
        module_content = read_module(module_path)
        content_parts.append(module_content)
        content_parts.append("\n\n")
    
    # Add schema version tracking (end of file)
    content_parts.append(f"""
-- =============================================================================
-- RECORD SCHEMA VERSION
-- =============================================================================

INSERT OR IGNORE INTO _migrations (filename) VALUES ('001_schema.sql');
""")
    
    # Combine all parts
    final_content = "".join(content_parts)
    
    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(final_content, encoding='utf-8')
    
    print(f"\n✅ Schema built successfully!")
    print(f"   Output: {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"   Size: {len(final_content):,} bytes")
    print(f"   Modules: {len(SCHEMA_MODULES)}")


def validate_modules():
    """Pre-flight check: Ensure all module files exist."""
    missing = []
    for label, module_path in SCHEMA_MODULES:
        if not module_path.exists():
            missing.append((label, module_path))
    
    if missing:
        print("❌ ERROR: Missing schema module files:\n")
        for label, path in missing:
            print(f"  - {label}: {path.relative_to(PROJECT_ROOT)}")
        print("\nPlease create missing files before building schema.")
        return False
    
    return True


if __name__ == "__main__":
    print("Market Spine - Schema Build Tool")
    print("=" * 60)
    
    # Validate all modules exist
    if not validate_modules():
        sys.exit(1)
    
    # Build schema
    try:
        build_schema()
    except Exception as e:
        print(f"\n❌ Build failed: {e}")
        sys.exit(1)
    
    print("\nDone. You can now use 'spine db init' to apply this schema.")
