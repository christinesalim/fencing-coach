#!/usr/bin/env python3
"""Pool Tracker Stage 3 — end-of-pool finalize + grid summary.

Verifies:
  - /api/pool-tracker/<id>/finalize computes V/D/TS/TR/Ind from bout_order_json
    and writes them to PoolRound summary columns
  - finalize creates one PoolBout row per Ethan bout with the correct
    opponent_name, opponent_club, score_for/against, result, bout_order
  - finalize is idempotent: calling it twice yields the same PoolBout rows
    (no duplicates) and same summary stats
  - finalize correctly ignores bouts without complete scores (partial pool)
  - finalize rejects when ethan_pool_num is null (400)
  - finalize 404s on unknown pool_round_id
  - auth is enforced
  - template exposes summaryView + renderSummary + savePoolFinal + finalize URL

Exits 0 only if every scenario PASSes.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from app import app
from database import PoolBout, PoolRound, Tournament, get_db


PREFIX = "PT_S3_TEST_"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "pool_tracker.html"
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


def make_pool_round(**fields):
    """Create a tournament + pool round. Returns pool_round_id."""
    db = get_db()
    try:
        t = Tournament(name=f"{PREFIX}T", date=datetime(2026, 1, 1))
        db.add(t); db.commit()
        tid = t.id
    finally:
        db.close()
    db = get_db()
    try:
        pr = PoolRound(tournament_id=tid, **fields)
        db.add(pr); db.commit()
        return pr.id
    finally:
        db.close()


def read_pr(pr_id):
    db = get_db()
    try:
        pr = db.query(PoolRound).filter_by(id=pr_id).first()
        if not pr: return None
        return {
            "victories": pr.victories,
            "defeats": pr.defeats,
            "touches_scored": pr.touches_scored,
            "touches_received": pr.touches_received,
            "indicator": pr.indicator,
        }
    finally:
        db.close()


def read_pool_bouts(pr_id):
    db = get_db()
    try:
        return [
            {
                "opponent_name": pb.opponent_name,
                "opponent_club": pb.opponent_club,
                "score_for": pb.score_for,
                "score_against": pb.score_against,
                "result": pb.result,
                "bout_order": pb.bout_order,
            }
            for pb in db.query(PoolBout).filter_by(pool_round_id=pr_id)
            .order_by(PoolBout.bout_order).all()
        ]
    finally:
        db.close()


def cleanup():
    db = get_db()
    try:
        tids = [t.id for t in db.query(Tournament).filter(
            Tournament.name.like(f"{PREFIX}%")
        ).all()]
        if tids:
            prids = [p.id for p in db.query(PoolRound).filter(
                PoolRound.tournament_id.in_(tids)
            ).all()]
            if prids:
                db.query(PoolBout).filter(PoolBout.pool_round_id.in_(prids)).delete(
                    synchronize_session=False
                )
            db.query(PoolRound).filter(PoolRound.tournament_id.in_(tids)).delete(
                synchronize_session=False
            )
            db.query(Tournament).filter(Tournament.id.in_(tids)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


# Roster: Ethan is pool position 3, surrounded by 5 others.
ROSTER = [
    {"pool_num": 1, "last_name": "BOROVIKOV", "first_name": "Alexander", "club": "AFM"},
    {"pool_num": 2, "last_name": "ZHU",       "first_name": "Alex",      "club": "AFM"},
    {"pool_num": 3, "last_name": "SALIM",     "first_name": "Ethan",     "club": "AFM"},
    {"pool_num": 4, "last_name": "HOLBROOK",  "first_name": "Kieran",    "club": "EBFG"},
    {"pool_num": 5, "last_name": "XIAO",      "first_name": "Yijian",    "club": "BAYFC"},
    {"pool_num": 6, "last_name": "POLIAKOV",  "first_name": "Timur",     "club": "CAP"},
]

# A full pool of 15 bouts; Ethan (pool 3) plays bouts 3, 5, 9, 12, 14.
# Scored only his 5 bouts + one non-Ethan bout (bout 1) to confirm non-Ethan
# scored bouts are ignored by the finalize math.
ETHAN = 3
BOUTS = [
    # Non-Ethan bouts (ignored by finalize math)
    {"order": 1,  "right_num": 1, "left_num": 2, "done": True, "right_score": 5, "left_score": 3},
    {"order": 2,  "right_num": 4, "left_num": 5, "done": False, "right_score": None, "left_score": None},
    # Ethan: lost 2-5 vs ZHU (opponent #2 on right)
    {"order": 3,  "right_num": 2, "left_num": 3, "done": True, "right_score": 5, "left_score": 2},
    {"order": 4,  "right_num": 1, "left_num": 5, "done": False, "right_score": None, "left_score": None},
    # Ethan: won 5-3 vs BOROVIKOV
    {"order": 5,  "right_num": 3, "left_num": 1, "done": True, "right_score": 5, "left_score": 3},
    {"order": 6,  "right_num": 6, "left_num": 2, "done": False, "right_score": None, "left_score": None},
    {"order": 7,  "right_num": 4, "left_num": 1, "done": False, "right_score": None, "left_score": None},
    {"order": 8,  "right_num": 5, "left_num": 2, "done": False, "right_score": None, "left_score": None},
    # Ethan: won 5-2 vs XIAO
    {"order": 9,  "right_num": 5, "left_num": 3, "done": True, "right_score": 2, "left_score": 5},
    {"order": 10, "right_num": 6, "left_num": 1, "done": False, "right_score": None, "left_score": None},
    {"order": 11, "right_num": 2, "left_num": 4, "done": False, "right_score": None, "left_score": None},
    # Ethan: lost 2-5 vs POLIAKOV
    {"order": 12, "right_num": 3, "left_num": 6, "done": True, "right_score": 2, "left_score": 5},
    {"order": 13, "right_num": 5, "left_num": 4, "done": False, "right_score": None, "left_score": None},
    # Ethan: won 5-4 vs HOLBROOK
    {"order": 14, "right_num": 3, "left_num": 4, "done": True, "right_score": 5, "left_score": 4},
    {"order": 15, "right_num": 1, "left_num": 2, "done": False, "right_score": None, "left_score": None},
]

# Ethan: 3V (vs BORO, XIAO, HOLB) - 2D (vs ZHU, POLI)
# TS = 5 + 5 + 5 + 2 + 2 = 19
# TR = 3 + 2 + 4 + 5 + 5 = 19
# Ind = 0


def main():
    cleanup()
    print("Pool Tracker Stage 3 — finalize + summary grid")
    print("=" * 55)

    # 1. Template surfaces --------------------------------------------
    tpl = TEMPLATE_PATH.read_text()
    checks = [
        ("summaryView exists",              'id="summaryView"' in tpl),
        ("renderSummary defined",           'function renderSummary' in tpl),
        ("savePoolFinal defined",           'function savePoolFinal' in tpl),
        ("backToTracker defined",           'function backToTracker' in tpl),
        ("hits /finalize endpoint",         '/finalize' in tpl),
        ("summary stats row (V–D, Ind, TS, TR tiles)",
            "statTile('V" in tpl and "statTile('Ind'" in tpl
            and "statTile('TS'" in tpl and "statTile('TR'" in tpl),
        ("partial-data note slot present",  'summaryPartial' in tpl),
        ("grid orders columns by pool_num (sort ascending)",
            '.sort((a, b) => a.pool_num - b.pool_num)' in tpl),
        ("grid skips Ethan's own column",   "r => r.pool_num !== e" in tpl),
        ("edits re-render summary too",     'renderSummary();' in tpl),
    ]
    for name, ok in checks:
        record(f"template: {name}", ok)

    # 2. Auth ---------------------------------------------------------
    r = app.test_client().post("/api/pool-tracker/1/finalize")
    record(
        "auth: finalize 302s unauth",
        r.status_code == 302 and "/login" in (r.headers.get("Location") or ""),
        f"status={r.status_code}",
    )

    c = authed_client()

    # 3. Happy path finalize ------------------------------------------
    pr_id = make_pool_round(
        pool_number=5, strip_number="6", ethan_pool_num=ETHAN,
        roster_json=json.dumps(ROSTER), bout_order_json=json.dumps(BOUTS),
    )
    r = c.post(f"/api/pool-tracker/{pr_id}/finalize")
    data = r.get_json() or {}
    pr_summary = read_pr(pr_id)
    record(
        "finalize: returns V/D/TS/TR/Ind matching Ethan's scored bouts (3V-2D, 19-19, ind 0)",
        r.status_code == 200
        and data.get("victories") == 3 and data.get("defeats") == 2
        and data.get("touches_scored") == 19 and data.get("touches_received") == 19
        and data.get("indicator") == 0
        and data.get("scored_bouts") == 5 and data.get("total_ethan_bouts") == 5,
        f"status={r.status_code} data={data}",
    )
    record(
        "finalize: writes same stats onto PoolRound summary cols",
        pr_summary == {"victories": 3, "defeats": 2, "touches_scored": 19,
                       "touches_received": 19, "indicator": 0},
        f"summary={pr_summary}",
    )

    # 4. PoolBout rows created correctly ------------------------------
    pbs = read_pool_bouts(pr_id)
    expected = [
        {"opponent_name": "ZHU Alex",       "opponent_club": "AFM",   "score_for": 2, "score_against": 5, "result": "lost", "bout_order": 3},
        {"opponent_name": "BOROVIKOV Alexander", "opponent_club": "AFM", "score_for": 5, "score_against": 3, "result": "won",  "bout_order": 5},
        {"opponent_name": "XIAO Yijian",    "opponent_club": "BAYFC", "score_for": 5, "score_against": 2, "result": "won",  "bout_order": 9},
        {"opponent_name": "POLIAKOV Timur", "opponent_club": "CAP",   "score_for": 2, "score_against": 5, "result": "lost", "bout_order": 12},
        {"opponent_name": "HOLBROOK Kieran", "opponent_club": "EBFG", "score_for": 5, "score_against": 4, "result": "won",  "bout_order": 14},
    ]
    record(
        "finalize: creates exactly 5 PoolBout rows (one per Ethan bout), scores + opponent info correct",
        pbs == expected,
        f"got={pbs}",
    )

    # 5. Idempotent — second call doesn't duplicate rows -------------
    c.post(f"/api/pool-tracker/{pr_id}/finalize")
    pbs2 = read_pool_bouts(pr_id)
    record(
        "finalize: idempotent — second call = same 5 rows, no duplicates",
        pbs2 == expected,
        f"count={len(pbs2)}",
    )

    # 6. Partial pool: unscored Ethan bouts excluded from totals -----
    partial_bouts = [dict(b) for b in BOUTS]
    # Clear scores for bout 14 (Ethan vs HOLB) → should go from 3V-2D to 2V-2D
    for b in partial_bouts:
        if b["order"] == 14:
            b["right_score"] = None
            b["left_score"] = None
            b["done"] = False
    partial_id = make_pool_round(
        pool_number=5, strip_number="6", ethan_pool_num=ETHAN,
        roster_json=json.dumps(ROSTER), bout_order_json=json.dumps(partial_bouts),
    )
    r = c.post(f"/api/pool-tracker/{partial_id}/finalize")
    data = r.get_json() or {}
    record(
        "finalize: partial pool (4 of 5 Ethan bouts scored) → 2V-2D, TS 14, TR 15",
        r.status_code == 200
        and data.get("victories") == 2 and data.get("defeats") == 2
        and data.get("touches_scored") == 14 and data.get("touches_received") == 15
        and data.get("scored_bouts") == 4 and data.get("total_ethan_bouts") == 5,
        f"data={data}",
    )

    # 7. Ethan missing → 400 ------------------------------------------
    missing_id = make_pool_round(
        pool_number=5, ethan_pool_num=None,
        roster_json=json.dumps(ROSTER), bout_order_json=json.dumps(BOUTS),
    )
    r = c.post(f"/api/pool-tracker/{missing_id}/finalize")
    body = r.get_json() or {}
    record(
        "finalize: ethan_pool_num=null → 400 w/ actionable error",
        r.status_code == 400 and "Ethan" in (body.get("error") or ""),
        f"status={r.status_code} body={body}",
    )

    # 8. Unknown pool_round_id → 404 ---------------------------------
    r = c.post("/api/pool-tracker/999999/finalize")
    record(
        "finalize: unknown pool_round_id → 404",
        r.status_code == 404,
        f"status={r.status_code}",
    )

    # 9. Zero Ethan bouts scored → 0 everything, 0 PoolBouts ---------
    zero_bouts = [dict(b, right_score=None, left_score=None, done=False) for b in BOUTS]
    zero_id = make_pool_round(
        pool_number=5, ethan_pool_num=ETHAN,
        roster_json=json.dumps(ROSTER), bout_order_json=json.dumps(zero_bouts),
    )
    r = c.post(f"/api/pool-tracker/{zero_id}/finalize")
    data = r.get_json() or {}
    record(
        "finalize: no Ethan bouts scored → all zeros, no PoolBout rows",
        r.status_code == 200
        and data.get("victories") == 0 and data.get("defeats") == 0
        and data.get("touches_scored") == 0 and data.get("touches_received") == 0
        and data.get("scored_bouts") == 0
        and len(read_pool_bouts(zero_id)) == 0,
        f"data={data}",
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
