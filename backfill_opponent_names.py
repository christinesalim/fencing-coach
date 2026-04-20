#!/usr/bin/env python3
"""One-shot: populate first_name/last_name for existing opponents that only have canonical_name.

Run once in the Render shell after deploy:

    python3 backfill_opponent_names.py

Idempotent — re-running after completion makes no changes.
"""
import sys
from database import get_db, Opponent, _parse_usfa_name


def backfill():
    db = get_db()
    try:
        rows = db.query(Opponent).filter(
            (Opponent.first_name.is_(None)) | (Opponent.first_name == ''),
            (Opponent.last_name.is_(None)) | (Opponent.last_name == ''),
        ).all()
        updated = 0
        skipped = 0
        for opp in rows:
            first, last = _parse_usfa_name(opp.canonical_name)
            if first or last:
                opp.first_name = first
                opp.last_name = last
                updated += 1
                print(f'  [{opp.id}] {opp.canonical_name!r} -> first={first!r} last={last!r}')
            else:
                skipped += 1
        db.commit()
        print(f'\nDone: {updated} updated, {skipped} couldn\'t be parsed, {len(rows)} candidates')
        return 0
    except Exception as e:
        db.rollback()
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(backfill())
