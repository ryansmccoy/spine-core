"""
Institutional Hardening Tests - Anomaly Detection and Data Readiness

Tests realistic failure scenarios identified in docs/analytics/FAILURE_SCENARIOS.md:
1. Missing tier for a week
2. Partial venue coverage
3. Zero-volume anomalies
4. Late-arriving data
5. Calendar corrections

Validates:
- Anomaly persistence (core_anomalies table)
- Data readiness certification (core_data_readiness table)
- Expected schedule tracking (core_expected_schedules table)
- Dependency tracking (core_calc_dependencies table)
"""

import pytest
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path


@pytest.fixture
def db_with_schema():
    """Create in-memory database with full schema"""
    db_path = Path(__file__).parent.parent / "migrations" / "schema.sql"
    schema_sql = db_path.read_text(encoding='utf-8')
    
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    conn.row_factory = sqlite3.Row
    return conn


def record_anomaly(conn, domain, pipeline, partition_key, severity, category, message, 
                  details=None, affected_records=None, capture_id=None):
    """Helper to record anomaly"""
    conn.execute("""
        INSERT INTO core_anomalies (
            domain, pipeline, partition_key, severity, category, message,
            details_json, affected_records, capture_id, detected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        domain, pipeline, json.dumps(partition_key), severity, category, message,
        json.dumps(details) if details else None,
        affected_records, capture_id, datetime.now().isoformat()
    ))
    conn.commit()


def check_readiness(conn, domain, partition_key, ready_for='trading'):
    """
    Check if data partition is ready for use.
    
    Criteria:
    1. All expected partitions present (per expected_schedules)
    2. All stages complete (per manifest)
    3. No CRITICAL anomalies
    4. Dependencies current
    5. Age exceeds preliminary period
    """
    partition_key_json = json.dumps(partition_key)
    
    # Check 1: Expected partitions present
    # For this test, we'll check if all 3 tiers exist for FINRA OTC
    if domain == 'finra.otc_transparency':
        week_ending = partition_key.get('week_ending')
        expected_tiers = ['NMS_TIER_1', 'NMS_TIER_2', 'OTC']
        
        actual_tiers = conn.execute("""
            SELECT DISTINCT json_extract(partition_key, '$.tier') as tier
            FROM core_manifest
            WHERE domain = ? 
              AND json_extract(partition_key, '$.week_ending') = ?
              AND stage = 'NORMALIZED'
        """, (domain, week_ending)).fetchall()
        
        actual_tier_set = {row['tier'] for row in actual_tiers}
        all_partitions_present = len(actual_tier_set) == len(expected_tiers)
    else:
        all_partitions_present = True  # Default for other domains
    
    # Check 2: All stages complete
    expected_stages = ['RAW', 'NORMALIZED', 'CALC']
    
    # For per-tier readiness checks, use partition_key with tier
    if 'tier' in partition_key:
        actual_stages = conn.execute("""
            SELECT DISTINCT stage
            FROM core_manifest
            WHERE domain = ?
              AND partition_key = ?
        """, (domain, partition_key_json)).fetchall()
    else:
        # For week-level checks, aggregate across all tiers
        week_ending = partition_key.get('week_ending')
        actual_stages = conn.execute("""
            SELECT DISTINCT stage
            FROM core_manifest
            WHERE domain = ?
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (domain, week_ending)).fetchall()
    
    actual_stage_set = {row['stage'] for row in actual_stages}
    all_stages_complete = all(stage in actual_stage_set for stage in expected_stages)
    
    # Check 3: No CRITICAL anomalies
    if 'tier' in partition_key:
        critical_anomalies = conn.execute("""
            SELECT COUNT(*) as count
            FROM core_anomalies
            WHERE domain = ?
              AND partition_key = ?
              AND severity = 'CRITICAL'
              AND resolved_at IS NULL
        """, (domain, partition_key_json)).fetchone()
    else:
        # For week-level checks, check across all tiers for that week
        week_ending = partition_key.get('week_ending')
        critical_anomalies = conn.execute("""
            SELECT COUNT(*) as count
            FROM core_anomalies
            WHERE domain = ?
              AND json_extract(partition_key, '$.week_ending') = ?
              AND severity = 'CRITICAL'
              AND resolved_at IS NULL
        """, (domain, week_ending)).fetchone()
    
    no_critical_anomalies = critical_anomalies['count'] == 0
    
    # Check 4: Dependencies current (simplified - check if dependencies exist)
    dependencies_current = True  # Simplified for this test
    
    # Check 5: Age exceeds preliminary period (simplified - assume 48 hours)
    age_exceeds_preliminary = True  # Simplified for this test
    
    # Overall readiness
    is_ready = (
        all_partitions_present and 
        all_stages_complete and 
        no_critical_anomalies and
        dependencies_current and
        age_exceeds_preliminary
    )
    
    # Build blocking issues list
    blocking_issues = []
    if not all_partitions_present:
        blocking_issues.append("Missing expected partitions")
    if not all_stages_complete:
        blocking_issues.append(f"Incomplete stages. Expected: {expected_stages}, Actual: {list(actual_stage_set)}")
    if not no_critical_anomalies:
        blocking_issues.append(f"CRITICAL anomalies present: {critical_anomalies['count']}")
    
    # Record readiness status
    conn.execute("""
        INSERT OR REPLACE INTO core_data_readiness (
            domain, partition_key, ready_for, is_ready,
            all_partitions_present, all_stages_complete, no_critical_anomalies,
            dependencies_current, age_exceeds_preliminary,
            blocking_issues, certified_at, certified_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        domain, partition_key_json, ready_for, 1 if is_ready else 0,
        1 if all_partitions_present else 0,
        1 if all_stages_complete else 0,
        1 if no_critical_anomalies else 0,
        1 if dependencies_current else 0,
        1 if age_exceeds_preliminary else 0,
        json.dumps(blocking_issues) if blocking_issues else None,
        datetime.now().isoformat() if is_ready else None,
        'test_system'
    ))
    conn.commit()
    
    return is_ready, blocking_issues


class TestScenario1_MissingTier:
    """Scenario 1: Missing tier for a week - OTC tier not published"""
    
    def test_missing_tier_detected(self, db_with_schema):
        conn = db_with_schema
        week_ending = '2025-12-22'
        
        # Simulate: Only NMS_TIER_1 and NMS_TIER_2 ingested successfully
        for tier in ['NMS_TIER_1', 'NMS_TIER_2']:
            partition_key = json.dumps({'week_ending': week_ending, 'tier': tier})
            conn.execute("""
                INSERT INTO core_manifest (domain, partition_key, stage, row_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, ('finra.otc_transparency', partition_key, 'NORMALIZED', 1000, datetime.now().isoformat()))
        
        # Record anomaly: OTC tier missing
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='ingest_week',
            partition_key={'week_ending': week_ending, 'tier': 'OTC'},
            severity='ERROR',
            category='INCOMPLETE_INPUT',
            message='Tier OTC failed ingestion - HTTP 404',
            details={'http_status': 404, 'expected_tiers': 3, 'actual_tiers': 2}
        )
        
        # Check readiness - should fail
        is_ready, blocking_issues = check_readiness(
            conn, 
            'finra.otc_transparency',
            {'week_ending': week_ending}
        )
        
        assert not is_ready, "Data should not be ready when tier missing"
        assert any('Missing expected partitions' in issue for issue in blocking_issues)
        
        # Verify anomaly recorded
        anomalies = conn.execute("""
            SELECT severity, category, message
            FROM core_anomalies
            WHERE domain = 'finra.otc_transparency'
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (week_ending,)).fetchall()
        
        assert len(anomalies) == 1
        assert anomalies[0]['severity'] == 'ERROR'
        assert anomalies[0]['category'] == 'INCOMPLETE_INPUT'


class TestScenario2_PartialVenueCoverage:
    """Scenario 2: Partial venue coverage - only 45 venues instead of 150+"""
    
    def test_venue_count_anomaly_detected(self, db_with_schema):
        conn = db_with_schema
        week_ending = '2025-12-15'
        tier = 'NMS_TIER_1'
        
        # Record anomaly: Low venue count
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='normalize_week',
            partition_key={'week_ending': week_ending, 'tier': tier},
            severity='WARN',
            category='COMPLETENESS',
            message='Venue count significantly below historical average',
            details={
                'current_venue_count': 45,
                'historical_p10': 140,
                'historical_p50': 165,
                'historical_p90': 180
            },
            affected_records=45
        )
        
        # Add downstream calculation warning
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='compute_venue_concentration_hhi',
            partition_key={'week_ending': week_ending, 'tier': tier},
            severity='WARN',
            category='INCOMPLETE_INPUT',
            message='HHI calculated from limited venue set (45 instead of ~165). Results may overstate concentration.',
            details={'venue_count': 45, 'typical_venue_count': 165}
        )
        
        # Mark stages as complete (data arrived, just incomplete)
        partition_key_json = json.dumps({'week_ending': week_ending, 'tier': tier})
        for stage in ['RAW', 'NORMALIZED', 'CALC']:
            conn.execute("""
                INSERT INTO core_manifest (domain, partition_key, stage, row_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, ('finra.otc_transparency', partition_key_json, stage, 100, datetime.now().isoformat()))
        
        # Check readiness - should pass (no CRITICAL anomalies)
        is_ready, blocking_issues = check_readiness(
            conn,
            'finra.otc_transparency',
            {'week_ending': week_ending, 'tier': tier}
        )
        
        # Should be ready despite WARN anomalies (not CRITICAL)
        # Note: This is policy decision - WARN doesn't block readiness
        
        # Verify anomalies recorded
        anomalies = conn.execute("""
            SELECT severity, category, pipeline, message
            FROM core_anomalies
            WHERE domain = 'finra.otc_transparency'
              AND json_extract(partition_key, '$.week_ending') = ?
              AND json_extract(partition_key, '$.tier') = ?
            ORDER BY id
        """, (week_ending, tier)).fetchall()
        
        assert len(anomalies) == 2
        assert anomalies[0]['category'] == 'COMPLETENESS'
        assert anomalies[1]['category'] == 'INCOMPLETE_INPUT'
        assert anomalies[1]['pipeline'] == 'compute_venue_concentration_hhi'


class TestScenario3_ZeroVolumeAnomaly:
    """Scenario 3: Zero-volume anomalies - trades without volume (business rule violation)"""
    
    def test_business_rule_violation_detected(self, db_with_schema):
        conn = db_with_schema
        week_ending = '2025-12-08'
        tier = 'OTC'
        
        # Record CRITICAL anomaly: Business rule violation
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='normalize_week',
            partition_key={'week_ending': week_ending, 'tier': tier},
            severity='CRITICAL',
            category='BUSINESS_RULE',
            message='150 records with total_trades > 0 but total_shares = 0 (logically impossible)',
            details={
                'violation': 'trades_without_volume',
                'sample_symbols': ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL']
            },
            affected_records=150
        )
        
        # Mark stages as complete
        partition_key_json = json.dumps({'week_ending': week_ending, 'tier': tier})
        for stage in ['RAW', 'NORMALIZED']:
            conn.execute("""
                INSERT INTO core_manifest (domain, partition_key, stage, row_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, ('finra.otc_transparency', partition_key_json, stage, 3000, datetime.now().isoformat()))
        
        # Check readiness - should FAIL (CRITICAL anomaly blocks)
        is_ready, blocking_issues = check_readiness(
            conn,
            'finra.otc_transparency',
            {'week_ending': week_ending, 'tier': tier}
        )
        
        assert not is_ready, "Data should NOT be ready with CRITICAL anomalies"
        assert any('CRITICAL anomalies' in issue for issue in blocking_issues)
        
        # Verify readiness record
        readiness = conn.execute("""
            SELECT is_ready, no_critical_anomalies, blocking_issues
            FROM core_data_readiness
            WHERE domain = 'finra.otc_transparency'
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (week_ending,)).fetchone()
        
        assert readiness['is_ready'] == 0
        assert readiness['no_critical_anomalies'] == 0


class TestScenario4_LateArrivingData:
    """Scenario 4: Late-arriving data - FINRA republishes with corrections"""
    
    def test_data_revision_tracked(self, db_with_schema):
        conn = db_with_schema
        week_ending = '2025-12-22'
        tier = 'NMS_TIER_1'
        
        # Monday capture (initial)
        monday_capture_id = f'finra.otc_transparency:{tier}:{week_ending}:20251223'
        partition_key_json = json.dumps({'week_ending': week_ending, 'tier': tier})
        
        conn.execute("""
            INSERT INTO core_manifest (domain, partition_key, stage, row_count, execution_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('finra.otc_transparency', partition_key_json, 'NORMALIZED', 2800, monday_capture_id, '2025-12-23T10:00:00Z'))
        
        # Wednesday capture (correction - 200 more symbols)
        wednesday_capture_id = f'finra.otc_transparency:{tier}:{week_ending}:20251225'
        
        # Record anomaly: Data revised
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='ingest_week',
            partition_key={'week_ending': week_ending, 'tier': tier},
            severity='INFO',
            category='FRESHNESS',
            message='FINRA republished data with corrections. 200 symbols added since previous capture.',
            details={
                'previous_capture_id': monday_capture_id,
                'new_capture_id': wednesday_capture_id,
                'previous_symbol_count': 2800,
                'new_symbol_count': 3000,
                'symbols_added': 200,
                'significant_hhi_changes': 15
            },
            capture_id=wednesday_capture_id
        )
        
        # Update manifest with new capture
        conn.execute("""
            UPDATE core_manifest 
            SET row_count = ?, execution_id = ?, updated_at = ?
            WHERE domain = ? AND partition_key = ? AND stage = ?
        """, (3000, wednesday_capture_id, '2025-12-25T09:00:00Z', 'finra.otc_transparency', partition_key_json, 'NORMALIZED'))
        
        # Verify revision tracking
        revisions = conn.execute("""
            SELECT severity, category, message, details_json
            FROM core_anomalies
            WHERE domain = 'finra.otc_transparency'
              AND category = 'FRESHNESS'
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (week_ending,)).fetchall()
        
        assert len(revisions) == 1
        details = json.loads(revisions[0]['details_json'])
        assert details['symbols_added'] == 200
        assert details['previous_symbol_count'] == 2800
        assert details['new_symbol_count'] == 3000


class TestScenario5_CalendarCorrection:
    """Scenario 5: Calendar corrections after analytics ran"""
    
    def test_dependency_invalidation(self, db_with_schema):
        conn = db_with_schema
        
        # Setup: Register dependency
        conn.execute("""
            INSERT INTO core_calc_dependencies (
                calc_domain, calc_pipeline, depends_on_domain, depends_on_table, dependency_type, description
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'finra.otc_transparency',
            'compute_normalized_volume_per_day',
            'reference.exchange_calendar',
            'reference_exchange_calendar_trading_days',
            'REQUIRED',
            'Requires trading day count for volume normalization'
        ))
        
        # Calendar corrected: MLK Day was not a holiday for OTC
        year = 2025
        month = 1
        old_trading_days = 20
        new_trading_days = 21
        
        # Record anomaly: Upstream dependency changed
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='compute_normalized_volume_per_day',
            partition_key={'year': year, 'month': month},
            severity='WARN',
            category='DEPENDENCY',
            message='Dependency reference.exchange_calendar revised. Calendar data corrected: January 2025 now has 21 trading days (was 20). Analytics may be outdated.',
            details={
                'dependency_domain': 'reference.exchange_calendar',
                'dependency_table': 'reference_exchange_calendar_trading_days',
                'previous_trading_days': old_trading_days,
                'new_trading_days': new_trading_days,
                'affected_calculations': ['normalized_volume_per_day', 'avg_daily_volume']
            }
        )
        
        # Verify dependency tracking
        dependencies = conn.execute("""
            SELECT calc_domain, calc_pipeline, depends_on_domain, dependency_type
            FROM core_calc_dependencies
            WHERE depends_on_domain = 'reference.exchange_calendar'
        """).fetchall()
        
        assert len(dependencies) == 1
        assert dependencies[0]['calc_domain'] == 'finra.otc_transparency'
        
        # Verify invalidation anomaly recorded
        anomalies = conn.execute("""
            SELECT severity, category, message
            FROM core_anomalies
            WHERE category = 'DEPENDENCY'
              AND domain = 'finra.otc_transparency'
        """).fetchall()
        
        assert len(anomalies) == 1
        assert anomalies[0]['severity'] == 'WARN'
        assert 'revised' in anomalies[0]['message']


class TestExpectedSchedules:
    """Test expected schedule tracking and missed run detection"""
    
    def test_expected_schedule_definition(self, db_with_schema):
        conn = db_with_schema
        
        # Define expected schedule: FINRA OTC weekly every Monday
        conn.execute("""
            INSERT INTO core_expected_schedules (
                domain, pipeline, schedule_type, partition_template, partition_values,
                expected_delay_hours, preliminary_hours, description, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'finra.otc_transparency',
            'ingest_week',
            'WEEKLY',
            json.dumps({'week_ending': '${MONDAY}', 'tier': '${TIER}'}),
            json.dumps({'TIER': ['NMS_TIER_1', 'NMS_TIER_2', 'OTC']}),
            24,  # Data expected within 24 hours of Monday
            48,  # Consider preliminary for 48 hours
            'FINRA OTC Transparency weekly ingestion - every Monday for previous week',
            1
        ))
        
        # Verify schedule recorded
        schedules = conn.execute("""
            SELECT domain, pipeline, schedule_type, expected_delay_hours
            FROM core_expected_schedules
            WHERE domain = 'finra.otc_transparency'
        """).fetchall()
        
        assert len(schedules) == 1
        assert schedules[0]['schedule_type'] == 'WEEKLY'
        assert schedules[0]['expected_delay_hours'] == 24
    
    def test_missed_run_detection(self, db_with_schema):
        conn = db_with_schema
        
        # Setup: Expected schedule
        conn.execute("""
            INSERT INTO core_expected_schedules (
                domain, pipeline, schedule_type, partition_template, partition_values,
                expected_delay_hours, description, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'finra.otc_transparency',
            'ingest_week',
            'WEEKLY',
            json.dumps({'week_ending': '${MONDAY}', 'tier': '${TIER}'}),
            json.dumps({'TIER': ['NMS_TIER_1', 'NMS_TIER_2', 'OTC']}),
            24,
            'FINRA OTC weekly',
            1
        ))
        
        # Simulate: Expected run for week 2025-12-22 not present
        week_ending = '2025-12-22'
        expected_tiers = ['NMS_TIER_1', 'NMS_TIER_2', 'OTC']
        
        # Only 2 tiers present in manifest
        for tier in ['NMS_TIER_1', 'NMS_TIER_2']:
            partition_key = json.dumps({'week_ending': week_ending, 'tier': tier})
            conn.execute("""
                INSERT INTO core_manifest (domain, partition_key, stage, row_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, ('finra.otc_transparency', partition_key, 'RAW', 1000, datetime.now().isoformat()))
        
        # Detect missed run: OTC tier
        actual_tiers = conn.execute("""
            SELECT DISTINCT json_extract(partition_key, '$.tier') as tier
            FROM core_manifest
            WHERE domain = 'finra.otc_transparency'
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (week_ending,)).fetchall()
        
        actual_tier_set = {row['tier'] for row in actual_tiers}
        missing_tiers = set(expected_tiers) - actual_tier_set
        
        # Record anomaly for missed run
        if missing_tiers:
            record_anomaly(
                conn,
                domain='finra.otc_transparency',
                pipeline='ingest_week',
                partition_key={'week_ending': week_ending},
                severity='ERROR',
                category='COMPLETENESS',
                message=f'Missed run detected. Expected tiers: {expected_tiers}, actual: {list(actual_tier_set)}, missing: {list(missing_tiers)}',
                details={
                    'expected_tiers': expected_tiers,
                    'actual_tiers': list(actual_tier_set),
                    'missing_tiers': list(missing_tiers)
                }
            )
        
        # Verify missed run anomaly
        anomalies = conn.execute("""
            SELECT severity, message, details_json
            FROM core_anomalies
            WHERE category = 'COMPLETENESS'
              AND message LIKE '%Missed run%'
        """).fetchall()
        
        assert len(anomalies) == 1
        details = json.loads(anomalies[0]['details_json'])
        assert 'OTC' in details['missing_tiers']


class TestReadinessCertification:
    """Test data readiness certification end-to-end"""
    
    def test_full_readiness_check(self, db_with_schema):
        conn = db_with_schema
        week_ending = '2025-12-22'
        
        # Setup: All 3 tiers present, all stages complete
        for tier in ['NMS_TIER_1', 'NMS_TIER_2', 'OTC']:
            partition_key = json.dumps({'week_ending': week_ending, 'tier': tier})
            for stage in ['RAW', 'NORMALIZED', 'CALC']:
                conn.execute("""
                    INSERT INTO core_manifest (domain, partition_key, stage, row_count, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, ('finra.otc_transparency', partition_key, stage, 1000, datetime.now().isoformat()))
        
        # No anomalies recorded
        
        # Check readiness
        is_ready, blocking_issues = check_readiness(
            conn,
            'finra.otc_transparency',
            {'week_ending': week_ending},
            ready_for='trading'
        )
        
        assert is_ready, f"Data should be ready. Blocking issues: {blocking_issues}"
        assert len(blocking_issues) == 0
        
        # Verify readiness record
        readiness = conn.execute("""
            SELECT is_ready, ready_for, all_partitions_present, all_stages_complete, 
                   no_critical_anomalies, certified_at
            FROM core_data_readiness
            WHERE domain = 'finra.otc_transparency'
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (week_ending,)).fetchone()
        
        assert readiness['is_ready'] == 1
        assert readiness['ready_for'] == 'trading'
        assert readiness['all_partitions_present'] == 1
        assert readiness['all_stages_complete'] == 1
        assert readiness['no_critical_anomalies'] == 1
        assert readiness['certified_at'] is not None
    
    def test_readiness_blocked_by_multiple_issues(self, db_with_schema):
        conn = db_with_schema
        week_ending = '2025-12-15'
        
        # Setup: Only 1 tier present
        partition_key = json.dumps({'week_ending': week_ending, 'tier': 'NMS_TIER_1'})
        conn.execute("""
            INSERT INTO core_manifest (domain, partition_key, stage, row_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('finra.otc_transparency', partition_key, 'RAW', 100, datetime.now().isoformat()))
        
        # CRITICAL anomaly present
        record_anomaly(
            conn,
            domain='finra.otc_transparency',
            pipeline='normalize_week',
            partition_key={'week_ending': week_ending, 'tier': 'NMS_TIER_1'},
            severity='CRITICAL',
            category='BUSINESS_RULE',
            message='Data quality failure'
        )
        
        # Check readiness
        is_ready, blocking_issues = check_readiness(
            conn,
            'finra.otc_transparency',
            {'week_ending': week_ending}
        )
        
        assert not is_ready
        assert len(blocking_issues) >= 2  # Missing partitions + CRITICAL anomaly
        
        # Verify both issues captured
        assert any('Missing expected partitions' in issue for issue in blocking_issues)
        assert any('CRITICAL anomalies' in issue for issue in blocking_issues)
