#!/usr/bin/env python3
"""Quick script to inspect the full_demo.db after population."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "full_demo.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r["name"] for r in cur.fetchall()]
print(f"Total tables: {len(tables)}\n")

total_rows = 0
for t in tables:
    cur.execute(f"SELECT COUNT(*) as cnt FROM [{t}]")
    cnt = cur.fetchone()["cnt"]
    total_rows += cnt
    marker = "+" if cnt > 0 else "-"
    print(f"  {marker} {t:40s}  {cnt:>5d} rows")
    if cnt > 0:
        cur.execute(f"SELECT * FROM [{t}] LIMIT 1")
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        vals = list(row)
        sample = ", ".join(f"{c}={v!r}" for c, v in zip(cols[:5], vals[:5]))
        print(f"      sample: {sample}")

print(f"\nTotal: {total_rows} rows across {len(tables)} tables")
conn.close()
