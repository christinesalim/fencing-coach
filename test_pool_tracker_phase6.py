#!/usr/bin/env python3
"""Pool Tracker Phase 6 — entry points.

Verifies:
  - /api/pool-tracker/quick-start without a body creates draft tournament
    named "Pool — <YYYY-MM-DD>" + a PoolRound and returns a redirect URL
  - /api/pool-tracker/quick-start WITH tournament_id attaches to that
    existing tournament (no new draft created)
  - /api/pool-tracker/quick-start rejects an unknown tournament_id with 404
  - /pool-tracker/<id> renders the placeholder with the tournament name
  - /pool-tracker/<id> 404s on unknown id
  - All routes enforce auth
  - index.html surfaces the Quick Start Pool nav card
  - tournament_detail.html surfaces the Start Pool Tracker button

Exits 0 only if every scenario PASSes.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from app import app
from database import PoolRound, Tournament, get_db


PREFIX = "PT6_TEST_"
INDEX_TPL = Path(__file__).parent / "templates" / "index.html"
TOURN_TPL = Path(__file__).parent / "templates" / "tournament_detail.html"
PLACEHOLDER_TPL = Path(__file__).parent / "templates" / "pool_tracker_placeholder.html"

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
    db = get_db()
    try:
        today_draft = f"Pool — {datetime.utcnow().strftime('%Y-%m-%d')}"
        tids = [t.id for t in db.query(Tournament).filter(
            (Tournament.name.like(f"{PREFIX}%"))
            | (Tournament.name == today_draft)
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
    print("Pool Tracker Phase 6 — entry points")
    print("=" * 50)

    # 1. Template surfaces --------------------------------------------
    index_src = INDEX_TPL.read_text()
    record(
        "template: index.html has Quick Start Pool nav card",
        "Quick Start Pool" in index_src and "quickStartPool" in index_src,
    )
    record(
        "template: index.html calls /api/pool-tracker/quick-start",
        "/api/pool-tracker/quick-start" in index_src,
    )

    tourn_src = TOURN_TPL.read_text()
    record(
        "template: tournament_detail.html has Start Pool Tracker button",
        "Start Pool Tracker" in tourn_src and "startPoolTracker" in tourn_src,
    )
    record(
        "template: tournament_detail.html passes tournament_id in POST body",
        "tournament_id: {{ tournament.id }}" in tourn_src,
    )

    record(
        "template: placeholder page exists",
        PLACEHOLDER_TPL.exists(),
    )

    # 2. Auth ---------------------------------------------------------
    unauthed = app.test_client()
    r1 = unauthed.post("/api/pool-tracker/quick-start")
    r2 = unauthed.get("/pool-tracker/1")
    record(
        "auth: both routes 302 to /login when unauthed",
        r1.status_code == 302 and r2.status_code == 302
        and "/login" in (r1.headers.get("Location") or "")
        and "/login" in (r2.headers.get("Location") or ""),
        f"quick-start={r1.status_code} tracker={r2.status_code}",
    )

    c = authed_client()

    # 3. Quick start WITHOUT body → creates draft tournament ---------
    r = c.post("/api/pool-tracker/quick-start")
    body = r.get_json() or {}
    pool_round_id = body.get("pool_round_id")
    tournament_id = body.get("tournament_id")
    redirect = body.get("redirect") or ""
    db = get_db()
    try:
        t = db.query(Tournament).filter_by(id=tournament_id).first() if tournament_id else None
    finally:
        db.close()
    today_prefix = f"Pool — {datetime.utcnow().strftime('%Y-%m-%d')}"
    record(
        "quick-start (no body): creates draft tournament + PoolRound",
        r.status_code == 200
        and body.get("success") is True
        and isinstance(pool_round_id, int)
        and isinstance(tournament_id, int)
        and redirect == f"/pool-tracker/{pool_round_id}"
        and t is not None
        and t.name == today_prefix,
        f"status={r.status_code} redirect={redirect} tname={t and t.name}",
    )
    draft_tid = tournament_id
    draft_prid = pool_round_id

    # 4. Quick start WITH tournament_id → attaches to that tournament
    db = get_db()
    try:
        existing = Tournament(
            name=f"{PREFIX}EXISTING", date=datetime(2026, 1, 1)
        )
        db.add(existing); db.commit()
        existing_id = existing.id
    finally:
        db.close()

    r = c.post(
        "/api/pool-tracker/quick-start",
        json={"tournament_id": existing_id},
    )
    body = r.get_json() or {}
    db = get_db()
    try:
        attached_count = db.query(PoolRound).filter_by(
            tournament_id=existing_id
        ).count()
        # Make sure no NEW draft tournament was created for this run
        extra_drafts = db.query(Tournament).filter(
            Tournament.name == today_prefix, Tournament.id != draft_tid
        ).count()
    finally:
        db.close()
    record(
        "quick-start (with tournament_id): attaches to existing, no new draft",
        r.status_code == 200
        and body.get("tournament_id") == existing_id
        and attached_count == 1
        and extra_drafts == 0,
        f"status={r.status_code} returned_tid={body.get('tournament_id')} "
        f"attached={attached_count} extra_drafts={extra_drafts}",
    )

    # 5. Quick start with UNKNOWN tournament_id → 404 ----------------
    r = c.post(
        "/api/pool-tracker/quick-start",
        json={"tournament_id": 999999},
    )
    body = r.get_json() or {}
    record(
        "quick-start: unknown tournament_id → 404",
        r.status_code == 404 and "not found" in (body.get("error") or "").lower(),
        f"status={r.status_code} body={body}",
    )

    # 6. Placeholder page renders ------------------------------------
    r = c.get(f"/pool-tracker/{draft_prid}")
    html = r.get_data(as_text=True)
    record(
        "placeholder: renders with tournament name + pool_round_id visible",
        r.status_code == 200
        and today_prefix in html
        and str(draft_prid) in html,
        f"status={r.status_code}",
    )

    # 7. Placeholder page 404s on unknown id -------------------------
    r = c.get("/pool-tracker/999999")
    record(
        "placeholder: unknown pool_round_id → 404",
        r.status_code == 404,
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
