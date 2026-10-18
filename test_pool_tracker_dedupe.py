#!/usr/bin/env python3
"""Quick Start dedupe behavior.

Repeated Quick Start taps shouldn't create duplicate "Pool — <today>"
tournaments or new PoolRounds while a previous one is still in progress.
Exits 0 only if every scenario PASSes.
"""

import sys
from datetime import datetime, timedelta

from app import app
from database import PoolRound, Tournament, get_db


PREFIX = "PT_DEDUPE_TEST_"
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


def cleanup():
    """Remove today's "Pool — <today>" tournament plus any test-prefix rows.
    Done both at start and end so repeated test runs stay independent of
    whichever Quick Start taps the user has done in the real UI."""
    db = get_db()
    try:
        today_name = f"Pool — {datetime.utcnow().strftime('%Y-%m-%d')}"
        tids = [t.id for t in db.query(Tournament).filter(
            (Tournament.name.like(f"{PREFIX}%"))
            | (Tournament.name == today_name)
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


def quick_start(c, tournament_id=None):
    payload = {}
    if tournament_id is not None:
        payload["tournament_id"] = tournament_id
    return c.post("/api/pool-tracker/quick-start", json=payload)


def count_today_drafts():
    db = get_db()
    try:
        today_name = f"Pool — {datetime.utcnow().strftime('%Y-%m-%d')}"
        return db.query(Tournament).filter(Tournament.name == today_name).count()
    finally:
        db.close()


def main():
    cleanup()
    print("Pool Tracker Quick Start dedupe")
    print("=" * 50)

    c = authed_client()

    # 1. First tap of the day: creates tournament + round, not reused ----
    r = quick_start(c)
    body = r.get_json() or {}
    first_tid = body.get("tournament_id")
    first_prid = body.get("pool_round_id")
    record(
        "first tap: creates tournament + round, reused=false",
        r.status_code == 200
        and body.get("success") is True
        and body.get("reused") is False
        and isinstance(first_tid, int)
        and isinstance(first_prid, int)
        and count_today_drafts() == 1,
        f"status={r.status_code} tid={first_tid} prid={first_prid} drafts_today={count_today_drafts()}",
    )

    # 2. Second tap, round still unfinished: resumes same round ----------
    r = quick_start(c)
    body = r.get_json() or {}
    record(
        "second tap, round unfinished: resumes same tournament AND round",
        r.status_code == 200
        and body.get("reused") is True
        and body.get("tournament_id") == first_tid
        and body.get("pool_round_id") == first_prid
        and count_today_drafts() == 1,
        f"tid={body.get('tournament_id')}/{first_tid} prid={body.get('pool_round_id')}/{first_prid} drafts={count_today_drafts()}",
    )

    # 3. Finalize round 1 (set victories), then tap: should get a NEW
    #    round on the SAME tournament (not a new tournament) ------------
    db = get_db()
    try:
        pr = db.query(PoolRound).filter_by(id=first_prid).first()
        pr.victories = 3
        pr.defeats = 2
        pr.touches_scored = 20
        pr.touches_received = 14
        pr.indicator = 6
        db.commit()
    finally:
        db.close()

    r = quick_start(c)
    body = r.get_json() or {}
    second_prid = body.get("pool_round_id")
    record(
        "finalized round + tap: new round on SAME tournament, reused=false",
        r.status_code == 200
        and body.get("tournament_id") == first_tid
        and body.get("reused") is False
        and second_prid != first_prid
        and count_today_drafts() == 1,
        f"second_prid={second_prid} vs first_prid={first_prid} drafts={count_today_drafts()}",
    )

    # 4. Tap again with the NEW unfinished round: should resume it -------
    r = quick_start(c)
    body = r.get_json() or {}
    record(
        "second-round tap: resumes the newly-created second round",
        r.status_code == 200
        and body.get("reused") is True
        and body.get("pool_round_id") == second_prid
        and count_today_drafts() == 1,
        f"got_prid={body.get('pool_round_id')} expected={second_prid}",
    )

    # 5. Yesterday's draft shouldn't be reused -- a new day gets a fresh
    #    tournament even if an unfinished round from yesterday exists ----
    db = get_db()
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        y_name = f"Pool — {yesterday.strftime('%Y-%m-%d')}"
        y_tourney = Tournament(name=y_name, date=yesterday)
        db.add(y_tourney); db.commit()
        y_round = PoolRound(tournament_id=y_tourney.id)  # unfinished (victories=None)
        db.add(y_round); db.commit()
        y_tid = y_tourney.id
        y_prid = y_round.id
    finally:
        db.close()

    r = quick_start(c)
    body = r.get_json() or {}
    record(
        "yesterday's unfinished draft is NOT reused today",
        r.status_code == 200
        and body.get("tournament_id") != y_tid
        and body.get("pool_round_id") != y_prid,
        f"got_tid={body.get('tournament_id')} y_tid={y_tid}",
    )

    # 6. Explicit tournament_id (tournament-detail flow) always creates
    #    a new round and never reuses ---------------------------------
    db = get_db()
    try:
        existing = Tournament(name=f"{PREFIX}EXISTING_TOURNEY", date=datetime(2026,1,1))
        db.add(existing); db.commit()
        existing_tid = existing.id
    finally:
        db.close()

    r = quick_start(c, tournament_id=existing_tid)
    body = r.get_json() or {}
    first_pr_on_existing = body.get("pool_round_id")
    record(
        "with tournament_id: creates new round, reused=false",
        r.status_code == 200
        and body.get("tournament_id") == existing_tid
        and body.get("reused") is False
        and isinstance(first_pr_on_existing, int),
        f"status={r.status_code} tid={body.get('tournament_id')} prid={first_pr_on_existing}",
    )

    r = quick_start(c, tournament_id=existing_tid)
    body = r.get_json() or {}
    record(
        "with tournament_id: second call ALWAYS creates another new round (no resume on explicit flow)",
        r.status_code == 200
        and body.get("reused") is False
        and body.get("pool_round_id") != first_pr_on_existing,
        f"second_prid={body.get('pool_round_id')} vs first={first_pr_on_existing}",
    )

    # Separate cleanup for yesterday + existing tournaments
    db = get_db()
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        y_name = f"Pool — {yesterday.strftime('%Y-%m-%d')}"
        extra_tids = [t.id for t in db.query(Tournament).filter(
            Tournament.name == y_name
        ).all()]
        if extra_tids:
            db.query(PoolRound).filter(PoolRound.tournament_id.in_(extra_tids)).delete(
                synchronize_session=False
            )
            db.query(Tournament).filter(Tournament.id.in_(extra_tids)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()

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
