"""Diagnose why an opponent's head-to-head is missing bouts.

Usage:
    python diagnose_opponent.py "USHAKOV Richard"
    python diagnose_opponent.py 42          # by opponent ID
"""

import sys
from database import (
    get_db, Opponent, BoutRecord, EliminationRound, PoolBout, PoolRound
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python diagnose_opponent.py <name or ID>")
        return

    query = sys.argv[1]
    db = get_db()
    try:
        # Find opponent(s)
        if query.isdigit():
            opps = db.query(Opponent).filter_by(id=int(query)).all()
        else:
            opps = db.query(Opponent).filter(
                Opponent.canonical_name.ilike(f'%{query}%')
            ).all()

        if not opps:
            print(f"No opponents found for '{query}'")
            return

        print(f"=== Found {len(opps)} opponent(s) matching '{query}' ===\n")
        for o in opps:
            print(f"  ID={o.id}  name={o.canonical_name!r}  club={o.club!r}")

        for o in opps:
            print(f"\n--- Opponent ID={o.id}: {o.canonical_name} ({o.club}) ---")

            # BoutRecords linked to this opponent
            records = db.query(BoutRecord).filter_by(opponent_id=o.id).all()
            print(f"  BoutRecords: {len(records)}")
            for r in records:
                kind = 'pool' if r.pool_bout_id else 'elim' if r.elimination_round_id else '???'
                print(f"    id={r.id} kind={kind} pool_bout_id={r.pool_bout_id} "
                      f"elim_id={r.elimination_round_id} "
                      f"score={r.score_for}-{r.score_against} result={r.result} "
                      f"tournament={r.tournament_name}")

        # Check for EliminationRound rows matching this name
        print(f"\n=== EliminationRound rows matching '{query}' ===")
        elims = db.query(EliminationRound).filter(
            EliminationRound.opponent_name.ilike(f'%{query}%')
        ).all()
        print(f"  Found {len(elims)} DE bout(s)")
        for e in elims:
            # Check if there's a BoutRecord for this elim
            br = db.query(BoutRecord).filter_by(elimination_round_id=e.id).first()
            linked_to = f"→ opponent {br.opponent_id}" if br else "→ NO BoutRecord"
            print(f"    elim_id={e.id} tournament_id={e.tournament_id} "
                  f"opponent={e.opponent_name!r} club={e.opponent_club!r} "
                  f"score={e.score_for}-{e.score_against} result={e.result} "
                  f"{linked_to}")

        # Check for PoolBout rows matching this name
        print(f"\n=== PoolBout rows matching '{query}' ===")
        pools = db.query(PoolBout).filter(
            PoolBout.opponent_name.ilike(f'%{query}%')
        ).all()
        print(f"  Found {len(pools)} pool bout(s)")
        for p in pools:
            br = db.query(BoutRecord).filter_by(pool_bout_id=p.id).first()
            linked_to = f"→ opponent {br.opponent_id}" if br else "→ NO BoutRecord"
            pr = db.query(PoolRound).filter_by(id=p.pool_round_id).first()
            tid = pr.tournament_id if pr else '?'
            print(f"    bout_id={p.id} tournament_id={tid} "
                  f"opponent={p.opponent_name!r} club={p.opponent_club!r} "
                  f"score={p.score_for}-{p.score_against} result={p.result} "
                  f"{linked_to}")

        # Check ScoutBout links
        print(f"\n=== ScoutBout rows matching '{query}' ===")
        from database import ScoutBout
        scout_a = db.query(ScoutBout).filter(
            ScoutBout.fencer_a_name.ilike(f'%{query}%')
        ).all()
        scout_b = db.query(ScoutBout).filter(
            ScoutBout.fencer_b_name.ilike(f'%{query}%')
        ).all()
        all_scout = {s.id: s for s in scout_a + scout_b}.values()
        print(f"  Found {len(list(all_scout))} scout bout(s)")
        for s in all_scout:
            print(f"    id={s.id} a_name={s.fencer_a_name!r} a_id={s.fencer_a_id} "
                  f"b_name={s.fencer_b_name!r} b_id={s.fencer_b_id} "
                  f"tournament={s.tournament_name!r} round={s.round_name!r}")

    finally:
        db.close()


if __name__ == '__main__':
    main()
