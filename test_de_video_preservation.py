#!/usr/bin/env python3
"""Smoke test: re-uploading DE results preserves attached bout videos.

Before this fix, save_de_results_to_db unconditionally deleted all
EliminationRound rows and inserted fresh ones with new IDs, orphaning
every BoutVideo that pointed at the old IDs. The fix snapshots the
(round_name, opponent_name) key of each video's old elim row, then
after recreate rewires BoutVideo.bout_id to the matching new row.

All rows created here use the DEVID_TEST_ prefix (tournament name,
opponent names) and get cleaned up at the end.

Exits 0 only if every scenario PASSes.
"""

import sys
from datetime import datetime

from database import (
    BoutVideo,
    DEBracket,
    EliminationRound,
    Tournament,
    add_bout_video,
    get_db,
    save_de_results_to_db,
)


PREFIX = "DEVID_TEST_"
results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def make_tournament():
    """Create a tournament row for the test and return its id."""
    db = get_db()
    try:
        t = Tournament(name=f"{PREFIX}T", date=datetime(2026, 1, 1))
        db.add(t)
        db.commit()
        return t.id
    finally:
        db.close()


def elim_rows(tournament_id):
    db = get_db()
    try:
        return [
            {"id": r.id, "round": r.round_name, "opp": r.opponent_name}
            for r in db.query(EliminationRound).filter_by(
                tournament_id=tournament_id
            ).order_by(EliminationRound.bout_order).all()
        ]
    finally:
        db.close()


def videos_for_elim(elim_id):
    db = get_db()
    try:
        return [
            v.id for v in db.query(BoutVideo).filter_by(
                bout_kind="elim", bout_id=elim_id
            ).all()
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
            elim_ids = [r.id for r in db.query(EliminationRound).filter(
                EliminationRound.tournament_id.in_(tids)
            ).all()]
            if elim_ids:
                db.query(BoutVideo).filter(
                    BoutVideo.bout_kind == "elim",
                    BoutVideo.bout_id.in_(elim_ids),
                ).delete(synchronize_session=False)
            db.query(EliminationRound).filter(
                EliminationRound.tournament_id.in_(tids)
            ).delete(synchronize_session=False)
            db.query(DEBracket).filter(
                DEBracket.tournament_id.in_(tids)
            ).delete(synchronize_session=False)
            db.query(Tournament).filter(Tournament.id.in_(tids)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def bracket(path_bouts):
    """Build a bracket_data dict with the given list of (round, opponent, result) tuples."""
    return {
        "our_fencer": {
            "path": [
                {
                    "round_name": r,
                    "opponent_name": opp,
                    "opponent_club": f"{PREFIX}CLUB",
                    "opponent_seed": i + 1,
                    "score_for": sf,
                    "score_against": sa,
                    "result": res,
                }
                for i, (r, opp, sf, sa, res) in enumerate(path_bouts)
            ]
        },
        "tournament_bracket": {"bracket_size": 32, "completeness": "complete"},
    }


def main():
    cleanup()
    print("DE re-upload video preservation smoke test")
    print("=" * 50)

    tid = make_tournament()

    # 1. Initial DE save (3 bouts) -----------------------------------
    first = bracket([
        ("T32",   f"{PREFIX}ALICE",   15, 3,  "won"),
        ("T16",   f"{PREFIX}BOB",     15, 10, "won"),
        ("Final", f"{PREFIX}CARLA",   10, 15, "lost"),
    ])
    save_de_results_to_db(tid, first)
    rows = elim_rows(tid)
    record(
        "initial save creates 3 elim rows",
        len(rows) == 3 and {r["opp"] for r in rows} == {
            f"{PREFIX}ALICE", f"{PREFIX}BOB", f"{PREFIX}CARLA",
        },
        f"rows={rows}",
    )
    alice_old_id = next(r["id"] for r in rows if r["opp"] == f"{PREFIX}ALICE")
    bob_old_id   = next(r["id"] for r in rows if r["opp"] == f"{PREFIX}BOB")
    carla_old_id = next(r["id"] for r in rows if r["opp"] == f"{PREFIX}CARLA")

    # 2. Attach videos: 2 to ALICE, 1 to BOB, 0 to CARLA -------------
    alice_v1 = add_bout_video("elim", alice_old_id, "bout-videos/elim_X_a1.mp4")
    alice_v2 = add_bout_video("elim", alice_old_id, "bout-videos/elim_X_a2.mp4")
    bob_v1   = add_bout_video("elim", bob_old_id,   "bout-videos/elim_X_b1.mp4")
    record(
        "attached 3 videos (2 ALICE, 1 BOB, 0 CARLA)",
        len(videos_for_elim(alice_old_id)) == 2
        and len(videos_for_elim(bob_old_id)) == 1
        and len(videos_for_elim(carla_old_id)) == 0,
    )

    # 3. Re-save SAME bracket (simulates fixing a missed round) ------
    # Add a Table-of-4 bout the first upload missed. Opponents + round
    # names for the existing bouts stay identical.
    second = bracket([
        ("T32",   f"{PREFIX}ALICE",     15, 3,  "won"),
        ("T16",   f"{PREFIX}BOB",       15, 10, "won"),
        ("T8",    f"{PREFIX}NEWBIE",    15, 12, "won"),  # was missing in first upload
        ("Final", f"{PREFIX}CARLA",     10, 15, "lost"),
    ])
    save_de_results_to_db(tid, second)
    new_rows = elim_rows(tid)
    record(
        "re-save produces 4 elim rows (added T8)",
        len(new_rows) == 4,
        f"rows={new_rows}",
    )

    # 4. Verify the delete+recreate actually ran (not an UPDATE in place)
    new_ids = {r["opp"]: r["id"] for r in new_rows}
    # On Postgres new ids would differ from old; SQLite reuses ids after
    # delete, so instead confirm that the delete left no trace by counting
    # rows and verifying we have the expected mix of opponents.
    record(
        "re-save left exactly one row per bracket opponent (no stale rows)",
        set(new_ids.keys()) == {
            f"{PREFIX}ALICE", f"{PREFIX}BOB",
            f"{PREFIX}NEWBIE", f"{PREFIX}CARLA",
        },
        f"opponents={set(new_ids.keys())}",
    )

    # 5. Videos were re-pointed to new elim ids ----------------------
    alice_new_id = new_ids[f"{PREFIX}ALICE"]
    bob_new_id   = new_ids[f"{PREFIX}BOB"]
    db = get_db()
    try:
        v1 = db.query(BoutVideo).filter_by(id=alice_v1).first()
        v2 = db.query(BoutVideo).filter_by(id=alice_v2).first()
        v3 = db.query(BoutVideo).filter_by(id=bob_v1).first()
    finally:
        db.close()
    record(
        "video attached to ALICE rewired to ALICE's new elim id",
        v1 and v1.bout_id == alice_new_id,
        f"v1.bout_id={v1 and v1.bout_id} expected={alice_new_id}",
    )
    record(
        "second video on ALICE also rewired",
        v2 and v2.bout_id == alice_new_id,
    )
    record(
        "video attached to BOB rewired to BOB's new elim id",
        v3 and v3.bout_id == bob_new_id,
    )

    # 6. Lookup via new id surfaces the preserved clips --------------
    record(
        "ALICE's new elim id now has 2 videos attached",
        len(videos_for_elim(alice_new_id)) == 2,
    )
    record(
        "BOB's new elim id now has 1 video attached",
        len(videos_for_elim(bob_new_id)) == 1,
    )

    # 7. Re-save with CARLA renamed → video gets orphaned (not crash)
    # Also attach a fresh video to BOB on the new id to make sure it survives.
    bob_v2 = add_bout_video("elim", bob_new_id, "bout-videos/elim_X_b2.mp4")
    third = bracket([
        ("T32",   f"{PREFIX}ALICE",         15, 3,  "won"),
        ("T16",   f"{PREFIX}BOB",           15, 10, "won"),
        ("T8",    f"{PREFIX}NEWBIE",        15, 12, "won"),
        ("Final", f"{PREFIX}CARLA RENAMED", 10, 15, "lost"),  # ← changed
    ])
    save_de_results_to_db(tid, third)
    db = get_db()
    try:
        third_rows = elim_rows(tid)
        new_ids_3 = {r["opp"]: r["id"] for r in third_rows}
        bob_v1_after = db.query(BoutVideo).filter_by(id=bob_v1).first()
        bob_v2_after = db.query(BoutVideo).filter_by(id=bob_v2).first()
        # CARLA had no videos originally, so no orphan here. Check BOB still OK.
    finally:
        db.close()
    bob_new_id_3 = new_ids_3.get(f"{PREFIX}BOB")
    record(
        "BOB's two videos still attached after a sibling bout was renamed",
        bob_v1_after and bob_v1_after.bout_id == bob_new_id_3
        and bob_v2_after and bob_v2_after.bout_id == bob_new_id_3,
        f"v1={bob_v1_after and bob_v1_after.bout_id} v2={bob_v2_after and bob_v2_after.bout_id} expected={bob_new_id_3}",
    )

    # 8. If we attach a video then re-save with that opponent gone,
    #    the video becomes an orphan (bout_id still points at an id that
    #    no longer exists). This is intentional — we don't delete the
    #    video so the user can recover or clean it up.
    newbie_id = new_ids_3[f"{PREFIX}NEWBIE"]
    newbie_v = add_bout_video("elim", newbie_id, "bout-videos/elim_X_n1.mp4")
    fourth = bracket([
        ("T32",   f"{PREFIX}ALICE",         15, 3,  "won"),
        ("T16",   f"{PREFIX}BOB",           15, 10, "won"),
        ("Final", f"{PREFIX}CARLA RENAMED", 10, 15, "lost"),  # NEWBIE dropped
    ])
    save_de_results_to_db(tid, fourth)
    db = get_db()
    try:
        orphaned = db.query(BoutVideo).filter_by(id=newbie_v).first()
        # NEWBIE was dropped from the bracket. The video row should still
        # exist (not auto-deleted) but no elim row for NEWBIE should remain.
        newbie_rows = db.query(EliminationRound).filter_by(
            tournament_id=tid,
            opponent_name=f"{PREFIX}NEWBIE",
        ).all()
    finally:
        db.close()
    record(
        "video for dropped opponent survives in BoutVideo as orphan",
        orphaned is not None and len(newbie_rows) == 0,
        f"orphan_exists={orphaned is not None} newbie_rows_remaining={len(newbie_rows)}",
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
