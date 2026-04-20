#!/usr/bin/env python3
"""One-shot backfill: link every existing PoolBout / EliminationRound row to an
Opponent and record it as a BoutRecord.

Run from the repo root:
    python3 backfill_bout_records.py

- Skips any bout that already has a BoutRecord (idempotent — re-running does
  nothing once everything is linked).
- Safe to ctrl-C mid-run (each bout is synced in its own transaction via
  `sync_bout_to_opponent`).
- Exits 0 on success; nonzero on any unhandled exception.
"""

import sys
import traceback

from database import (
    BoutRecord,
    EliminationRound,
    PoolBout,
    PoolRound,
    Tournament,
    get_db,
    sync_bout_to_opponent,
)


def _existing_pool_bout_record_ids(db):
    """Return the set of PoolBout ids that already have a BoutRecord."""
    rows = db.query(BoutRecord.pool_bout_id).filter(
        BoutRecord.pool_bout_id.isnot(None)
    ).all()
    return {r[0] for r in rows if r[0] is not None}


def _existing_elim_record_ids(db):
    """Return the set of EliminationRound ids that already have a BoutRecord."""
    rows = db.query(BoutRecord.elimination_round_id).filter(
        BoutRecord.elimination_round_id.isnot(None)
    ).all()
    return {r[0] for r in rows if r[0] is not None}


def _tournament_context_for(db, tournament_id, tournament_cache):
    """Resolve a tournament context dict with a small in-run cache."""
    if tournament_id in tournament_cache:
        return tournament_cache[tournament_id]
    ctx = {'tournament_id': tournament_id, 'tournament_name': None, 'tournament_date': None}
    if tournament_id:
        t = db.query(Tournament).filter_by(id=tournament_id).first()
        if t:
            ctx['tournament_name'] = t.name
            ctx['tournament_date'] = t.date
    tournament_cache[tournament_id] = ctx
    return ctx


def _format_summary(kind, bout_dict, summary):
    name = bout_dict.get('opponent_name') or '(no name)'
    action = summary.get('action') or 'skipped'
    opp_id = summary.get('opponent_id')
    tier = summary.get('tier')
    if action == 'auto_link':
        return f"SYNCED {kind} {name} → opponent {opp_id} (auto_link, tier {tier})"
    if action == 'stub_created':
        return f"STUB   {kind} {name} → new opponent {opp_id}"
    if summary.get('error'):
        return f"SKIP   {kind} {name}: {summary['error']}"
    return f"SKIP   {kind} {name} (no opponent_name)"


def backfill():
    totals = {'total': 0, 'auto_link': 0, 'stub_created': 0, 'skipped': 0, 'errors': 0}
    tournament_cache = {}

    db = get_db()
    try:
        done_pool_ids = _existing_pool_bout_record_ids(db)
        done_elim_ids = _existing_elim_record_ids(db)

        pool_rows = (
            db.query(PoolBout, PoolRound.tournament_id)
            .join(PoolRound, PoolBout.pool_round_id == PoolRound.id)
            .order_by(PoolBout.id)
            .all()
        )

        elim_rows = (
            db.query(EliminationRound)
            .order_by(EliminationRound.id)
            .all()
        )
    finally:
        db.close()

    # --- Pool bouts ---
    for pool_bout, tournament_id in pool_rows:
        if pool_bout.id in done_pool_ids:
            continue
        totals['total'] += 1
        # Fresh session for each tournament context lookup — cheap, and keeps
        # the operation safely interruptible.
        db = get_db()
        try:
            ctx = _tournament_context_for(db, tournament_id, tournament_cache)
        finally:
            db.close()

        bout_data = {
            'opponent_name': pool_bout.opponent_name,
            'opponent_club': pool_bout.opponent_club,
            'score_for': pool_bout.score_for,
            'score_against': pool_bout.score_against,
            'result': pool_bout.result,
            'pool_bout_id': pool_bout.id,
        }
        summary = sync_bout_to_opponent('pool', bout_data, ctx)
        action = summary.get('action') or 'skipped'
        totals[action] = totals.get(action, 0) + 1
        if summary.get('error'):
            totals['errors'] += 1
        print(_format_summary('pool', bout_data, summary))

    # --- Elimination rounds ---
    for elim in elim_rows:
        if elim.id in done_elim_ids:
            continue
        totals['total'] += 1
        db = get_db()
        try:
            ctx = _tournament_context_for(db, elim.tournament_id, tournament_cache)
        finally:
            db.close()

        bout_data = {
            'opponent_name': elim.opponent_name,
            'opponent_club': elim.opponent_club,
            'score_for': elim.score_for,
            'score_against': elim.score_against,
            'result': elim.result,
            'elimination_round_id': elim.id,
        }
        summary = sync_bout_to_opponent('elim', bout_data, ctx)
        action = summary.get('action') or 'skipped'
        totals[action] = totals.get(action, 0) + 1
        if summary.get('error'):
            totals['errors'] += 1
        print(_format_summary('elim', bout_data, summary))

    print()
    print("=== Backfill complete ===")
    print(f"  Bouts processed:  {totals['total']}")
    print(f"  Auto-linked:      {totals.get('auto_link', 0)}")
    print(f"  Stubs created:    {totals.get('stub_created', 0)}")
    print(f"  Skipped:          {totals.get('skipped', 0)}")
    if totals['errors']:
        print(f"  Errors logged:    {totals['errors']}")


def main():
    try:
        backfill()
        return 0
    except KeyboardInterrupt:
        print("\n[interrupted] partial progress is preserved — re-run to resume.")
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
