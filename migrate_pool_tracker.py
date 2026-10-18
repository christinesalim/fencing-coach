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
    ("strip_number", "VARCHAR(20)"),   # bumped from INTEGER — see fix_strip_number_type()
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


def strip_number_type(conn):
    """Return the current SQL type of pool_rounds.strip_number, or None if the
    column doesn't exist. Used to detect if the type upgrade is needed."""
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text("PRAGMA table_info(pool_rounds)")).fetchall()
        for r in rows:
            # (cid, name, type, notnull, dflt_value, pk)
            if r[1] == "strip_number":
                return (r[2] or "").upper()
        return None
    rows = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'pool_rounds' AND column_name = 'strip_number'"
    )).fetchall()
    return rows[0][0].upper() if rows else None


def fix_strip_number_type(conn):
    """Bump strip_number from INTEGER to VARCHAR(20). Dual-strip pools come
    back from Vision as strings like '9-10'; Postgres rejects those with
    'invalid input syntax for type integer'. Returns True if a change was
    applied, False if already string-like.
    """
    cur = strip_number_type(conn)
    if cur is None or not cur.startswith("INT"):
        return False  # column missing OR already a string type

    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        # SQLite can't ALTER COLUMN TYPE directly. Drop + re-add is safe
        # because no deployment has stored strip values yet (if any had,
        # they'd be bare ints and losing them is acceptable).
        conn.execute(text("ALTER TABLE pool_rounds DROP COLUMN strip_number"))
        conn.execute(text("ALTER TABLE pool_rounds ADD COLUMN strip_number VARCHAR(20)"))
    else:
        # Postgres: USING ... :: TEXT handles any existing integer values.
        conn.execute(text(
            "ALTER TABLE pool_rounds ALTER COLUMN strip_number "
            "TYPE VARCHAR(20) USING strip_number::text"
        ))
    return True


def main():
    added = []
    skipped = []
    strip_upgraded = False
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
        strip_upgraded = fix_strip_number_type(conn)

    print(f"Pool Tracker migration on {engine.url.get_backend_name()}:")
    if added:
        print(f"  added:   {', '.join(added)}")
    if skipped:
        print(f"  skipped (already present): {', '.join(skipped)}")
    if strip_upgraded:
        print("  upgraded: strip_number INTEGER -> VARCHAR(20) (dual-strip pools)")
    if not added and not skipped and not strip_upgraded:
        print("  nothing to do (pool_rounds table missing?)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"MIGRATION FAILED: {e}", file=sys.stderr)
        sys.exit(1)
