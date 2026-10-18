#!/usr/bin/env python3
"""Pool Tracker Stage 2 — live tracker UI + save endpoints.

Verifies:
  - /pool-tracker/<id> renders the real template (not placeholder)
  - Initial state hydrates from the PoolRound row into window.POOL_STATE
  - Empty roster renders upload view; populated roster renders tracker
  - /api/pool-tracker/<id>/save-extraction persists roster+bouts+scalars
  - /api/pool-tracker/<id>/update autosave replaces bouts in place
  - Both save endpoints validate payload shape (bouts list, score range)
  - Both endpoints are auth-gated
  - Template exposes the key JS functions and modal elements

Exits 0 only if every scenario PASSes.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from app import app
from database import PoolRound, Tournament, get_db


PREFIX = "PT_S2_TEST_"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "pool_tracker.html"
PLACEHOLDER_PATH = Path(__file__).parent / "templates" / "pool_tracker_placeholder.html"

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


def read_pool_round(pr_id):
    db = get_db()
    try:
        pr = db.query(PoolRound).filter_by(id=pr_id).first()
        if not pr:
            return None
        return {
            "pool_number": pr.pool_number,
            "strip_number": pr.strip_number,
            "ethan_pool_num": pr.ethan_pool_num,
            "roster": json.loads(pr.roster_json) if pr.roster_json else None,
            "bouts": json.loads(pr.bout_order_json) if pr.bout_order_json else None,
        }
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


ROSTER = [
    {"pool_num": 1, "last_name": "BOROVIKOV", "first_name": "Alexander", "club": "AFM", "region": "Central California"},
    {"pool_num": 2, "last_name": "ZHU", "first_name": "Alexander", "club": "AFM", "region": "Central California"},
    {"pool_num": 3, "last_name": "SALIM", "first_name": "Ethan", "club": "AFM", "region": "Central California"},
    {"pool_num": 4, "last_name": "HOLBROOK", "first_name": "Kieran", "club": "EBFG", "region": "Northern California"},
    {"pool_num": 5, "last_name": "XIAO", "first_name": "Yijian", "club": "BAYFC", "region": "Central California"},
    {"pool_num": 6, "last_name": "POLIAKOV", "first_name": "Timur", "club": "CAP", "region": "Central California"},
]
BOUTS = [
    {"order": 1, "right_num": 1, "left_num": 2, "done": False, "right_score": None, "left_score": None},
    {"order": 2, "right_num": 4, "left_num": 5, "done": False, "right_score": None, "left_score": None},
    {"order": 3, "right_num": 2, "left_num": 3, "done": True,  "right_score": 2,    "left_score": 5},
]


def main():
    cleanup()
    print("Pool Tracker Stage 2 — live tracker + save endpoints")
    print("=" * 55)

    # 0. Placeholder template is gone --------------------------------
    record(
        "placeholder template removed",
        not PLACEHOLDER_PATH.exists(),
    )

    # 1. Template content ---------------------------------------------
    tpl = TEMPLATE_PATH.read_text()
    tpl_checks = [
        ("state hydrated from embedded JSON",      '<script id="initialState"' in tpl and 'state_json | safe' in tpl),
        ("has upload / processing / tracker views", 'id="uploadView"' in tpl and 'id="processingView"' in tpl and 'id="trackerView"' in tpl),
        ("has score modal",                         'id="scoreModal"' in tpl and 'id="modalMarkNotDoneBtn"' in tpl),
        ("calls /api/upload-pool-order-photo",      '/api/upload-pool-order-photo' in tpl),
        ("calls save-extraction",                   '/save-extraction' in tpl),
        ("calls update",                            "/update'" in tpl or '/update"' in tpl or '/update,' in tpl or 'update,' in tpl),
        ("defines openScoreModal",                  'function openScoreModal' in tpl),
        ("defines saveFromModal",                   'function saveFromModal' in tpl),
        ("defines markNotDoneFromModal",            'function markNotDoneFromModal' in tpl),
        ("defines toggleBoutDone",                  'function toggleBoutDone' in tpl),
        ("defines queueAutosave",                   'function queueAutosave' in tpl),
        ("localStorage cache key uses pool_round_id","pool_tracker_' + POOL_ROUND_ID" in tpl),
        ("iOS-friendly inputs (-webkit-appearance:none + inputmode=numeric)",
            '-webkit-appearance: none' in tpl and 'inputmode="numeric"' in tpl),
    ]
    for name, ok in tpl_checks:
        record(f"template: {name}", ok)

    # 2. Page renders upload view when roster empty -------------------
    c = authed_client()
    pr_id = make_pool_round()
    r = c.get(f"/pool-tracker/{pr_id}")
    html = r.get_data(as_text=True)
    record(
        "render: empty-roster PoolRound serves state w/ empty roster + bouts",
        r.status_code == 200
        and '"roster": []' in html
        and '"bouts": []' in html
        and f'"pool_round_id": {pr_id}' in html,
        f"status={r.status_code}",
    )

    # 3. Page renders tracker view when roster populated --------------
    pr_id_full = make_pool_round(
        pool_number=5,
        strip_number="6",
        ethan_pool_num=3,
        roster_json=json.dumps(ROSTER),
        bout_order_json=json.dumps(BOUTS),
    )
    r = c.get(f"/pool-tracker/{pr_id_full}")
    html = r.get_data(as_text=True)
    record(
        "render: populated PoolRound embeds full state in JSON blob",
        r.status_code == 200
        and '"pool_number": 5' in html
        and '"ethan_pool_num": 3' in html
        and "BOROVIKOV" in html
        and "SALIM" in html,
        f"status={r.status_code}",
    )

    # 4. Auth on save endpoints ---------------------------------------
    unauthed = app.test_client()
    for path in [
        f"/api/pool-tracker/{pr_id}/save-extraction",
        f"/api/pool-tracker/{pr_id}/update",
    ]:
        r = unauthed.post(path, json={})
        record(
            f"auth: {path} 302s unauth",
            r.status_code == 302 and "/login" in (r.headers.get("Location") or ""),
            f"status={r.status_code}",
        )

    # 5. save-extraction happy path (single strip, numeric input) ----
    r = c.post(
        f"/api/pool-tracker/{pr_id}/save-extraction",
        json={
            "pool_number": 5,
            "strip_number": 6,          # client might send int; server coerces to str
            "ethan_pool_num": 3,
            "roster": ROSTER,
            "bouts": BOUTS,
        },
    )
    body = r.get_json() or {}
    got = read_pool_round(pr_id)
    record(
        "save-extraction: persists roster+bouts+scalars (int strip coerced to str)",
        r.status_code == 200
        and body.get("success") is True
        and got["pool_number"] == 5
        and got["strip_number"] == "6"
        and got["ethan_pool_num"] == 3
        and got["roster"] == ROSTER
        and len(got["bouts"]) == 3
        and got["bouts"][2]["right_score"] == 2,
        f"status={r.status_code} strip={got['strip_number']!r}",
    )

    # 5b. save-extraction accepts dual-strip "9-10" without crashing ----
    dual_id = make_pool_round()
    r = c.post(
        f"/api/pool-tracker/{dual_id}/save-extraction",
        json={
            "pool_number": 7,
            "strip_number": "9-10",   # dual-strip pool; previously crashed Postgres
            "ethan_pool_num": None,
            "roster": [], "bouts": [],
        },
    )
    got = read_pool_round(dual_id)
    record(
        "save-extraction: accepts dual-strip '9-10' as strip_number",
        r.status_code == 200 and got["strip_number"] == "9-10",
        f"status={r.status_code} strip={got['strip_number']!r}",
    )

    # 6. save-extraction: unknown id → 404 ----------------------------
    r = c.post(
        "/api/pool-tracker/999999/save-extraction",
        json={"roster": [], "bouts": []},
    )
    record(
        "save-extraction: unknown pool_round_id → 404",
        r.status_code == 404,
        f"status={r.status_code}",
    )

    # 7. save-extraction: bad bout shape → 400 ------------------------
    r = c.post(
        f"/api/pool-tracker/{pr_id}/save-extraction",
        json={"roster": [], "bouts": [{"nope": True}]},
    )
    record(
        "save-extraction: malformed bout → 400",
        r.status_code == 400,
        f"status={r.status_code} body={r.get_json()}",
    )

    # 8. save-extraction: out-of-range score → 400 --------------------
    r = c.post(
        f"/api/pool-tracker/{pr_id}/save-extraction",
        json={
            "roster": [],
            "bouts": [{"order": 1, "right_num": 1, "left_num": 2, "right_score": 7, "left_score": 0}],
        },
    )
    record(
        "save-extraction: score outside 0..5 → 400",
        r.status_code == 400 and "0-5" in ((r.get_json() or {}).get("error") or ""),
        f"status={r.status_code} body={r.get_json()}",
    )

    # 9. /update replaces bouts in place; doesn't touch roster --------
    updated_bouts = [
        {"order": 1, "right_num": 1, "left_num": 2, "done": True, "right_score": 5, "left_score": 3},
        {"order": 2, "right_num": 4, "left_num": 5, "done": True, "right_score": 5, "left_score": 4},
        {"order": 3, "right_num": 2, "left_num": 3, "done": True, "right_score": 2, "left_score": 5},
    ]
    r = c.post(
        f"/api/pool-tracker/{pr_id}/update",
        json={"bouts": updated_bouts},
    )
    got = read_pool_round(pr_id)
    record(
        "update: replaces bouts; roster + scalars untouched",
        r.status_code == 200
        and len(got["bouts"]) == 3
        and got["bouts"][0]["done"] is True
        and got["bouts"][0]["right_score"] == 5
        and got["roster"] == ROSTER
        and got["pool_number"] == 5,
        f"status={r.status_code} b0_score={got['bouts'][0].get('right_score')}",
    )

    # 10. /update: unknown id → 404 ----------------------------------
    r = c.post(
        "/api/pool-tracker/999999/update",
        json={"bouts": []},
    )
    record(
        "update: unknown pool_round_id → 404",
        r.status_code == 404,
        f"status={r.status_code}",
    )

    # 11. /update: non-list bouts → 400 ------------------------------
    r = c.post(
        f"/api/pool-tracker/{pr_id}/update",
        json={"bouts": "not a list"},
    )
    record(
        "update: non-list bouts → 400",
        r.status_code == 400,
        f"status={r.status_code}",
    )

    # 12. /update tolerates null scores (user cleared both inputs) ----
    cleared = [
        {"order": 1, "right_num": 1, "left_num": 2, "done": True, "right_score": None, "left_score": None},
    ]
    r = c.post(
        f"/api/pool-tracker/{pr_id}/update",
        json={"bouts": cleared},
    )
    got = read_pool_round(pr_id)
    record(
        "update: tolerates null scores on a done bout (just marked done, no score)",
        r.status_code == 200
        and len(got["bouts"]) == 1
        and got["bouts"][0]["done"] is True
        and got["bouts"][0]["right_score"] is None
        and got["bouts"][0]["left_score"] is None,
        f"status={r.status_code}",
    )

    # 13. End-to-end: fresh PoolRound → save-extraction → GET page sees
    # populated state in the hydration blob.
    fresh_id = make_pool_round()
    c.post(
        f"/api/pool-tracker/{fresh_id}/save-extraction",
        json={
            "pool_number": 2, "strip_number": None, "ethan_pool_num": 3,
            "roster": ROSTER, "bouts": BOUTS,
        },
    )
    r = c.get(f"/pool-tracker/{fresh_id}")
    html = r.get_data(as_text=True)
    record(
        "end-to-end: save then reload returns tracker-ready state",
        r.status_code == 200
        and '"pool_number": 2' in html
        and '"ethan_pool_num": 3' in html
        and "SALIM" in html,
        f"status={r.status_code}",
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
