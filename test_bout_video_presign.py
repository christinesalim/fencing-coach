#!/usr/bin/env python3
"""Smoke test for the presigned direct-to-R2 bout-video upload (Phase 1).

Covers the two new endpoint pairs added for pool bouts and elim rounds:

    POST /api/pool-bouts/<id>/videos/presign
    POST /api/pool-bouts/<id>/videos/register
    POST /api/elimination-rounds/<id>/videos/presign
    POST /api/elimination-rounds/<id>/videos/register

R2 is stubbed via a monkey-patched ``app.get_r2_client`` so no real Cloudflare
calls happen. All DB rows created use the PRESIGN_TEST_ prefix (on
``opponent_name`` for pool/elim rows) and get cleaned up on exit.

Exits 0 only if every scenario PASSes.
"""

import sys
from unittest.mock import MagicMock

import app as app_module
from app import app
from database import (
    BoutVideo,
    EliminationRound,
    PoolBout,
    get_db,
)


PREFIX = "PRESIGN_TEST_"
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
    mock_client.generate_presigned_url = MagicMock(
        return_value="https://r2.example.test/signed-put-url"
    )
    mock_client.head_object = MagicMock(return_value={"ContentLength": 1234})
    app_module.get_r2_client = lambda: mock_client
    return mock_client


def create_pool_bout():
    db = get_db()
    try:
        b = PoolBout(
            pool_round_id=0,
            opponent_name=f"{PREFIX}POOL",
            opponent_club=f"{PREFIX}CLUB",
            score_for=5, score_against=3, result="won",
            bout_order=1,
        )
        db.add(b)
        db.commit()
        return b.id
    finally:
        db.close()


def create_elim_round():
    db = get_db()
    try:
        r = EliminationRound(
            tournament_id=0,
            round_name=f"{PREFIX}T32",
            opponent_name=f"{PREFIX}ELIM",
            opponent_club=f"{PREFIX}CLUB",
            score_for=15, score_against=12, result="won",
            bout_order=1,
        )
        db.add(r)
        db.commit()
        return r.id
    finally:
        db.close()


def cleanup():
    """Remove any PRESIGN_TEST_* rows."""
    db = get_db()
    try:
        pool_ids = [b.id for b in db.query(PoolBout).filter(
            PoolBout.opponent_name.like(f"{PREFIX}%")
        ).all()]
        elim_ids = [r.id for r in db.query(EliminationRound).filter(
            EliminationRound.opponent_name.like(f"{PREFIX}%")
        ).all()]
        # Delete any BoutVideo rows attached to these bouts
        for bid in pool_ids:
            db.query(BoutVideo).filter_by(bout_kind="pool", bout_id=bid).delete()
        for rid in elim_ids:
            db.query(BoutVideo).filter_by(bout_kind="elim", bout_id=rid).delete()
        db.query(PoolBout).filter(PoolBout.id.in_(pool_ids)).delete(synchronize_session=False) if pool_ids else None
        db.query(EliminationRound).filter(EliminationRound.id.in_(elim_ids)).delete(synchronize_session=False) if elim_ids else None
        db.commit()
    finally:
        db.close()


def main():
    cleanup()
    print("Bout-video presigned upload smoke test (Phase 1)")
    print("=" * 55)

    mock_r2 = install_r2_mock()

    # 1. Auth: every new route 302s when unauthed ----------------------
    unauthed = app.test_client()
    routes = [
        "/api/pool-bouts/1/videos/presign",
        "/api/pool-bouts/1/videos/register",
        "/api/elimination-rounds/1/videos/presign",
        "/api/elimination-rounds/1/videos/register",
    ]
    failures = []
    for path in routes:
        r = unauthed.post(path, json={})
        if r.status_code != 302 or "/login" not in (r.headers.get("Location") or ""):
            failures.append(f"{path}={r.status_code}")
    record(
        "auth: all four new routes redirect to /login when unauthed",
        not failures,
        "; ".join(failures),
    )

    c = authed_client()
    pool_id = create_pool_bout()
    elim_id = create_elim_round()

    # 2. Presign (pool): happy path -----------------------------------
    r = c.post(
        f"/api/pool-bouts/{pool_id}/videos/presign",
        json={"filename": "my clip.mp4"},  # name has space to exercise secure_filename
    )
    j = r.get_json() or {}
    expected_prefix = f"bout-videos/pool_{pool_id}_"
    presign_ok = (
        r.status_code == 200
        and j.get("upload_url", "").startswith("https://")
        and j.get("r2_key", "").startswith(expected_prefix)
        and j.get("r2_key", "").endswith(".mp4")
        and j.get("content_type") == "video/mp4"
        and j.get("expires_in") == 3600
    )
    record(
        "presign (pool): returns upload_url + namespaced r2_key + content_type",
        presign_ok,
        f"status={r.status_code} body={j}",
    )

    # Also confirm the ExtraArgs we passed to boto3 are what we expect
    call = mock_r2.generate_presigned_url.call_args
    params = (call.kwargs if call else {}).get("Params") or {}
    record(
        "presign (pool): boto3 called with put_object + Key + ContentType",
        (call.args[0] if call and call.args else None) == "put_object"
        and params.get("Key", "").startswith(expected_prefix)
        and params.get("ContentType") == "video/mp4",
        f"args={call.args if call else None} params={params}",
    )

    presigned_pool_key = j.get("r2_key")

    # 3. Presign (elim): happy path -----------------------------------
    r = c.post(
        f"/api/elimination-rounds/{elim_id}/videos/presign",
        json={"filename": "bout.mov"},
    )
    j = r.get_json() or {}
    expected_elim_prefix = f"bout-videos/elim_{elim_id}_"
    record(
        "presign (elim): returns namespaced r2_key with .mov extension",
        r.status_code == 200
        and j.get("r2_key", "").startswith(expected_elim_prefix)
        and j.get("r2_key", "").endswith(".mov")
        and j.get("content_type") == "video/quicktime",
        f"status={r.status_code} body={j}",
    )
    presigned_elim_key = j.get("r2_key")

    # 4. Presign: nonexistent bout → 404 -------------------------------
    r = c.post("/api/pool-bouts/999999/videos/presign", json={"filename": "x.mp4"})
    record(
        "presign: nonexistent bout → 404",
        r.status_code == 404 and (r.get_json() or {}).get("error"),
        f"status={r.status_code} body={r.get_json()}",
    )

    # 5. Presign: bad extension → 400 ---------------------------------
    r = c.post(
        f"/api/pool-bouts/{pool_id}/videos/presign",
        json={"filename": "evil.exe"},
    )
    record(
        "presign: unsupported extension → 400",
        r.status_code == 400 and "Unsupported" in ((r.get_json() or {}).get("error") or ""),
        f"status={r.status_code} body={r.get_json()}",
    )

    # 6. Register (pool): happy path — head_object succeeds, DB row created
    r = c.post(
        f"/api/pool-bouts/{pool_id}/videos/register",
        json={"r2_key": presigned_pool_key},
    )
    j = r.get_json() or {}
    register_ok = r.status_code == 200 and j.get("success") and isinstance(j.get("video_id"), int)
    record(
        "register (pool): HEAD-checks R2 then creates BoutVideo row",
        register_ok and mock_r2.head_object.called,
        f"status={r.status_code} body={j} head_called={mock_r2.head_object.called}",
    )

    # Verify the row actually landed with correct fields
    if register_ok:
        db = get_db()
        try:
            v = db.query(BoutVideo).filter_by(id=j["video_id"]).first()
            row_ok = v is not None and v.bout_kind == "pool" and v.bout_id == pool_id and v.r2_key == presigned_pool_key
        finally:
            db.close()
        record(
            "register (pool): persisted row matches submitted r2_key",
            row_ok,
            f"row={v and (v.bout_kind, v.bout_id, v.r2_key)}",
        )

    # 7. Register (elim): happy path ----------------------------------
    r = c.post(
        f"/api/elimination-rounds/{elim_id}/videos/register",
        json={"r2_key": presigned_elim_key},
    )
    j = r.get_json() or {}
    record(
        "register (elim): creates BoutVideo row for elim-kind",
        r.status_code == 200 and j.get("success") and isinstance(j.get("video_id"), int),
        f"status={r.status_code} body={j}",
    )

    # 8. Register: cross-bout key injection → 400 ---------------------
    other_pool_id = create_pool_bout()
    foreign_key = f"bout-videos/pool_{other_pool_id}_abc.mp4"
    r = c.post(
        f"/api/pool-bouts/{pool_id}/videos/register",
        json={"r2_key": foreign_key},
    )
    record(
        "register: rejects r2_key belonging to a different bout",
        r.status_code == 400 and "does not match" in ((r.get_json() or {}).get("error") or ""),
        f"status={r.status_code} body={r.get_json()}",
    )

    # 9. Register: nonexistent bout → 404 -----------------------------
    r = c.post(
        "/api/pool-bouts/999999/videos/register",
        json={"r2_key": "bout-videos/pool_999999_x.mp4"},
    )
    record(
        "register: nonexistent bout → 404",
        r.status_code == 404,
        f"status={r.status_code}",
    )

    # 10. Register: R2 HEAD fails (upload didn't actually happen) → 400
    mock_r2.head_object.side_effect = Exception("NoSuchKey")
    try:
        r = c.post(
            f"/api/pool-bouts/{pool_id}/videos/register",
            json={"r2_key": presigned_pool_key},  # key format valid; HEAD will fail
        )
        record(
            "register: R2 HEAD miss → 400 'file not found in R2'",
            r.status_code == 400 and "not found in R2" in ((r.get_json() or {}).get("error") or ""),
            f"status={r.status_code} body={r.get_json()}",
        )
    finally:
        mock_r2.head_object.side_effect = None

    # 11. Old /videos endpoint still exists (rollback safety) ---------
    # We deliberately did NOT delete the old upload endpoint. Confirm it still
    # responds (its own body-missing error path will fire).
    r = c.post(f"/api/pool-bouts/{pool_id}/videos")
    record(
        "old /videos endpoint still mounted (rollback target)",
        r.status_code in (400, 500),  # 400 "No video file uploaded"
        f"status={r.status_code}",
    )

    # Cleanup ---------------------------------------------------------
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
