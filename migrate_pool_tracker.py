#!/usr/bin/env python3
"""Pool Tracker — add new columns to pool_rounds.

SQLAlchemy's create_all adds new tables but NOT new columns on existing
tables, so this script runs the ALTER TABLE statements manually. Safe to
run multiple times — each column add is guarded by an existence check.

Run once on each environment after deploying the Phase 2 schema change:
    python3 migrate_pool_tracker.py

On Render, run via Shell tab in the dashboard (or Render Jobs).
"""

import sys

from sqlalchemy import text

from database import engine


COLUMNS = [
    ("strip_number", "INTEGER"),
    ("roster_json", "TEXT"),
    ("bout_order_json", "TEXT"),
    ("ethan_pool_num", "INTEGER"),
]


def existing_columns(conn, table):
    """Return the set of column names on `table`. Works on SQLite + Postgres."""
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}
    # postgresql
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :t"
    ), {"t": table}).fetchall()
    return {r[0] for r in rows}


def main():
    added = []
    skipped = []
    with engine.begin() as conn:
        existing = existing_columns(conn, "pool_rounds")
        for col_name, col_type in COLUMNS:
            if col_name in existing:
                skipped.append(col_name)
                continue
            conn.execute(text(
                f"ALTER TABLE pool_rounds ADD COLUMN {col_name} {col_type}"
            ))
            added.append(col_name)

    print(f"Pool Tracker migration on {engine.url.get_backend_name()}:")
    if added:
        print(f"  added:   {', '.join(added)}")
    if skipped:
        print(f"  skipped (already present): {', '.join(skipped)}")
    if not added and not skipped:
        print("  nothing to do (pool_rounds table missing?)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"MIGRATION FAILED: {e}", file=sys.stderr)
        sys.exit(1)
