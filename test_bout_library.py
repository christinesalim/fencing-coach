#!/usr/bin/env python3
"""Bout Library smoke test (Phase 1 + Phase 2).

Exercises the new /bout-library page, the /api/scout-bouts/* endpoints,
the /api/scout-videos/* endpoints, the opponent-profile + opponent-intel
integrations, and the cascade-delete-with-R2-purge behaviour.

R2 calls are stubbed via a monkey-patched ``app.get_r2_client`` so this
test never touches Cloudflare. Every persisted record uses the BL_TEST_
prefix so cleanup is trivial.

Exits 0 only if all scenarios PASS.
"""

import io
import sys
from unittest.mock import MagicMock

import app as app_module
from app import app
from database import (
    Opponent,
    ScoutBout,
    ScoutVideo,
    create_opponent,
    create_scout_bout,
    delete_opponent,
    delete_scout_bout,
    get_db,
    get_scout_bout,
    get_scout_bouts_for_opponent,
)


PREFIX = "BL_TEST_"
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


def install_r2_mock():
    """Replace app.get_r2_client so no real boto3 calls happen."""
    mock_client = MagicMock()
    mock_client.upload_file = MagicMock()
    mock_client.delete_object = MagicMock()
    mock_client.generate_presigned_url = MagicMock(
        return_value="https://r2.example.test/scout/abc.mp4"
    )
    app_module.get_r2_client = lambda: mock_client
    return mock_client


def cleanup():
    """Remove any BL_TEST_* records left by previous runs."""
    db = get_db()
    try:
        # Scout videos attached to bouts whose names use the prefix
        bouts = (
            db.query(ScoutBout)
            .filter(
                (ScoutBout.fencer_a_name.like(f"{PREFIX}%"))
                | (ScoutBout.fencer_b_name.like(f"{PREFIX}%"))
                | (ScoutBout.tournament_name.like(f"{PREFIX}%"))
            )
            .all()
        )
        for bout in bouts:
            try:
                delete_scout_bout(bout.id)
            except Exception:
                pass
    finally:
        db.close()

    db = get_db()
    try:
        opps = (
            db.query(Opponent)
            .filter(
                (Opponent.canonical_name.like(f"{PREFIX}%"))
                | (Opponent.last_name.like(f"{PREFIX}%"))
                | (Opponent.first_name.like(f"{PREFIX}%"))
                | (Opponent.club.like(f"{PREFIX}%"))
            )
            .all()
        )
        opp_ids = [o.id for o in opps]
    finally:
        db.close()
    for oid in opp_ids:
        try:
            delete_opponent(oid)
        except Exception:
            pass


def count_leftover():
    """Count BL_TEST_* records still in DB after cleanup."""
    leftover = 0
    db = get_db()
    try:
        leftover += db.query(ScoutBout).filter(
            (ScoutBout.fencer_a_name.like(f"{PREFIX}%"))
            | (ScoutBout.fencer_b_name.like(f"{PREFIX}%"))
            | (ScoutBout.tournament_name.like(f"{PREFIX}%"))
        ).count()
        leftover += db.query(Opponent).filter(
            (Opponent.canonical_name.like(f"{PREFIX}%"))
            | (Opponent.last_name.like(f"{PREFIX}%"))
            | (Opponent.first_name.like(f"{PREFIX}%"))
            | (Opponent.club.like(f"{PREFIX}%"))
        ).count()
    finally:
        db.close()
    return leftover


def main():
    cleanup()

    print("Bout Library smoke test")
    print("=" * 50)

    mock_r2 = install_r2_mock()

    # 1. Imports ----------------------------------------------------------
    try:
        # Imports already happened at top of file; this is a sanity check.
        assert callable(create_scout_bout)
        record("imports", True)
    except Exception as e:
        record("imports", False, str(e))

    # 2. Auth guards ------------------------------------------------------
    unauthed = app.test_client()
    auth_routes = [
        ("/bout-library", "GET"),
        ("/api/scout-bouts", "GET"),
        ("/api/scout-bouts", "POST"),
        ("/api/scout-bouts/1", "GET"),
        ("/api/scout-bouts/1", "POST"),
        ("/api/scout-bouts/1/delete", "POST"),
        ("/api/scout-bouts/1/videos", "POST"),
        ("/api/scout-videos/1/playback", "GET"),
        ("/api/scout-videos/1", "POST"),
        ("/api/scout-videos/1/delete", "POST"),
    ]
    auth_failures = []
    for path, method in auth_routes:
        if method == "GET":
            r = unauthed.get(path)
        else:
            r = unauthed.post(path)
        if r.status_code != 302 or "/login" not in (r.headers.get("Location") or ""):
            auth_failures.append(f"{method} {path} = {r.status_code}")
    record(
        "auth: every new route 302s to /login when unauthed",
        not auth_failures,
        ", ".join(auth_failures) if auth_failures else "",
    )

    c = authed_client()

    # 3. Create scout bout with no matching opponents -------------------
    body = {
        "fencer_a_name": f"{PREFIX}NEWFENCER A",
        "fencer_b_name": f"{PREFIX}NEWFENCER B",
        "tournament_name": f"{PREFIX}TOURNEY",
        "round_name": "Pool",
        "score": "5-3",
        "notes": "BL_TEST teaching note",
        "tags": ["lefty_vs_righty"],
    }
    r = c.post("/api/scout-bouts", json=body)
    bout_data = r.get_json() or {}
    bout = bout_data.get("bout") or {}
    bout_id = bout.get("id")
    record(
        "create scout bout (unmatched)",
        r.status_code == 200 and bout_id is not None
        and bout.get("fencer_a_id") is None
        and bout.get("fencer_b_id") is None,
        f"status={r.status_code} fa_id={bout.get('fencer_a_id')} fb_id={bout.get('fencer_b_id')}",
    )

    # 4. Auto-link Tier 1 (exact name + same club) -----------------------
    opp = create_opponent({
        "canonical_name": f"{PREFIX}OPP1 X",
        "club": f"{PREFIX}CLUB",
    })
    opp_id = opp["id"]
    body2 = {
        "fencer_a_name": f"{PREFIX}OPP1 X",
        "fencer_a_club": f"{PREFIX}CLUB",
        "fencer_b_name": f"{PREFIX}OTHER FENCER",
        "tournament_name": f"{PREFIX}TOURNEY",
        "notes": "BL_TEST link check",
        "tags": [],
    }
    r2 = c.post("/api/scout-bouts", json=body2)
    bout2 = (r2.get_json() or {}).get("bout") or {}
    record(
        "auto-link Tier 1 opponent on fencer_a",
        r2.status_code == 200 and bout2.get("fencer_a_id") == opp_id,
        f"status={r2.status_code} fencer_a_id={bout2.get('fencer_a_id')} expected={opp_id}",
    )

    # 5. Upload 3 dummy clips --------------------------------------------
    files_for_upload = {
        "files": [
            (io.BytesIO(b"x" * 32), "BL_TEST_clip_a.mp4"),
            (io.BytesIO(b"x" * 32), "BL_TEST_clip_b.mp4"),
            (io.BytesIO(b"x" * 32), "BL_TEST_clip_c.mp4"),
        ],
    }
    r3 = c.post(
        f"/api/scout-bouts/{bout_id}/videos",
        data=files_for_upload,
        content_type="multipart/form-data",
    )
    upload_data = r3.get_json() or {}
    videos = upload_data.get("videos") or []
    sort_orders = sorted([v.get("sort_order") for v in videos])
    record(
        "upload 3 clips",
        r3.status_code == 200 and len(videos) == 3 and sort_orders == [0, 1, 2]
        and mock_r2.upload_file.call_count >= 3,
        f"status={r3.status_code} count={len(videos)} sorts={sort_orders} r2_uploads={mock_r2.upload_file.call_count}",
    )

    # 6. GET bout returns videos in sort order ----------------------------
    r4 = c.get(f"/api/scout-bouts/{bout_id}")
    fetched = (r4.get_json() or {}).get("bout") or {}
    fetched_videos = fetched.get("videos") or []
    sort_in_order = [v.get("sort_order") for v in fetched_videos] == [0, 1, 2]
    record(
        "GET bout returns 3 videos in order",
        r4.status_code == 200 and len(fetched_videos) == 3 and sort_in_order,
        f"status={r4.status_code} count={len(fetched_videos)} sorts={[v.get('sort_order') for v in fetched_videos]}",
    )

    first_video_id = fetched_videos[0]["id"] if fetched_videos else None

    # 7. Playback URL ----------------------------------------------------
    r5 = c.get(f"/api/scout-videos/{first_video_id}/playback")
    playback = r5.get_json() or {}
    record(
        "playback URL for clip",
        r5.status_code == 200 and "url" in playback,
        f"status={r5.status_code} body={playback}",
    )

    # 8. Update clip notes -----------------------------------------------
    r6 = c.post(
        f"/api/scout-videos/{first_video_id}",
        json={"clip_notes": "the duck"},
    )
    updated = (r6.get_json() or {}).get("video") or {}
    record(
        "update clip_notes",
        r6.status_code == 200 and updated.get("clip_notes") == "the duck",
        f"status={r6.status_code} clip_notes={updated.get('clip_notes')}",
    )

    # 9. Delete a single clip --------------------------------------------
    pre_delete_calls = mock_r2.delete_object.call_count
    r7 = c.post(f"/api/scout-videos/{first_video_id}/delete")
    after_get = c.get(f"/api/scout-bouts/{bout_id}").get_json() or {}
    after_videos = (after_get.get("bout") or {}).get("videos") or []
    record(
        "delete single clip + R2 purge",
        r7.status_code == 200
        and len(after_videos) == 2
        and mock_r2.delete_object.call_count >= pre_delete_calls + 1,
        f"status={r7.status_code} remaining={len(after_videos)} r2_deletes={mock_r2.delete_object.call_count}",
    )

    # 10. /bout-library page renders -------------------------------------
    r8 = c.get("/bout-library")
    page_html = r8.get_data(as_text=True) if r8.status_code == 200 else ""
    has_opp = f"{PREFIX}OPP1 X" in page_html
    has_notes = "BL_TEST teaching note" in page_html
    has_clip = "Clip 1" in page_html or "Clip" in page_html
    record(
        "GET /bout-library renders fenced HTML",
        r8.status_code == 200 and has_opp and has_notes and has_clip,
        f"status={r8.status_code} opp={has_opp} notes={has_notes} clip={has_clip}",
    )

    # 11. /bout-library?opponent_id=<id> filtering -----------------------
    r9 = c.get(f"/bout-library?opponent_id={opp_id}")
    body9 = r9.get_data(as_text=True) if r9.status_code == 200 else ""
    in_filtered = f"{PREFIX}OPP1 X" in body9
    other_bout_excluded = (f"{PREFIX}NEWFENCER A" not in body9) or (
        f"{PREFIX}NEWFENCER B" not in body9
    )
    record(
        "GET /bout-library?opponent_id=<id>",
        r9.status_code == 200 and in_filtered and other_bout_excluded,
        f"status={r9.status_code} included={in_filtered} excluded_other={other_bout_excluded}",
    )

    # 12. opponent profile page contains scouting section ---------------
    r10 = c.get(f"/opponents/{opp_id}")
    profile_html = r10.get_data(as_text=True) if r10.status_code == 200 else ""
    record(
        "opponent profile contains Scouting Videos section + bout",
        r10.status_code == 200
        and "Scouting Videos" in profile_html
        and f"{PREFIX}OTHER FENCER" in profile_html,
        f"status={r10.status_code}",
    )

    # 13. opponent intel page contains collapsible scouting markup ------
    r11 = c.get(f"/opponents/{opp_id}/intel")
    intel_html = r11.get_data(as_text=True) if r11.status_code == 200 else ""
    record(
        "opponent intel contains scouting section markup",
        r11.status_code == 200
        and "Scouting Videos" in intel_html
        and "scoutSection" in intel_html,
        f"status={r11.status_code}",
    )

    # 14. /api/opponents/<id>/intel JSON includes scout_bouts -----------
    r12 = c.get(f"/api/opponents/{opp_id}/intel")
    intel_json = r12.get_json() or {}
    scout_list = intel_json.get("scout_bouts")
    record(
        "intel JSON includes scout_bouts list",
        r12.status_code == 200
        and isinstance(scout_list, list)
        and len(scout_list) >= 1,
        f"status={r12.status_code} type={type(scout_list).__name__} len={len(scout_list) if isinstance(scout_list, list) else 'n/a'}",
    )

    # 15. Cascade delete bout + clips + R2 purge ------------------------
    pre_calls = mock_r2.delete_object.call_count
    # Get videos still attached to the cascade-target bout
    remaining = get_scout_bout(bout_id) or {}
    remaining_clip_count = len(remaining.get("videos") or [])
    r13 = c.post(f"/api/scout-bouts/{bout_id}/delete")
    after_get_404 = c.get(f"/api/scout-bouts/{bout_id}")
    record(
        "cascade delete bout + clips + R2 purge",
        r13.status_code == 200
        and after_get_404.status_code == 404
        and mock_r2.delete_object.call_count >= pre_calls + remaining_clip_count,
        f"status={r13.status_code} get_after={after_get_404.status_code} "
        f"remaining_pre_delete={remaining_clip_count} new_r2_calls={mock_r2.delete_object.call_count - pre_calls}",
    )

    # 16. Cleanup ---------------------------------------------------------
    cleanup()
    leftover = count_leftover()
    record("cleanup BL_TEST_* rows", leftover == 0, f"leftover={leftover}")

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
