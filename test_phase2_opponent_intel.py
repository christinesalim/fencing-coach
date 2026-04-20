#!/usr/bin/env python3
"""Phase 2 smoke test: Opponent Intelligence API + page routes.

Exercises every endpoint added in Phase 2 via Flask's test client. Prints
PASS/FAIL per scenario. Exits nonzero if any scenario fails. Uses a
QA_P2_* prefix on canonical_name so cleanup is idempotent.
"""

import sys

from app import app
from database import get_all_opponents, delete_opponent


TEST_NAME_PREFIX = "QA_P2_"

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def cleanup():
    """Remove any QA_P2_* opponents from previous runs."""
    for opp in get_all_opponents():
        if (opp.get("canonical_name") or "").startswith(TEST_NAME_PREFIX):
            try:
                delete_opponent(opp["id"])
            except Exception:
                pass


def authed_client():
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    return c


def unauthed_client():
    return app.test_client()


def main():
    print("=== Phase 2 Opponent Intel smoke test ===\n")
    cleanup()

    # --- Auth guard tests (no session) ---
    print("Auth guards:")
    for path in ["/opponents", "/opponents/1", "/api/opponents"]:
        resp = unauthed_client().get(path)
        record(
            f"GET {path} unauthed redirects to /login",
            resp.status_code == 302 and "/login" in (resp.headers.get("Location") or ""),
            f"status={resp.status_code}",
        )

    c = authed_client()

    # --- Page routes ---
    print("\nPage routes:")
    resp = c.get("/opponents")
    record("GET /opponents returns 200", resp.status_code == 200, f"status={resp.status_code}")
    body = resp.get_data(as_text=True)
    record(
        "GET /opponents contains 'Opponent Intel' title",
        "Opponent Intel" in body,
    )
    record(
        "GET /opponents contains New Opponent FAB",
        "openNewOpponentModal" in body,
    )

    resp = c.get("/opponents/9999999")
    record("GET /opponents/9999999 returns 404", resp.status_code == 404, f"status={resp.status_code}")

    # --- Create opponent ---
    print("\nCreate opponent:")
    create_payload = {
        "first_name": "Testy",
        "last_name": TEST_NAME_PREFIX + "SMITH",
        "club": "Test Club",
        "handedness": "right",
        "height_category": "tall",
        "build": "athletic",
        "speed_rating": "fast",
        "primary_style": "aggressive",
        "division": "Pacific Coast",
    }
    resp = c.post("/api/opponents", json=create_payload)
    record("POST /api/opponents creates opponent", resp.status_code == 200,
           f"status={resp.status_code}")
    data = resp.get_json() or {}
    record(
        "Create response has success and opponent",
        data.get("success") is True and isinstance(data.get("opponent"), dict),
    )
    opp = data.get("opponent") or {}
    opponent_id = opp.get("id")
    record("Created opponent has an id", bool(opponent_id))
    record(
        "Canonical name auto-synthesized",
        (opp.get("canonical_name") or "").startswith(TEST_NAME_PREFIX),
        f"canonical={opp.get('canonical_name')}",
    )

    # --- List opponents ---
    print("\nList / get opponents:")
    resp = c.get("/api/opponents")
    record("GET /api/opponents returns 200", resp.status_code == 200)
    data = resp.get_json() or {}
    record(
        "List response has opponents array containing our test opponent",
        any(o.get("id") == opponent_id for o in (data.get("opponents") or [])),
    )

    # Single GET
    resp = c.get(f"/api/opponents/{opponent_id}")
    record(f"GET /api/opponents/{opponent_id} returns 200", resp.status_code == 200)
    data = resp.get_json() or {}
    record(
        "Single GET includes opponent + head_to_head",
        isinstance(data.get("opponent"), dict) and "head_to_head" in data,
    )

    resp = c.get("/api/opponents/9999999")
    record("GET /api/opponents/9999999 returns 404", resp.status_code == 404)

    # --- Update opponent ---
    print("\nUpdate opponent:")
    resp = c.post(f"/api/opponents/{opponent_id}", json={"speed_rating": "very_fast"})
    record("POST /api/opponents/<id> update returns 200", resp.status_code == 200)
    resp = c.get(f"/api/opponents/{opponent_id}")
    record(
        "speed_rating persisted as very_fast",
        (resp.get_json() or {}).get("opponent", {}).get("speed_rating") == "very_fast",
    )

    resp = c.post("/api/opponents/9999999", json={"speed_rating": "fast"})
    record("POST /api/opponents/9999999 (missing) returns 404", resp.status_code == 404)

    # --- Add tactical note ---
    print("\nTactical notes:")
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes",
        json={"category": "weakness", "observation": "Slow on parry 4 riposte"},
    )
    record("POST /api/opponents/<id>/notes adds note", resp.status_code == 200)
    note = (resp.get_json() or {}).get("note") or {}
    note_id = note.get("id")
    record("Note has id", bool(note_id))

    # Missing observation should 400
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes",
        json={"category": "weakness"},
    )
    record(
        "POST /api/opponents/<id>/notes without observation returns 400",
        resp.status_code == 400,
    )

    # Validate
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/{note_id}/validate"
    )
    record("POST .../validate returns 200", resp.status_code == 200)
    updated = (resp.get_json() or {}).get("note") or {}
    record(
        "times_validated incremented to 1",
        updated.get("times_validated") == 1,
        f"got {updated.get('times_validated')}",
    )

    # Validate again
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/{note_id}/validate"
    )
    updated = (resp.get_json() or {}).get("note") or {}
    record(
        "times_validated increments on repeat",
        updated.get("times_validated") == 2,
    )

    # Invalidate
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/{note_id}/invalidate"
    )
    updated = (resp.get_json() or {}).get("note") or {}
    record(
        "times_invalidated incremented to 1",
        updated.get("times_invalidated") == 1,
    )

    # Update note text
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/{note_id}",
        json={"observation": "Slow on parry 4 riposte; overshoots distance"},
    )
    record("POST /api/opponents/<id>/notes/<note_id> updates note", resp.status_code == 200)

    # Validate missing note
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/9999999/validate"
    )
    record("validate on missing note returns 404", resp.status_code == 404)

    # --- Bout record ---
    print("\nBout records:")
    bout_payload = {
        "tournament_name": "QA_P2_SYC Test",
        "tournament_date": "2026-03-10",
        "bout_type": "pool",
        "score_for": 5,
        "score_against": 3,
        "result": "won",
        "notes": "Smoke test pool bout",
    }
    resp = c.post(f"/api/opponents/{opponent_id}/bouts", json=bout_payload)
    record("POST /api/opponents/<id>/bouts adds bout", resp.status_code == 200)
    bout = (resp.get_json() or {}).get("bout") or {}
    record("Bout has id", bool(bout.get("id")))

    resp = c.post("/api/opponents/9999999/bouts", json=bout_payload)
    record("POST /api/opponents/9999999/bouts returns 404", resp.status_code == 404)

    # Bout should show up in head-to-head
    resp = c.get(f"/api/opponents/{opponent_id}")
    h2h = (resp.get_json() or {}).get("head_to_head") or {}
    record(
        "Bout shows up in head_to_head (wins=1)",
        h2h.get("wins") == 1 and len(h2h.get("bouts") or []) == 1,
    )

    # --- Add a DE bout too to test trend rendering logic ---
    c.post(
        f"/api/opponents/{opponent_id}/bouts",
        json={
            "tournament_name": "QA_P2_SYC Test",
            "tournament_date": "2026-03-10",
            "bout_type": "elimination",
            "score_for": 10,
            "score_against": 12,
            "result": "lost",
        },
    )

    # --- Search ---
    print("\nSearch / filter:")
    resp = c.get(f"/api/opponents/search?q={TEST_NAME_PREFIX}SMITH")
    record("GET /api/opponents/search returns 200", resp.status_code == 200)
    data = resp.get_json() or {}
    record(
        "Search returns matches array",
        isinstance(data.get("matches"), list),
    )
    matched_ids = [m.get("opponent", {}).get("id") for m in data.get("matches") or []]
    record("Test opponent appears in search results", opponent_id in matched_ids)

    resp = c.get("/api/opponents/search?q=")
    record("GET /api/opponents/search with empty q returns {matches: []}",
           resp.status_code == 200 and (resp.get_json() or {}).get("matches") == [])

    # Filter
    resp = c.get("/api/opponents/filter?handedness=right&height_category=tall")
    record("GET /api/opponents/filter returns 200", resp.status_code == 200)
    data = resp.get_json() or {}
    filter_ids = [o.get("id") for o in data.get("opponents") or []]
    record("Filter returns our opponent", opponent_id in filter_ids)

    # Filter that should exclude
    resp = c.get("/api/opponents/filter?handedness=left")
    data = resp.get_json() or {}
    filter_ids = [o.get("id") for o in data.get("opponents") or []]
    record("Filter excludes non-matching", opponent_id not in filter_ids)

    # --- Delete note ---
    print("\nDelete flows:")
    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/{note_id}/delete"
    )
    record("POST .../notes/<note_id>/delete returns 200", resp.status_code == 200)

    resp = c.post(
        f"/api/opponents/{opponent_id}/notes/9999999/delete"
    )
    record("Delete missing note returns 404", resp.status_code == 404)

    # --- Render profile page ---
    resp = c.get(f"/opponents/{opponent_id}")
    record("GET /opponents/<id> returns 200", resp.status_code == 200)
    body = resp.get_data(as_text=True)
    record("Profile page contains Save Changes button", "Save Changes" in body)
    record("Profile page contains Add Historical Bout", "Add Historical Bout" in body)

    # --- Delete opponent ---
    resp = c.post(f"/api/opponents/{opponent_id}/delete")
    record("POST /api/opponents/<id>/delete returns 200", resp.status_code == 200)

    resp = c.post("/api/opponents/9999999/delete")
    record("POST /api/opponents/9999999/delete returns 404", resp.status_code == 404)

    # Confirm gone
    resp = c.get(f"/api/opponents/{opponent_id}")
    record("Opponent is gone after delete (404)", resp.status_code == 404)

    # Final cleanup
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
