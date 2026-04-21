#!/usr/bin/env python3
"""Phase 5 smoke test: Final Results photo extraction + Tournament Summary.

Exercises the new `/api/upload-final-results`, `/api/confirm-final-results`,
and `/api/tournaments/<id>/regenerate-summary` endpoints, plus the Tournament
Summary card rendering on the tournament detail page.

The narrative-generating scenarios require ``ANTHROPIC_API_KEY`` so they can
hit Claude end-to-end; they are skipped (not failed) when the env var is
unset. The Vision-extraction `extract_final_results` call is monkey-patched
so the test doesn't need Claude Vision.

Test rows use prefix ``TEST_P5_`` so cleanup is trivial.
"""

import os
import sys

from app import app
from database import (
    Tournament,
    TournamentSummary,
    create_tournament,
    delete_tournament,
    get_all_opponents,
    get_db,
    get_tournament,
    get_tournament_summary,
    delete_opponent,
)


PREFIX = "TEST_P5_"
HAS_ANTHROPIC_KEY = bool(os.environ.get('ANTHROPIC_API_KEY'))
results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def skip(name, detail=""):
    results.append((name, True, "(skipped) " + detail))
    print(f"  [SKIP] {name}" + (f" — {detail}" if detail else ""))


def authed_client():
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    return c


def cleanup():
    """Remove any TEST_P5_* tournaments, summaries, and stub opponents."""
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

    # Defensive — sweep any orphan TournamentSummary rows.
    db = get_db()
    try:
        db.query(TournamentSummary).filter(
            TournamentSummary.tournament_id.in_(t_ids)
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    # Stub opponents that Phase-5 tests might have created (none expected,
    # but be defensive in case future phases wire in stub creation).
    for opp in get_all_opponents():
        canonical = (opp.get("canonical_name") or "")
        if canonical.startswith(PREFIX):
            try:
                delete_opponent(opp["id"])
            except Exception:
                pass


def count_leftover():
    db = get_db()
    try:
        return db.query(Tournament).filter(
            Tournament.name.like(f"{PREFIX}%")
        ).count()
    finally:
        db.close()


# ── Synthetic extraction stub (no Claude Vision) ────────────────────────

SYNTHETIC_EXTRACTED = {
    'event_name': "Y-12 Men's Épée",
    'ethan_rank': '28T',
    'total_fencers': 36,
    'podium': [
        {'place': '1', 'name': 'JU Shang', 'club': 'Bayside Fencing Club', 'division': 'Central California'},
        {'place': '2', 'name': 'SAMOYLOV Daniel', 'club': 'Academy Of Fencing Masters (AFM)', 'division': 'Central California'},
        {'place': '3T', 'name': 'PARK Sihoon', 'club': 'LA International Fencing', 'division': 'Southern California'},
        {'place': '3T', 'name': 'KHUSHRAJ Rohan', 'club': 'Bayside Fencing Club', 'division': 'Central California'},
    ],
    'warnings': ['Ranks 17-20 not visible — possible gap between screenshots'],
}


def monkeypatch_extractor():
    """Replace `extract_final_results` at both import sites with a stub."""
    import app as app_module
    import final_results_extraction as fr_module

    def stub(image_paths, our_fencer_name, tournament_id=None):
        return dict(SYNTHETIC_EXTRACTED)

    app_module.extract_final_results = stub  # what the route actually calls
    fr_module.extract_final_results = stub


def main():
    print("=== Phase 5 Final Results smoke test ===\n")
    if not HAS_ANTHROPIC_KEY:
        print("ANTHROPIC_API_KEY not set — narrative-generation scenarios will be SKIPPED.\n")
    cleanup()
    monkeypatch_extractor()
    c = authed_client()

    # 1. Import does not crash.
    try:
        from final_results_extraction import extract_final_results  # noqa: F401
        record("final_results_extraction importable", True)
    except Exception as e:
        record("final_results_extraction importable", False, str(e))

    # 2. Auth guard.
    print("\nAuth guard:")
    unauthed = app.test_client()
    resp = unauthed.post('/api/upload-final-results', data={})
    record(
        "unauthed POST /api/upload-final-results redirects to /login",
        resp.status_code == 302 and '/login' in resp.headers.get('Location', ''),
        f"status={resp.status_code} location={resp.headers.get('Location', '')}"
    )

    # Seed a tournament for the real scenarios.
    t = create_tournament({
        'name': PREFIX + 'SYC Tournament',
        'date': '2026-04-15',
        'location': 'Test City',
        'level': 'SYC',
    })
    tid = t['id']

    # 7. Missing tournament_id → 400.
    print("\nEdge: confirm with missing tournament_id:")
    resp = c.post('/api/confirm-final-results', json={'final_results': {}})
    record(
        "POST /api/confirm-final-results without tournament_id → 400",
        resp.status_code == 400, f"status={resp.status_code}"
    )

    # 8. Unknown tournament_id → 404.
    print("\nEdge: confirm with unknown tournament_id:")
    resp = c.post('/api/confirm-final-results', json={
        'tournament_id': 99999999, 'final_results': SYNTHETIC_EXTRACTED
    })
    record(
        "POST /api/confirm-final-results with unknown id → 404",
        resp.status_code == 404, f"status={resp.status_code}"
    )

    # 3 + 4. Confirm persists columns + creates summary w/ narrative.
    print("\nConfirm final results (happy path):")
    if HAS_ANTHROPIC_KEY:
        resp = c.post('/api/confirm-final-results', json={
            'tournament_id': tid,
            'final_results': SYNTHETIC_EXTRACTED,
        })
        record(
            "POST /api/confirm-final-results → 200",
            resp.status_code == 200, f"status={resp.status_code}"
        )
        payload = resp.get_json() or {}
        record("response has summary key", 'summary' in payload, f"keys={list(payload.keys())}")

        tn = get_tournament(tid)
        record("Tournament.final_rank == '28T'",
               tn.get('final_rank') == '28T', f"got={tn.get('final_rank')}")
        record("Tournament.total_fencers == 36",
               tn.get('total_fencers') == 36, f"got={tn.get('total_fencers')}")
        record("Tournament.event_name == \"Y-12 Men's Épée\"",
               tn.get('event_name') == "Y-12 Men's Épée", f"got={tn.get('event_name')}")

        stored = get_tournament_summary(tid)
        data = (stored or {}).get('data') or {}
        record("TournamentSummary row exists", stored is not None)
        narrative = (data.get('narrative') or '').strip()
        record("TournamentSummary.narrative is non-empty",
               bool(narrative), f"len={len(narrative)}")
        record("TournamentSummary.podium has 4 entries",
               len(data.get('podium') or []) == 4,
               f"got {len(data.get('podium') or [])}")
    else:
        skip("POST /api/confirm-final-results (happy path)", "no ANTHROPIC_API_KEY")
        skip("TournamentSummary narrative non-empty", "no ANTHROPIC_API_KEY")
        # Even without Anthropic we can at least check the column writes via
        # the helper directly so Phase 5 rank/total/event are exercised.
        from app import _normalize_final_results_payload
        from database import update_tournament_final_results
        update_tournament_final_results(tid, _normalize_final_results_payload(SYNTHETIC_EXTRACTED))
        tn = get_tournament(tid)
        record("Tournament.final_rank == '28T' (via helper, no narrative)",
               tn.get('final_rank') == '28T', f"got={tn.get('final_rank')}")
        record("Tournament.total_fencers == 36 (via helper, no narrative)",
               tn.get('total_fencers') == 36, f"got={tn.get('total_fencers')}")

    # 5. Regenerate summary.
    print("\nRegenerate summary:")
    if HAS_ANTHROPIC_KEY:
        before = get_tournament_summary(tid)
        before_gen = (before or {}).get('generated_at')

        resp = c.post(f'/api/tournaments/{tid}/regenerate-summary', json={})
        record(
            f"POST /api/tournaments/{tid}/regenerate-summary → 200",
            resp.status_code == 200, f"status={resp.status_code}"
        )
        after = get_tournament_summary(tid)
        record("regenerate produced a summary row", after is not None)
        # generated_at is a string at ~minute precision; we don't require a
        # different value — just that the call succeeded and narrative exists.
        record("regenerated narrative non-empty",
               bool(((after or {}).get('data') or {}).get('narrative')),
               "")
    else:
        skip("POST /api/tournaments/<id>/regenerate-summary", "no ANTHROPIC_API_KEY")

    # 6. Tournament detail page renders the summary card.
    print("\nDetail page rendering:")
    resp = c.get(f'/tournaments/{tid}')
    record("GET /tournaments/<id> → 200",
           resp.status_code == 200, f"status={resp.status_code}")
    body = resp.get_data(as_text=True)

    if HAS_ANTHROPIC_KEY:
        record("Detail page contains 'Final Results' heading",
               'Final Results' in body)
        record("Detail page renders podium name 'JU Shang'",
               'JU Shang' in body, "")
        record("Detail page renders Ethan rank '28T'",
               '28T' in body, "")
        record("Detail page renders total fencers '36'",
               '36' in body, "")
        record("Detail page contains Regenerate summary link",
               'Regenerate summary' in body, "")
    else:
        # Without an API key, the confirm-final-results round-trip won't have
        # written the narrative. But the column helper did write rank/total/
        # event + podium inside summary_json, so those should still render.
        record("Detail page contains 'Final Results' heading",
               'Final Results' in body)
        record("Detail page renders rank '28T' (from helper)",
               '28T' in body, "")
        record("Detail page renders podium name 'JU Shang' (from helper)",
               'JU Shang' in body, "")

    # 9. Edge: confirm with an empty podium should still save + render.
    print("\nEdge: confirm with empty podium:")
    t2 = create_tournament({
        'name': PREFIX + 'Empty Podium Event',
        'date': '2026-03-01',
    })
    t2id = t2['id']
    empty_payload = {
        'event_name': None,
        'ethan_rank': '12',
        'total_fencers': None,
        'podium': [],
        'warnings': [],
    }
    if HAS_ANTHROPIC_KEY:
        resp = c.post('/api/confirm-final-results', json={
            'tournament_id': t2id,
            'final_results': empty_payload,
        })
        record("confirm w/ empty podium → 200",
               resp.status_code == 200, f"status={resp.status_code}")
        tn2 = get_tournament(t2id)
        record("empty-podium tournament got final_rank='12'",
               tn2.get('final_rank') == '12', f"got={tn2.get('final_rank')}")
        resp2 = c.get(f'/tournaments/{t2id}')
        record("GET /tournaments/<id> with empty podium → 200",
               resp2.status_code == 200, f"status={resp2.status_code}")
    else:
        from database import update_tournament_final_results
        update_tournament_final_results(t2id, empty_payload)
        tn2 = get_tournament(t2id)
        record("empty-podium tournament got final_rank='12' (via helper)",
               tn2.get('final_rank') == '12', f"got={tn2.get('final_rank')}")
        resp2 = c.get(f'/tournaments/{t2id}')
        record("GET /tournaments/<id> with empty podium → 200",
               resp2.status_code == 200, f"status={resp2.status_code}")

    # 10. Cleanup.
    print("\nCleanup:")
    cleanup()
    leftover = count_leftover()
    record("No TEST_P5_* tournaments remain after cleanup",
           leftover == 0, f"leftover={leftover}")

    # Tally.
    failed = [r for r in results if not r[1]]
    total = len(results)
    print(f"\n=== Phase 5 smoke test: {total - len(failed)}/{total} passed ===")
    if failed:
        print("FAILURES:")
        for name, _, detail in failed:
            print(f"  - {name} ({detail})")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
