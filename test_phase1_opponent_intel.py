"""Phase 1 smoke test for the Opponent Intelligence system.

Exercises models, helper functions, and fuzzy matching end-to-end against the
local SQLite database. Prints PASS/FAIL per scenario and exits non-zero if any
scenario fails. Idempotent — can be re-run safely because it cleans up all test
records (identified by the `TEST_OI_` prefix) before it exits.
"""

import sys
import traceback

TEST_PREFIX = 'TEST_OI_'

results = []


def record(name, ok, detail=''):
    status = 'PASS' if ok else 'FAIL'
    results.append((name, ok, detail))
    line = f'[{status}] {name}'
    if detail:
        line += f' -- {detail}'
    print(line)


def cleanup(db, Opponent, OpponentTacticalNote, BoutRecord):
    """Remove every TEST_OI_* record the suite may have left behind."""
    try:
        opps = db.query(Opponent).filter(
            Opponent.canonical_name.like(f'{TEST_PREFIX}%')
        ).all()
        # Also clean opponents whose last_name starts with TEST_PREFIX (defensive).
        opps_by_last = db.query(Opponent).filter(
            Opponent.last_name.like(f'{TEST_PREFIX}%')
        ).all()
        seen = set()
        for opp in list(opps) + list(opps_by_last):
            if opp.id in seen:
                continue
            seen.add(opp.id)
            db.query(OpponentTacticalNote).filter_by(opponent_id=opp.id).delete()
            db.query(BoutRecord).filter_by(opponent_id=opp.id).delete()
            db.delete(opp)
        db.commit()
    except Exception:
        db.rollback()
        raise


def main():
    # 1. Import check
    try:
        from database import (
            Opponent,
            OpponentTacticalNote,
            BoutRecord,
            create_opponent,
            match_opponent,
            lookup_opponents_by_names,
            get_db,
            get_opponent,
            get_tactical_notes,
            get_head_to_head,
            add_tactical_note,
            add_bout_record,
            delete_opponent,
        )
        record('Scenario 1: Imports', True,
               'Opponent, OpponentTacticalNote, BoutRecord, create_opponent, match_opponent, lookup_opponents_by_names imported')
    except Exception as e:
        record('Scenario 1: Imports', False, f'{type(e).__name__}: {e}')
        print('Cannot continue without imports; bailing.')
        sys.exit(1)

    # Pre-clean anything left from a prior crashed run.
    cleanup_db = get_db()
    try:
        cleanup(cleanup_db, Opponent, OpponentTacticalNote, BoutRecord)
    finally:
        cleanup_db.close()

    created_opp_id = None

    try:
        # 2. Create opponent, verify canonical_name synthesis
        opp = create_opponent({
            'first_name': f'{TEST_PREFIX}Dylan',
            'last_name': f'{TEST_PREFIX}JI',
            'club': f'{TEST_PREFIX}AFM',
            'club_aliases': [f'{TEST_PREFIX}Academy Fencing Masters'],
            'handedness': 'right',
            'primary_style': 'aggressive',
        })
        created_opp_id = opp['id']
        expected_canonical = f'{TEST_PREFIX}JI'.upper() + f' {TEST_PREFIX}Dylan'
        ok = opp['canonical_name'] == expected_canonical
        record(
            'Scenario 2: canonical_name synthesized as "LASTNAME Firstname"',
            ok,
            f'got canonical_name={opp["canonical_name"]!r}, expected={expected_canonical!r}',
        )

        # 3. Tactical note with confidence = validated / (validated + invalidated)
        note = add_tactical_note(created_opp_id, {
            'category': 'weakness',
            'observation': f'{TEST_PREFIX} slow on retreat',
            'times_validated': 2,
            'times_invalidated': 0,
        })
        notes = get_tactical_notes(created_opp_id)
        found = next((n for n in notes if n['id'] == note['id']), None)
        ok = (
            found is not None
            and found['confidence'] == 1.0
            and found['times_validated'] == 2
            and found['times_invalidated'] == 0
        )
        record(
            'Scenario 3: tactical note confidence == 1.0 when 2/0',
            ok,
            f'confidence={found["confidence"] if found else None!r}',
        )

        # 4. Two bout records -> get_head_to_head aggregates + sorts newest-first
        add_bout_record(created_opp_id, {
            'tournament_name': f'{TEST_PREFIX}Early Tournament',
            'tournament_date': '2025-09-01',
            'bout_type': 'pool',
            'score_for': 5,
            'score_against': 3,
            'result': 'won',
        })
        add_bout_record(created_opp_id, {
            'tournament_name': f'{TEST_PREFIX}Later Tournament',
            'tournament_date': '2026-02-15',
            'bout_type': 'elimination',
            'score_for': 2,
            'score_against': 5,
            'result': 'lost',
        })
        h2h = get_head_to_head(created_opp_id)
        ok = (
            h2h['wins'] == 1
            and h2h['losses'] == 1
            and h2h['touches_for'] == 7
            and h2h['touches_against'] == 8
            and len(h2h['bouts']) == 2
            and h2h['bouts'][0]['tournament_date'] == '2026-02-15'  # newest first
            and h2h['bouts'][1]['tournament_date'] == '2025-09-01'
        )
        record(
            'Scenario 4: head-to-head totals + newest-first sort',
            ok,
            (
                f'wins={h2h["wins"]}, losses={h2h["losses"]}, '
                f'touches_for={h2h["touches_for"]}, touches_against={h2h["touches_against"]}, '
                f'dates=[{h2h["bouts"][0]["tournament_date"]}, {h2h["bouts"][1]["tournament_date"]}]'
            ),
        )

        # 5. Fuzzy matching tiers
        # Build the opponent dict the matcher expects (get_opponent already
        # deserializes name_aliases / club_aliases).
        full_opp = get_opponent(created_opp_id)
        all_opps = [full_opp]

        # 5a: exact normalized match on name AND club -> tier 1
        m1 = match_opponent(expected_canonical, f'{TEST_PREFIX}AFM', all_opps)
        ok = m1['tier'] == 1 and m1['confidence'] == 'exact'
        record(
            'Scenario 5a: exact (name, club) -> tier 1',
            ok,
            f'tier={m1["tier"]}, confidence={m1["confidence"]}, name_score={m1["name_score"]}, club_score={m1["club_score"]}',
        )

        # 5b: abbreviated/reordered name with exact club -> tier 2
        m2 = match_opponent(f'{TEST_PREFIX}JI, D.', f'{TEST_PREFIX}AFM', all_opps)
        ok = m2['tier'] == 2 and m2['confidence'] == 'high'
        record(
            'Scenario 5b: ("JI, D.", exact club) -> tier 2',
            ok,
            f'tier={m2["tier"]}, name_score={m2["name_score"]}, club_score={m2["club_score"]}',
        )

        # 5c: canonical name with a fuzzy-matching club alias -> tier 3
        m3 = match_opponent(
            expected_canonical,
            f'{TEST_PREFIX}Academy Fencing Masters',
            all_opps,
        )
        ok = m3['tier'] == 3 and m3['confidence'] == 'medium'
        record(
            'Scenario 5c: (exact name, club alias full-match) -> tier 3',
            ok,
            f'tier={m3["tier"]}, name_score={m3["name_score"]}, club_score={m3["club_score"]}',
        )

        # 5d: nothing close -> no match
        m4 = match_opponent(
            f'{TEST_PREFIX}TOTALLY UNKNOWN Person',
            f'{TEST_PREFIX}Random Club',
            all_opps,
        )
        ok = m4['tier'] is None and m4['action'] == 'create_new'
        record(
            'Scenario 5d: unrelated query -> tier None, action create_new',
            ok,
            f'tier={m4["tier"]}, action={m4["action"]}',
        )

        # 6. Batch lookup returns entries with the expected shape
        batch = lookup_opponents_by_names([
            expected_canonical,
            f'{TEST_PREFIX}UNKNOWN Person',
        ])
        ok = (
            len(batch) == 2
            and batch[0]['query_name'] == expected_canonical
            and batch[0]['match']['opponent'] is not None
            and batch[1]['query_name'] == f'{TEST_PREFIX}UNKNOWN Person'
            and batch[1]['match']['opponent'] is None
            and batch[1]['match']['action'] == 'create_new'
        )
        record(
            'Scenario 6: lookup_opponents_by_names shape + results',
            ok,
            f'len={len(batch)}, first_match_tier={batch[0]["match"]["tier"]}, second_match_action={batch[1]["match"]["action"]}',
        )

        # 7. Delete cascade: opponent, notes, and bout records all gone
        deleted = delete_opponent(created_opp_id)
        db = get_db()
        try:
            opp_rows = db.query(Opponent).filter_by(id=created_opp_id).count()
            note_rows = db.query(OpponentTacticalNote).filter_by(opponent_id=created_opp_id).count()
            bout_rows = db.query(BoutRecord).filter_by(opponent_id=created_opp_id).count()
        finally:
            db.close()
        ok = deleted is True and opp_rows == 0 and note_rows == 0 and bout_rows == 0
        record(
            'Scenario 7: delete_opponent cascades to notes + bout records',
            ok,
            f'deleted={deleted}, opp_rows={opp_rows}, note_rows={note_rows}, bout_rows={bout_rows}',
        )
        created_opp_id = None  # already gone

    except Exception as e:
        record('EXCEPTION during scenarios 2-7', False, traceback.format_exc())
    finally:
        # 8. Cleanup: always remove test data so the suite is re-runnable.
        try:
            db = get_db()
            cleanup(db, Opponent, OpponentTacticalNote, BoutRecord)
            remaining = db.query(Opponent).filter(
                Opponent.canonical_name.like(f'{TEST_PREFIX}%')
            ).count()
            db.close()
            record(
                'Scenario 8: cleanup leaves no TEST_OI_* rows',
                remaining == 0,
                f'remaining opponent rows={remaining}',
            )
        except Exception as e:
            record('Scenario 8: cleanup', False, f'{type(e).__name__}: {e}')

    # Tally
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print('')
    print(f'Total: {passed} PASS, {failed} FAIL')
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
