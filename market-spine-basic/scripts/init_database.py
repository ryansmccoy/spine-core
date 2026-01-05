#!/usr/bin/env python3
"""Initialize Market Spine database with core schema."""

import argparse
import sqlite3
import sys
from pathlib import Path


def init_database(db_path: Path, force: bool = False) -> None:
    """Initialize database with core tables.
    
    Args:
        db_path: Path to SQLite database file
        force: Drop existing tables if they exist (default: False)
    """
    if db_path.exists() and not force:
        print(f"Database already exists: {db_path}")
        response = input("Recreate tables? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    
    # Create parent directory if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    
    if force:
        print("Dropping existing tables...")
        conn.executescript("""
            DROP TABLE IF EXISTS core_data_readiness;
            DROP TABLE IF EXISTS core_anomalies;
            DROP TABLE IF EXISTS core_manifest;
        """)
    
    print("Creating core tables...")
    conn.executescript("""
        -- Core Manifest: Track all data captures/ingestions
        CREATE TABLE IF NOT EXISTS core_manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            stage TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            row_count INTEGER,
            metadata_json TEXT,
            capture_id TEXT,
            captured_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_manifest_domain_partition 
            ON core_manifest(domain, partition_key);
        CREATE INDEX IF NOT EXISTS idx_manifest_capture_id 
            ON core_manifest(capture_id);
        CREATE INDEX IF NOT EXISTS idx_manifest_stage 
            ON core_manifest(stage);
        
        -- Core Anomalies: Track data quality issues
        CREATE TABLE IF NOT EXISTS core_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            pipeline TEXT,
            partition_key TEXT,
            stage TEXT,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            affected_records INTEGER,
            execution_id TEXT,
            capture_id TEXT,
            detected_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution_note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_anomalies_domain 
            ON core_anomalies(domain);
        CREATE INDEX IF NOT EXISTS idx_anomalies_severity 
            ON core_anomalies(severity);
        CREATE INDEX IF NOT EXISTS idx_anomalies_partition 
            ON core_anomalies(partition_key);
        CREATE INDEX IF NOT EXISTS idx_anomalies_capture 
            ON core_anomalies(capture_id);
        
        -- Core Data Readiness: Track data certification status
        CREATE TABLE IF NOT EXISTS core_data_readiness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            is_ready INTEGER DEFAULT 0,
            ready_for TEXT,
            all_partitions_present INTEGER DEFAULT 0,
            all_stages_complete INTEGER DEFAULT 0,
            no_critical_anomalies INTEGER DEFAULT 0,
            blocking_issues TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(domain, partition_key, ready_for)
        );
        
        CREATE INDEX IF NOT EXISTS idx_readiness_domain_partition 
            ON core_data_readiness(domain, partition_key);
        CREATE INDEX IF NOT EXISTS idx_readiness_status 
            ON core_data_readiness(is_ready);
    """)
    
    conn.commit()
    conn.close()
    
    print(f"✓ Database initialized: {db_path}")
    print("\nTables created:")
    print("  - core_manifest (data capture tracking)")
    print("  - core_anomalies (data quality issues)")
    print("  - core_data_readiness (certification status)")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Initialize Market Spine database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/market_spine.db"),
        help="Database file path (default: data/market_spine.db)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop existing tables without prompting",
    )
    
    args = parser.parse_args()
    
    try:
        init_database(args.db, args.force)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
