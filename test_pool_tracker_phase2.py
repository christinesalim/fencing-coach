#!/usr/bin/env python3
"""Pool Tracker Phase 2 — schema + migration.

Verifies:
  - PoolRound model declares the 4 new columns
  - Columns are nullable (so existing rows don't break)
  - Can insert + read back values on the new columns
  - migrate_pool_tracker.py is idempotent (safe to run twice)

Exits 0 only if every scenario PASSes.
"""

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from database import PoolRound, Tournament, engine, get_db
from datetime import datetime


results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def cleanup():
    db = get_db()
    try:
        tids = [t.id for t in db.query(Tournament).filter(
            Tournament.name.like("PT2_TEST_%")
        ).all()]
        if tids:
            db.query(PoolRound).filter(PoolRound.tournament_id.in_(tids)).delete(
                synchronize_session=False
            )
            db.query(Tournament).filter(Tournament.id.in_(tids)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def main():
    cleanup()
    print("Pool Tracker Phase 2 — schema + migration")
    print("=" * 50)

    # 1. Model declares the 4 new columns ------------------------------
    cols = {c.name for c in PoolRound.__table__.columns}
    expected = {"strip_number", "roster_json", "bout_order_json", "ethan_pool_num"}
    record(
        "model: PoolRound declares strip_number + roster_json + bout_order_json + ethan_pool_num",
        expected.issubset(cols),
        f"missing={expected - cols}",
    )

    # 2. New columns are nullable --------------------------------------
    nullability = {
        c.name: c.nullable for c in PoolRound.__table__.columns
        if c.name in expected
    }
    record(
        "model: all new columns are nullable",
        all(nullability.values()),
        f"nullability={nullability}",
    )

    # 3. Round-trip insert on the new columns --------------------------
    # Create a tournament, insert a PoolRound with all new fields set,
    # read it back, assert values match.
    db = get_db()
    try:
        t = Tournament(name="PT2_TEST_T", date=datetime(2026, 1, 1))
        db.add(t); db.commit()
        tid = t.id
    finally:
        db.close()

    roster = [{"pool_num": 1, "last_name": "SALIM", "first_name": "Ethan"}]
    bouts = [{"order": 1, "right_num": 1, "left_num": 2, "done": False}]
    db = get_db()
    try:
        pr = PoolRound(
            tournament_id=tid,
            pool_number=5,
            strip_number=6,
            roster_json=json.dumps(roster),
            bout_order_json=json.dumps(bouts),
            ethan_pool_num=1,
        )
        db.add(pr); db.commit()
        pr_id = pr.id
    finally:
        db.close()

    db = get_db()
    try:
        got = db.query(PoolRound).filter_by(id=pr_id).first()
        round_trip_ok = (
            got.pool_number == 5
            and got.strip_number == 6
            and got.ethan_pool_num == 1
            and json.loads(got.roster_json or "[]") == roster
            and json.loads(got.bout_order_json or "[]") == bouts
        )
    finally:
        db.close()
    record(
        "db: round-trip insert + read on all new columns",
        round_trip_ok,
        "" if round_trip_ok else f"strip={got.strip_number} ethan={got.ethan_pool_num}",
    )

    # 4. Existing-row safety: a PoolRound with only old fields set still
    #    works (new columns default to NULL)
    db = get_db()
    try:
        legacy = PoolRound(tournament_id=tid, pool_number=1, victories=3)
        db.add(legacy); db.commit()
        legacy_id = legacy.id
    finally:
        db.close()
    db = get_db()
    try:
        got = db.query(PoolRound).filter_by(id=legacy_id).first()
        legacy_ok = (
            got.pool_number == 1
            and got.victories == 3
            and got.strip_number is None
            and got.roster_json is None
            and got.bout_order_json is None
            and got.ethan_pool_num is None
        )
    finally:
        db.close()
    record(
        "db: legacy-style insert (old fields only) leaves new cols NULL",
        legacy_ok,
    )

    # 5. Migration script is idempotent --------------------------------
    # On SQLite the columns already exist (added by create_all when the
    # module imports), so the first run should report everything skipped,
    # and the second run should match.
    script = Path(__file__).parent / "migrate_pool_tracker.py"
    r1 = subprocess.run(["python3", str(script)], capture_output=True, text=True)
    r2 = subprocess.run(["python3", str(script)], capture_output=True, text=True)
    record(
        "migration: script exits 0 both runs (idempotent)",
        r1.returncode == 0 and r2.returncode == 0,
        f"r1={r1.returncode} r2={r2.returncode} err1={r1.stderr[:120]}",
    )
    # Both runs should report the same set of skipped columns on SQLite
    record(
        "migration: second run matches first (no spurious adds)",
        r1.stdout.strip() == r2.stdout.strip(),
        f"\n    r1={r1.stdout.strip()!r}\n    r2={r2.stdout.strip()!r}",
    )

    cleanup()

    print()
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("All tests passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
