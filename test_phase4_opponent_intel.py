#!/usr/bin/env python3
"""Phase 4 smoke test: Pre-bout opponent intel view.

Exercises the new `/opponents/<id>/intel` page route, the
`/api/opponents/<id>/intel` JSON endpoint, the tournament detail badge
href update, and the "View Pre-Bout Intel" button on the profile page.

Prints PASS/FAIL per scenario and exits 0 only if everything passes.
Test records use prefix ``TEST_P4_`` so cleanup is trivial.
"""

import sys
from datetime import datetime

from app import app
from database import (
    Tournament,
    PoolBout,
    PoolRound,
    add_bout_record,
    add_tactical_note,
    create_opponent,
    create_tournament,
    delete_opponent,
    delete_tournament,
    get_all_opponents,
    get_db,
    update_opponent,
)


PREFIX = "TEST_P4_"
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
    """Remove any TEST_P4_* data from previous runs."""
    for opp in get_all_opponents():
        canonical = (opp.get("canonical_name") or "")
        last_name = (opp.get("last_name") or "")
        first_name = (opp.get("first_name") or "")
        if (canonical.startswith(PREFIX)
                or last_name.startswith(PREFIX)
                or first_name.startswith(PREFIX)):
            try:
                delete_opponent(opp["id"])
            except Exception:
                pass

    # Tournaments + pool bouts/rounds with the prefix.
    db = get_db()
    try:
        t_ids = [
            t.id for t in db.query(Tournament)
            .filter(Tournament.name.like(f"{PREFIX}%"))
            .all()
        ]
    finally:
        db.close()
    for tid in t_ids:
        try:
            delete_tournament(tid)
        except Exception:
            pass


def count_leftover():
    """Return the count of TEST_P4_* records still present."""
    leftover = 0
    for opp in get_all_opponents():
        canonical = (opp.get("canonical_name") or "")
        last_name = (opp.get("last_name") or "")
        first_name = (opp.get("first_name") or "")
        if (canonical.startswith(PREFIX)
                or last_name.startswith(PREFIX)
                or first_name.startswith(PREFIX)):
            leftover += 1
    db = get_db()
    try:
        leftover += db.query(Tournament).filter(
            Tournament.name.like(f"{PREFIX}%")
        ).count()
    finally:
        db.close()
    return leftover


def main():
    print("=== Phase 4 Opponent Intel smoke test ===\n")
    cleanup()
    c = authed_client()

    # --- 404s for unknown opponent id ---
    print("404s for missing opponent:")
    resp = c.get("/opponents/9999999/intel")
    record("GET /opponents/9999999/intel returns 404",
           resp.status_code == 404, f"status={resp.status_code}")

    resp = c.get("/api/opponents/9999999/intel")
    record("GET /api/opponents/9999999/intel returns 404",
           resp.status_code == 404, f"status={resp.status_code}")

    # --- Create an opponent with no data ---
    print("\nEmpty opponent:")
    opp = create_opponent({
        "first_name": "Sam",
        "last_name": PREFIX + "BLANK",
        "club": "Test Club",
    })
    opp_id = opp["id"]

    resp = c.get(f"/opponents/{opp_id}/intel")
    record("GET /opponents/<id>/intel returns 200 when opponent has no notes",
           resp.status_code == 200, f"status={resp.status_code}")
    body = resp.get_data(as_text=True)
    record("Empty intel page contains opponent canonical_name",
           opp["canonical_name"] in body)
    record("Empty intel page shows 'No intel yet' message",
           "No intel yet" in body)

    # --- Now flesh out the opponent with notes + bouts + traits ---
    print("\nAdd notes across categories:")
    # what_worked: confidence 0.9 (validated=9, invalidated=1)
    add_tactical_note(opp_id, {
        "category": "what_worked",
        "observation": "Attack in preparation during their step forward",
        "times_validated": 9,
        "times_invalidated": 1,
    })
    # favorite_action: confidence 0.5 (validated=1, invalidated=1)
    add_tactical_note(opp_id, {
        "category": "favorite_action",
        "observation": "Loves a quick second-intention parry-riposte",
        "times_validated": 1,
        "times_invalidated": 1,
    })
    # tell: confidence None (no signals yet)
    add_tactical_note(opp_id, {
        "category": "tell",
        "observation": "Drops rear shoulder right before attacking",
        "times_validated": 0,
        "times_invalidated": 0,
    })
    # weakness: confidence 0.8 (validated=4, invalidated=1)
    add_tactical_note(opp_id, {
        "category": "weakness",
        "observation": "Slow retreat — press the distance",
        "times_validated": 4,
        "times_invalidated": 1,
    })
    # general: should NOT appear in any intel section
    add_tactical_note(opp_id, {
        "category": "general",
        "observation": "GENERAL note should be excluded from intel",
        "times_validated": 3,
        "times_invalidated": 0,
    })

    # Two bouts — newest first = lost 3-5 at 2026-04-15
    print("Add bout history:")
    add_bout_record(opp_id, {
        "tournament_name": "TEST_P4_Older NAC",
        "tournament_date": "2026-02-15",
        "bout_type": "pool",
        "score_for": 5, "score_against": 3,
        "result": "won",
    })
    add_bout_record(opp_id, {
        "tournament_name": "TEST_P4_Newer NAC",
        "tournament_date": "2026-04-15",
        "bout_type": "elimination",
        "score_for": 3, "score_against": 5,
        "result": "lost",
    })

    print("Update opponent traits:")
    update_opponent(opp_id, {
        "handedness": "left",
        "height_category": "tall",
        "primary_style": "aggressive",
        "speed_rating": "fast",
    })

    # --- JSON intel API ---
    print("\nJSON intel payload:")
    resp = c.get(f"/api/opponents/{opp_id}/intel")
    record("GET /api/opponents/<id>/intel returns 200",
           resp.status_code == 200, f"status={resp.status_code}")
    payload = resp.get_json() or {}

    record("Payload has opponent, head_to_head, notes_by_section",
           all(k in payload for k in ("opponent", "head_to_head", "notes_by_section")))

    notes_by = payload.get("notes_by_section") or {}
    what_works = notes_by.get("what_works") or []
    watch_out_for = notes_by.get("watch_out_for") or []
    weaknesses = notes_by.get("weaknesses") or []

    record("notes_by_section.what_works has length 1",
           len(what_works) == 1, f"got {len(what_works)}")
    record("what_works entry is the Attack-in-preparation note",
           len(what_works) == 1 and "Attack in preparation" in (what_works[0].get("observation") or ""))

    record("notes_by_section.watch_out_for has length 2",
           len(watch_out_for) == 2, f"got {len(watch_out_for)}")
    if len(watch_out_for) >= 2:
        first_conf = watch_out_for[0].get("confidence")
        last_conf = watch_out_for[-1].get("confidence")
        record("watch_out_for: highest-confidence note is first",
               first_conf is not None and (last_conf is None or first_conf >= last_conf),
               f"first={first_conf} last={last_conf}")
        record("watch_out_for: None-confidence note is last",
               last_conf is None, f"last conf={last_conf}")

    record("notes_by_section.weaknesses has length 1",
           len(weaknesses) == 1, f"got {len(weaknesses)}")

    # Ensure general note didn't leak into any section.
    all_intel_obs = (
        [n.get("observation") for n in what_works]
        + [n.get("observation") for n in watch_out_for]
        + [n.get("observation") for n in weaknesses]
    )
    record("general-category note excluded from all intel sections",
           not any("GENERAL note" in (o or "") for o in all_intel_obs))

    # Physical summary
    phys = payload.get("physical_summary")
    record("physical_summary is a non-empty string",
           isinstance(phys, str) and len(phys) > 0, f"summary={phys!r}")
    record("physical_summary mentions 'left' (handedness)",
           isinstance(phys, str) and "left" in phys.lower())
    record("physical_summary mentions 'tall' (height)",
           isinstance(phys, str) and "tall" in phys.lower())
    record("physical_summary mentions 'aggressive' (style)",
           isinstance(phys, str) and "aggressive" in phys.lower())
    record("physical_summary mentions 'fast' (speed)",
           isinstance(phys, str) and "fast" in phys.lower())

    # Last encounter
    le = payload.get("last_encounter") or {}
    record("last_encounter.tournament_date is the newer 2026-04-15",
           le.get("tournament_date") == "2026-04-15",
           f"date={le.get('tournament_date')}")
    record("last_encounter.result is 'lost'",
           (le.get("result") or "").lower() == "lost",
           f"result={le.get('result')}")

    # Head to head
    h2h = payload.get("head_to_head") or {}
    record("head_to_head wins == 1",
           h2h.get("wins") == 1, f"wins={h2h.get('wins')}")
    record("head_to_head losses == 1",
           h2h.get("losses") == 1, f"losses={h2h.get('losses')}")

    # --- HTML intel page ---
    print("\nHTML intel page:")
    resp = c.get(f"/opponents/{opp_id}/intel")
    record("GET /opponents/<id>/intel returns 200",
           resp.status_code == 200, f"status={resp.status_code}")
    body = resp.get_data(as_text=True)

    record("HTML contains opponent canonical_name",
           opp["canonical_name"] in body)
    record("HTML contains 'WHAT WORKS' heading",
           "WHAT WORKS" in body)
    record("HTML contains 'WATCH OUT FOR' heading",
           "WATCH OUT FOR" in body)
    record("HTML contains 'WEAKNESSES TO EXPLOIT' heading",
           "WEAKNESSES TO EXPLOIT" in body)
    record("HTML H2H summary shows '1-1'", "1-1" in body)
    record("HTML contains the physical summary text",
           phys in body if isinstance(phys, str) else False)
    record("HTML contains 'Edit notes' link pointing to profile",
           f'href="/opponents/{opp_id}"' in body and "Edit notes" in body)
    record("HTML contains a back link (← back)", "back to profile" in body)

    # --- Tournament detail badge href check ---
    print("\nTournament detail badge href:")
    # Create a tournament + pool round + pool bout + bout record so the
    # tournament detail page renders a 'View Intel' badge linked to the opponent.
    t = create_tournament({
        "name": PREFIX + "Tournament",
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
    })
    t_id = t["id"]
    db = get_db()
    pool_bout_id = None
    try:
        round_row = PoolRound(
            tournament_id=t_id, pool_number=1, position_in_pool=1,
            victories=1, defeats=0, touches_scored=5, touches_received=3,
            indicator=2,
        )
        db.add(round_row)
        db.flush()
        pb = PoolBout(
            pool_round_id=round_row.id,
            opponent_name=opp["canonical_name"],
            opponent_club="Test Club",
            score_for=5, score_against=3, result="won",
            bout_order=1,
        )
        db.add(pb)
        db.commit()
        pool_bout_id = pb.id
    except Exception as e:
        db.rollback()
        record("Setup tournament/pool bout", False, str(e))
    finally:
        db.close()

    # Link the pool bout to the opponent via a BoutRecord so the detail page
    # populates `opponent_id` on the bout and renders the 'View Intel' badge.
    if pool_bout_id:
        add_bout_record(opp_id, {
            "tournament_id": t_id,
            "tournament_name": t["name"],
            "bout_type": "pool",
            "pool_bout_id": pool_bout_id,
            "score_for": 5, "score_against": 3, "result": "won",
        })

    resp = c.get(f"/tournaments/{t_id}")
    if resp.status_code == 200:
        body = resp.get_data(as_text=True)
        expected_href = f'/opponents/{opp_id}/intel'
        record("tournament detail badge href ends in /intel",
               expected_href in body,
               f"expected substring {expected_href!r}")
    else:
        record("GET /tournaments/<id> returns 200", False,
               f"status={resp.status_code}")

    # --- Profile page should expose a link to intel ---
    print("\nProfile page link:")
    resp = c.get(f"/opponents/{opp_id}")
    record("GET /opponents/<id> returns 200",
           resp.status_code == 200, f"status={resp.status_code}")
    body = resp.get_data(as_text=True)
    record("Profile page links to /opponents/<id>/intel",
           f'/opponents/{opp_id}/intel' in body)

    # --- Cleanup ---
    print("\nCleanup:")
    cleanup()
    leftover = count_leftover()
    record("No TEST_P4_* records remain after cleanup",
           leftover == 0, f"leftover={leftover}")

    # --- Tally ---
    failed = [r for r in results if not r[1]]
    print(f"\n=== Phase 4 smoke test: {len(results) - len(failed)}/{len(results)} passed ===")
    if failed:
        print("FAILURES:")
        for name, _, detail in failed:
            print(f"  - {name} ({detail})")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
