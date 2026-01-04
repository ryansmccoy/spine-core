"""
Schema Module Validation Tests

Ensures schema modules maintain proper ownership boundaries:
- Core module contains only core_* tables
- Domain modules contain only domain-specific tables
- No cross-contamination between modules
"""

import pytest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestSchemaModuleOwnership:
    """Validate schema module ownership boundaries."""
    
    def test_core_module_contains_only_core_tables(self):
        """Core module (spine-core) should only contain core_* tables and _migrations."""
        core_schema = PROJECT_ROOT / "packages/spine-core/src/spine/core/schema/00_core.sql"
        content = core_schema.read_text(encoding='utf-8')
        
        # Should contain core_* tables
        assert "CREATE TABLE IF NOT EXISTS core_executions" in content
        assert "CREATE TABLE IF NOT EXISTS core_manifest" in content
        assert "CREATE TABLE IF NOT EXISTS core_anomalies" in content
        assert "CREATE TABLE IF NOT EXISTS core_data_readiness" in content
        
        # Should NOT contain domain-specific tables
        assert "finra_otc_transparency" not in content.lower()
        assert "reference_exchange_calendar" not in content.lower()
        
        print("✅ Core module contains only core_* tables")
    
    
    def test_finra_domain_contains_only_finra_tables(self):
        """FINRA domain module should only contain finra_otc_transparency_* tables."""
        finra_tables = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/finra/otc_transparency/schema/00_tables.sql"
        content = finra_tables.read_text(encoding='utf-8')
        
        # Should contain finra_otc_transparency_* tables
        assert "CREATE TABLE IF NOT EXISTS finra_otc_transparency_raw" in content
        assert "CREATE TABLE IF NOT EXISTS finra_otc_transparency_normalized" in content
        assert "CREATE TABLE IF NOT EXISTS finra_otc_transparency_symbol_summary" in content
        
        # Should NOT contain core or other domain tables
        assert "CREATE TABLE IF NOT EXISTS core_" not in content
        assert "reference_exchange_calendar" not in content
        
        print("✅ FINRA domain module contains only finra_* tables")
    
    
    def test_reference_domain_contains_only_reference_tables(self):
        """Reference domain module should only contain reference_exchange_calendar_* tables."""
        ref_tables = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/reference/exchange_calendar/schema/00_tables.sql"
        content = ref_tables.read_text(encoding='utf-8')
        
        # Should contain reference_exchange_calendar_* tables
        assert "CREATE TABLE IF NOT EXISTS reference_exchange_calendar_holidays" in content
        assert "CREATE TABLE IF NOT EXISTS reference_exchange_calendar_trading_days" in content
        
        # Should NOT contain core or other domain tables
        assert "CREATE TABLE IF NOT EXISTS core_" not in content
        assert "finra_otc_transparency" not in content
        
        print("✅ Reference domain module contains only reference_* tables")
    
    
    def test_build_script_exists_and_runnable(self):
        """Build script should exist and be executable."""
        build_script = PROJECT_ROOT / "scripts/build_schema.py"
        assert build_script.exists(), "build_schema.py not found"
        
        content = build_script.read_text(encoding='utf-8')
        assert "SCHEMA_MODULES" in content
        assert "generate_header" in content
        assert "build_schema" in content
        
        print("✅ Build script exists with correct structure")
    
    
    def test_generated_schema_contains_all_modules(self):
        """Generated schema should contain all module sections."""
        generated_schema = PROJECT_ROOT / "market-spine-basic/migrations/schema.sql"
        assert generated_schema.exists(), "Generated schema.sql not found (run python scripts/build_schema.py)"
        
        content = generated_schema.read_text(encoding='utf-8')
        
        # Should have generation header
        assert "THIS FILE IS GENERATED - DO NOT EDIT DIRECTLY" in content
        assert "python scripts/build_schema.py" in content
        
        # Should contain all core tables
        assert "CREATE TABLE IF NOT EXISTS core_executions" in content
        assert "CREATE TABLE IF NOT EXISTS core_manifest" in content
        assert "CREATE TABLE IF NOT EXISTS core_anomalies" in content
        assert "CREATE TABLE IF NOT EXISTS core_data_readiness" in content
        
        # Should contain all FINRA tables
        assert "CREATE TABLE IF NOT EXISTS finra_otc_transparency_raw" in content
        assert "CREATE TABLE IF NOT EXISTS finra_otc_transparency_normalized" in content
        
        # Should contain all reference tables
        assert "CREATE TABLE IF NOT EXISTS reference_exchange_calendar_holidays" in content
        assert "CREATE TABLE IF NOT EXISTS reference_exchange_calendar_trading_days" in content
        
        # Should contain module markers
        assert "MODULE: Core Framework" in content
        assert "MODULE: FINRA OTC Transparency - Tables" in content
        assert "MODULE: Reference: Exchange Calendar - Tables" in content
        
        print("✅ Generated schema contains all modules correctly")


class TestSchemaModuleStructure:
    """Validate schema module directory structure."""
    
    def test_core_schema_directory_structure(self):
        """Core schema directory should exist with correct structure."""
        core_dir = PROJECT_ROOT / "packages/spine-core/src/spine/core/schema"
        assert core_dir.exists(), f"Core schema directory missing: {core_dir}"
        
        # Should have 00_core.sql
        assert (core_dir / "00_core.sql").exists(), "00_core.sql missing"
        
        print("✅ Core schema directory structure correct")
    
    
    def test_finra_schema_directory_structure(self):
        """FINRA schema directory should exist with correct structure."""
        finra_dir = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/finra/otc_transparency/schema"
        assert finra_dir.exists(), f"FINRA schema directory missing: {finra_dir}"
        
        # Should have tables, indexes, and views
        assert (finra_dir / "00_tables.sql").exists(), "00_tables.sql missing"
        assert (finra_dir / "01_indexes.sql").exists(), "01_indexes.sql missing"
        assert (finra_dir / "02_views.sql").exists(), "02_views.sql missing"
        
        print("✅ FINRA schema directory structure correct")
    
    
    def test_reference_schema_directory_structure(self):
        """Reference schema directory should exist with correct structure."""
        ref_dir = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/reference/exchange_calendar/schema"
        assert ref_dir.exists(), f"Reference schema directory missing: {ref_dir}"
        
        # Should have tables and indexes
        assert (ref_dir / "00_tables.sql").exists(), "00_tables.sql missing"
        assert (ref_dir / "01_indexes.sql").exists(), "01_indexes.sql missing"
        
        print("✅ Reference schema directory structure correct")


class TestSchemaIndexSeparation:
    """Validate that indexes are separated from tables in domain modules."""
    
    def test_finra_tables_do_not_contain_indexes(self):
        """FINRA 00_tables.sql should not contain CREATE INDEX statements."""
        finra_tables = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/finra/otc_transparency/schema/00_tables.sql"
        content = finra_tables.read_text(encoding='utf-8')
        
        assert "CREATE INDEX" not in content, "Tables file should not contain CREATE INDEX statements"
        
        print("✅ FINRA tables file contains no indexes")
    
    
    def test_finra_indexes_contain_only_indexes(self):
        """FINRA 01_indexes.sql should only contain CREATE INDEX statements."""
        finra_indexes = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/finra/otc_transparency/schema/01_indexes.sql"
        content = finra_indexes.read_text(encoding='utf-8')
        
        # Should contain indexes
        assert "CREATE INDEX" in content
        
        # Should NOT contain table definitions
        assert "CREATE TABLE" not in content
        assert "CREATE VIEW" not in content
        
        print("✅ FINRA indexes file contains only indexes")
    
    
    def test_finra_views_contain_only_views(self):
        """FINRA 02_views.sql should only contain CREATE VIEW statements."""
        finra_views = PROJECT_ROOT / "packages/spine-domains/src/spine/domains/finra/otc_transparency/schema/02_views.sql"
        content = finra_views.read_text(encoding='utf-8')
        
        # Should contain views
        assert "CREATE VIEW" in content
        
        # Should NOT contain tables or indexes
        assert "CREATE TABLE" not in content
        assert "CREATE INDEX" not in content
        
        print("✅ FINRA views file contains only views")
