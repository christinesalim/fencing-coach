#!/usr/bin/env python3
"""Phase 3 smoke test: Opponent auto-sync + backfill + detail page badges.

Exercises the new `sync_bout_to_opponent` wiring, the `/api/opponents/lookup`
endpoint, the photo-extraction `opponent_intel` sidecar, and the
`backfill_bout_records.py` script. Prints PASS/FAIL per scenario and exits 0
only if everything passes.

All created records use prefix ``TEST_P3_`` so cleanup is trivial.
"""

import subprocess
import sys
from datetime import datetime

from app import app
from database import (
    BoutRecord,
    Opponent,
    PoolBout,
    PoolRound,
    EliminationRound,
    Tournament,
    create_opponent,
    create_tournament,
    delete_opponent,
    delete_tournament,
    get_all_opponents,
    get_db,
    save_de_results_to_db,
    save_pool_results_to_db,
)


PREFIX = "TEST_P3_"
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
    """Remove any TEST_P3_* data from previous runs."""
    # Opponents (cascades to BoutRecords + notes).
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

    # Tournaments (cascades to pool/DE tables + linked BoutRecords via
    # database.delete_tournament).
    db = get_db()
    try:
        tourneys = db.query(Tournament).filter(Tournament.name.like(f"{PREFIX}%")).all()
        ids = [t.id for t in tourneys]
    finally:
        db.close()
    for tid in ids:
        try:
            delete_tournament(tid)
        except Exception:
            pass


def count_bout_records_for_opponent(opponent_id):
    db = get_db()
    try:
        return db.query(BoutRecord).filter_by(opponent_id=opponent_id).count()
    finally:
        db.close()


def count_all_bout_records():
    db = get_db()
    try:
        return db.query(BoutRecord).count()
    finally:
        db.close()


def main():
    print("=== Phase 3 Opponent Sync smoke test ===\n")
    cleanup()

    c = authed_client()

    # ------------------------------------------------------------------
    # Scenario 1: save_pool_results_to_db auto-sync
    # ------------------------------------------------------------------
    print("Scenario 1: Pool save auto-sync")

    existing_opp = create_opponent({
        "canonical_name": f"{PREFIX}KNOWN_JI Dylan",
        "first_name": "Dylan",
        "last_name": f"{PREFIX}KNOWN",
        "club": "AFM",
    })
    existing_opp_id = existing_opp["id"]

    tournament = create_tournament({
        "name": f"{PREFIX}NorCal SYC",
        "date": "2026-03-15",
        "location": "San Jose",
        "weapon": "epee",
        "age_category": "Y12",
        "level": "SYC",
    })
    tournament_id = tournament["id"]

    pool_data = {
        "pool_number": 1,
        "position_in_pool": 3,
        "victories": 2,
        "defeats": 1,
        "touches_scored": 12,
        "touches_received": 10,
        "indicator": 2,
        "bouts": [
            # 1: matches existing opponent (Tier 1 exact)
            {
                "opponent_name": f"{PREFIX}KNOWN_JI Dylan",
                "opponent_club": "AFM",
                "score_for": 5, "score_against": 3,
                "result": "won", "bout_order": 1,
            },
            # 2: brand-new — should create a stub opponent
            {
                "opponent_name": f"{PREFIX}STUB_LU Brian",
                "opponent_club": "MTeam",
                "score_for": 4, "score_against": 5,
                "result": "lost", "bout_order": 2,
            },
            # 3: empty opponent name — must skip cleanly
            {
                "opponent_name": "",
                "opponent_club": "",
                "score_for": 3, "score_against": 5,
                "result": "lost", "bout_order": 3,
            },
        ],
    }

    pool_before = count_bout_records_for_opponent(existing_opp_id)
    save_result = save_pool_results_to_db(tournament_id, pool_data)
    intel = save_result.get("opponent_intel") or []

    record("Pool save returns opponent_intel aligned to bouts",
           len(intel) == 3, f"got {len(intel)} entries")
    record("Bout 1 auto-links to existing opponent",
           intel[0].get("action") == "auto_link"
           and intel[0].get("opponent_id") == existing_opp_id,
           f"action={intel[0].get('action')} opp_id={intel[0].get('opponent_id')}")
    record("Bout 1 'known' flag is True", intel[0].get("known") is True)
    record("Bout 2 creates stub opponent",
           intel[1].get("action") == "stub_created"
           and intel[1].get("opponent_id") is not None,
           f"action={intel[1].get('action')} opp_id={intel[1].get('opponent_id')}")
    record("Bout 3 (empty name) is skipped without crashing",
           intel[2].get("action") == "skipped"
           and intel[2].get("opponent_id") is None)

    pool_after = count_bout_records_for_opponent(existing_opp_id)
    record("Existing opponent now has +1 BoutRecord",
           pool_after == pool_before + 1,
           f"before={pool_before} after={pool_after}")

    stub_opp_id = intel[1].get("opponent_id")
    record("Stub opponent has 1 BoutRecord",
           count_bout_records_for_opponent(stub_opp_id) == 1 if stub_opp_id else False)

    # ------------------------------------------------------------------
    # Scenario 2: save_de_results_to_db auto-sync
    # ------------------------------------------------------------------
    print("\nScenario 2: DE save auto-sync")

    bracket_data = {
        "tournament_bracket": {
            "bracket_size": 32,
            "completeness": "our_path_only",
        },
        "our_fencer": {
            "name": "SALIM Ethan",
            "seed": 7,
            "final_placement_range": "9-12",
            "path": [
                # 1: matches existing opponent
                {
                    "round_name": "T32",
                    "opponent_name": f"{PREFIX}KNOWN_JI Dylan",
                    "opponent_club": "AFM",
                    "opponent_seed": 26,
                    "score_for": 15, "score_against": 10,
                    "result": "won",
                },
                # 2: brand-new — stub created
                {
                    "round_name": "T16",
                    "opponent_name": f"{PREFIX}STUB_DE_BRAND New",
                    "opponent_club": "Test Club",
                    "opponent_seed": 3,
                    "score_for": 11, "score_against": 15,
                    "result": "lost",
                },
                # 3: BYE — should be filtered out entirely (not in intel)
                {
                    "round_name": "T8",
                    "opponent_name": "BYE",
                    "opponent_club": None,
                    "opponent_seed": None,
                    "score_for": None, "score_against": None,
                    "result": None,
                },
                # 4: empty name — skipped
                {
                    "round_name": "T4",
                    "opponent_name": "",
                    "opponent_club": "",
                    "opponent_seed": None,
                    "score_for": 5, "score_against": 15,
                    "result": "lost",
                },
            ],
        },
    }

    de_before = count_bout_records_for_opponent(existing_opp_id)
    de_result = save_de_results_to_db(tournament_id, bracket_data)
    de_intel = (de_result or {}).get("opponent_intel") or []

    # BYE was filtered out, so we expect 3 entries (not 4).
    record("DE save returns opponent_intel aligned to non-BYE bouts",
           len(de_intel) == 3,
           f"got {len(de_intel)} entries")
    record("DE bout 1 auto-links to existing opponent",
           de_intel[0].get("action") == "auto_link"
           and de_intel[0].get("opponent_id") == existing_opp_id)
    record("DE bout 2 creates stub opponent",
           de_intel[1].get("action") == "stub_created"
           and de_intel[1].get("opponent_id") is not None)
    record("DE bout 3 (empty name) is skipped",
           de_intel[2].get("action") == "skipped")

    de_after = count_bout_records_for_opponent(existing_opp_id)
    record("Existing opponent now has +1 DE BoutRecord",
           de_after == de_before + 1,
           f"before={de_before} after={de_after}")

    # ------------------------------------------------------------------
    # Scenario 3: /api/confirm-pool-results returns opponent_intel
    # ------------------------------------------------------------------
    print("\nScenario 3: confirm endpoints include opponent_intel")

    # We exercise the confirm-pool-results endpoint directly (the photo
    # extraction step is mocked out of scope). A new tournament + simpler
    # bout payload keeps this isolated from Scenario 1's saved data.
    tournament2 = create_tournament({
        "name": f"{PREFIX}Confirm Endpoint Test",
        "date": "2026-04-01",
        "location": "Test Loc",
    })
    tid2 = tournament2["id"]

    confirm_pool_payload = {
        "tournament_id": tid2,
        "pool_data": {
            "pool_number": 2,
            "position_in_pool": 2,
            "victories": 2,
            "defeats": 0,
            "touches_scored": 10,
            "touches_received": 4,
            "indicator": 6,
            "bouts": [
                {
                    "opponent_name": f"{PREFIX}KNOWN_JI Dylan",
                    "opponent_club": "AFM",
                    "score_for": 5, "score_against": 2,
                    "result": "won", "bout_order": 1,
                },
                {
                    "opponent_name": f"{PREFIX}CONFIRM_Fresh Face",
                    "opponent_club": "Some Club",
                    "score_for": 5, "score_against": 4,
                    "result": "won", "bout_order": 2,
                },
            ],
        },
    }

    resp = c.post("/api/confirm-pool-results", json=confirm_pool_payload)
    record("POST /api/confirm-pool-results returns 200", resp.status_code == 200)
    body = resp.get_json() or {}
    intel_from_confirm = body.get("opponent_intel") or []
    record("confirm-pool-results response includes opponent_intel",
           len(intel_from_confirm) == 2)
    record("First intel entry is auto_link to known opponent",
           intel_from_confirm[0].get("action") == "auto_link"
           and intel_from_confirm[0].get("opponent_id") == existing_opp_id)
    record("Second intel entry creates a stub",
           intel_from_confirm[1].get("action") == "stub_created"
           and intel_from_confirm[1].get("opponent_id") is not None)

    # Same shape for DE confirm.
    confirm_de_payload = {
        "tournament_id": tid2,
        "bracket_data": {
            "tournament_bracket": {"bracket_size": 16, "completeness": "our_path_only"},
            "our_fencer": {
                "name": "SALIM Ethan",
                "seed": 5,
                "path": [
                    {
                        "round_name": "T16",
                        "opponent_name": f"{PREFIX}CONFIRM_DE_Opp",
                        "opponent_club": "DE Club",
                        "opponent_seed": 12,
                        "score_for": 15, "score_against": 7,
                        "result": "won",
                    }
                ],
            },
        },
    }
    resp = c.post("/api/confirm-de-results", json=confirm_de_payload)
    record("POST /api/confirm-de-results returns 200", resp.status_code == 200)
    body = resp.get_json() or {}
    de_intel_from_confirm = body.get("opponent_intel") or []
    record("confirm-de-results response includes opponent_intel",
           len(de_intel_from_confirm) == 1)

    # ------------------------------------------------------------------
    # Scenario 4: /api/opponents/lookup
    # ------------------------------------------------------------------
    print("\nScenario 4: /api/opponents/lookup")

    resp = c.post("/api/opponents/lookup", json={
        "names": [
            # Provide the club to hit Tier 1 exact
            {"name": f"{PREFIX}KNOWN_JI Dylan", "club": "AFM"},
            # Plain string with no matching canonical name — expect no match
            f"{PREFIX}UNKNOWN_Person_Doe",
        ],
    })
    record("POST /api/opponents/lookup returns 200", resp.status_code == 200)
    body = resp.get_json() or {}
    matches = body.get("matches") or []
    record("lookup returns 2 entries in order", len(matches) == 2)
    if len(matches) == 2:
        first = matches[0].get("match") or {}
        record("first lookup result has a tier 1/2 opponent match",
               first.get("opponent") is not None
               and first.get("tier") in (1, 2),
               f"tier={first.get('tier')}")
        second = matches[1].get("match") or {}
        record("second lookup result is a no-match",
               second.get("opponent") is None
               and second.get("tier") is None)

    resp = c.post("/api/opponents/lookup", json={"names": "not-a-list"})
    record("lookup with invalid names returns 400", resp.status_code == 400)

    # ------------------------------------------------------------------
    # Scenario 5: Backfill script — idempotency
    # ------------------------------------------------------------------
    print("\nScenario 5: Backfill script")

    before_count = count_all_bout_records()
    proc = subprocess.run(
        [sys.executable, "backfill_bout_records.py"],
        capture_output=True, text=True,
    )
    record("backfill_bout_records.py exits 0",
           proc.returncode == 0,
           f"rc={proc.returncode} stderr={(proc.stderr or '')[:200]}")
    after_count = count_all_bout_records()
    # All current bouts should already be synced (sync happens on save),
    # so backfill should produce zero new rows on the first run.
    record("Backfill creates 0 new BoutRecords (bouts already synced)",
           after_count == before_count,
           f"before={before_count} after={after_count}")

    # Re-run: still 0 new rows.
    proc2 = subprocess.run(
        [sys.executable, "backfill_bout_records.py"],
        capture_output=True, text=True,
    )
    record("backfill re-run also exits 0",
           proc2.returncode == 0,
           f"rc={proc2.returncode}")
    third_count = count_all_bout_records()
    record("Backfill is idempotent (row count unchanged on 2nd run)",
           third_count == after_count,
           f"round2={after_count} round3={third_count}")

    # ------------------------------------------------------------------
    # Scenario 6: Tournament detail page renders opponent badges
    # ------------------------------------------------------------------
    print("\nScenario 6: Tournament detail page")

    resp = c.get(f"/tournaments/{tid2}")
    record("GET /tournaments/<id> returns 200", resp.status_code == 200)
    html = resp.get_data(as_text=True)
    # Badge link targets /opponents/<id> — the known opponent appears in both
    # pool and DE sections so we should find at least one link.
    expected_link = f"/opponents/{existing_opp_id}"
    record("Tournament detail HTML contains an /opponents/<id> link",
           expected_link in html,
           f"looking for {expected_link}")
    record("Tournament detail HTML contains the 'View Intel' badge text",
           "View Intel" in html)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    cleanup()

    # --- Summary ---
    fails = [r for r in results if not r[1]]
    total = len(results)
    print()
    print(f"=== {total - len(fails)}/{total} passed ===")
    if fails:
        print("FAILURES:")
        for name, _, detail in fails:
            print(f"  - {name}" + (f" — {detail}" if detail else ""))
        sys.exit(1)
    print("ALL GREEN")


if __name__ == "__main__":
    main()
