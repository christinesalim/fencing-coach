#!/usr/bin/env python3
"""Smoke test: tournament_detail page surfaces a Resume Pool Tracker banner
for any PoolRound on the tournament that has roster data.

Prevents the "I lost my in-progress pool and can't find the URL" regression
that triggered this fix.

Exits 0 only if every scenario PASSes.
"""

import json
import sys
from datetime import datetime

from app import app
from database import PoolRound, Tournament, get_db


PREFIX = "PT_RES_TEST_"
results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def authed_client():
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    return c


def make_tournament():
    db = get_db()
    try:
        t = Tournament(name=f"{PREFIX}T", date=datetime(2026, 1, 1))
        db.add(t); db.commit()
        return t.id
    finally:
        db.close()


def make_pool_round(tid, **fields):
    db = get_db()
    try:
        pr = PoolRound(tournament_id=tid, **fields)
        db.add(pr); db.commit()
        return pr.id
    finally:
        db.close()


def cleanup():
    db = get_db()
    try:
        tids = [t.id for t in db.query(Tournament).filter(
            Tournament.name.like(f"{PREFIX}%")
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
    print("Pool Tracker resume-banner smoke test")
    print("=" * 50)

    c = authed_client()

    # Case A: tournament with no PoolRound rows at all --------------
    tid = make_tournament()
    html = c.get(f"/tournaments/{tid}").get_data(as_text=True)
    record(
        "no pool rounds → no resume banner",
        "Resume Pool Tracker" not in html,
    )

    # Case B: PoolRound exists but has NO roster_json (just an empty
    # shell from Quick Start that was abandoned pre-upload) ---------
    make_pool_round(tid)
    html = c.get(f"/tournaments/{tid}").get_data(as_text=True)
    record(
        "empty PoolRound (no roster yet) → still no resume banner",
        "Resume Pool Tracker" not in html,
    )

    # Case C: PoolRound with roster_json → banner shows a link to it
    bouts = [
        {"order": 1, "right_num": 1, "left_num": 2, "done": True, "right_score": 5, "left_score": 3},
        {"order": 2, "right_num": 4, "left_num": 5, "done": False, "right_score": None, "left_score": None},
        {"order": 3, "right_num": 2, "left_num": 3, "done": True, "right_score": 2, "left_score": 5},
    ]
    pr_id = make_pool_round(
        tid,
        pool_number=5,
        strip_number="9-10",
        roster_json=json.dumps([{"pool_num": 1, "last_name": "FOO", "first_name": "Bar"}]),
        bout_order_json=json.dumps(bouts),
    )
    html = c.get(f"/tournaments/{tid}").get_data(as_text=True)
    record(
        "populated PoolRound → banner with link + pool # + strip + progress",
        "Resume Pool Tracker" in html
        and f"/pool-tracker/{pr_id}" in html
        and "Pool #5" in html
        and "Strip 9-10" in html
        and "2 of 3 done" in html,
    )

    # Case D: multiple pool rounds → all listed (newest first) ------
    pr_id2 = make_pool_round(
        tid,
        pool_number=6,
        roster_json=json.dumps([{"pool_num": 1, "last_name": "X", "first_name": "Y"}]),
        bout_order_json=json.dumps([]),
    )
    html = c.get(f"/tournaments/{tid}").get_data(as_text=True)
    record(
        "multiple populated PoolRounds → all shown; newest id listed first",
        f"/pool-tracker/{pr_id}" in html
        and f"/pool-tracker/{pr_id2}" in html
        and html.find(f"/pool-tracker/{pr_id2}") < html.find(f"/pool-tracker/{pr_id}"),
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
