"""Fuzzy opponent matching for the Opponent Intelligence system.

Names and clubs in fencing data appear in many formats (LAST First vs First Last,
abbreviations, misspellings, "AFM" vs "Academy of Fencing Masters"). This module
exposes a tier-based matcher that plugs into `database.match_opponent` style flows.
"""

import re

from thefuzz import fuzz


def normalize(s):
    """Normalize a string for fuzzy comparison.

    Strips whitespace, lowercases, drops commas/periods, collapses internal
    whitespace to a single space. Returns an empty string for None.
    """
    if not s:
        return ''
    s = str(s).strip().lower()
    s = s.replace(',', ' ').replace('.', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _best_score(query, candidates):
    """Return the max of ratio / token_sort_ratio / partial_ratio across candidates."""
    query_norm = normalize(query)
    if not query_norm:
        return 0

    best = 0
    for candidate in candidates:
        cand_norm = normalize(candidate)
        if not cand_norm:
            continue
        r = fuzz.ratio(query_norm, cand_norm)
        tsr = fuzz.token_sort_ratio(query_norm, cand_norm)
        pr = fuzz.partial_ratio(query_norm, cand_norm)
        local = max(r, tsr, pr)
        if local > best:
            best = local
    return int(best)


def name_score(query, candidate_strings):
    """Score a query name against a list of candidate names.

    Returns an int 0-100: max of fuzz.ratio, fuzz.token_sort_ratio,
    fuzz.partial_ratio over every candidate.
    """
    return _best_score(query, candidate_strings)


def club_score(query, candidate_strings):
    """Score a query club against a list of candidate club strings.

    Same three-metric approach as `name_score`.
    """
    return _best_score(query, candidate_strings)


def _name_candidates(opp):
    """Build the candidate-name list for an opponent dict."""
    candidates = []
    if opp.get('canonical_name'):
        candidates.append(opp['canonical_name'])
    # Also score against "First Last" to catch natural-order queries
    first = opp.get('first_name')
    last = opp.get('last_name')
    if first and last:
        candidates.append(f'{first} {last}')
        candidates.append(f'{last} {first}')
    aliases = opp.get('name_aliases') or []
    if isinstance(aliases, list):
        candidates.extend([a for a in aliases if a])
    return candidates


def _club_candidates(opp):
    """Build the candidate-club list for an opponent dict."""
    candidates = []
    if opp.get('club'):
        candidates.append(opp['club'])
    aliases = opp.get('club_aliases') or []
    if isinstance(aliases, list):
        candidates.extend([a for a in aliases if a])
    return candidates


def _club_empty(value):
    return value is None or normalize(value) == ''


def match_opponent(query_name, query_club, all_opponents):
    """Match a (name, club) query against a list of opponent dicts.

    Implements the four-tier confidence system from the plan. Each opponent dict
    must already contain deserialized `name_aliases` and `club_aliases` lists.

    Returns a dict:
        {
            'tier': 1 | 2 | 3 | 4 | None,
            'confidence': 'exact' | 'high' | 'medium' | 'low' | 'none',
            'name_score': int,
            'club_score': int,
            'opponent': {...} | None,
            'action': 'auto_link' | 'confirm' | 'create_new',
        }
    """
    query_name_norm = normalize(query_name)
    query_club_norm = normalize(query_club)
    query_club_empty = _club_empty(query_club)

    # Collect best candidate per tier so we can pick the strongest tier overall.
    best_t1 = None
    best_t2 = None
    best_t3 = None
    best_t4 = None

    for opp in all_opponents:
        name_cands = _name_candidates(opp)
        club_cands = _club_candidates(opp)

        # Exact checks compare against the opponent's canonical name and
        # primary club only; alias hits are intentionally a fuzzy-tier concern.
        canonical_norm = normalize(opp.get('canonical_name'))
        primary_club_norm = normalize(opp.get('club'))
        name_exact = bool(query_name_norm) and canonical_norm == query_name_norm
        club_exact = bool(query_club_norm) and primary_club_norm == query_club_norm

        n_score = name_score(query_name, name_cands)
        c_score = club_score(query_club, club_cands)

        opp_club_empty = not any(not _club_empty(c) for c in club_cands)

        # Tier 1: exact name AND exact club (both non-empty).
        if name_exact and club_exact:
            if best_t1 is None or n_score > best_t1['name_score']:
                best_t1 = {
                    'tier': 1,
                    'confidence': 'exact',
                    'name_score': n_score,
                    'club_score': c_score,
                    'opponent': opp,
                    'action': 'auto_link',
                }
            continue

        # Tier 2: fuzzy name >= 85 AND exact club match.
        if n_score >= 85 and club_exact:
            if best_t2 is None or n_score > best_t2['name_score']:
                best_t2 = {
                    'tier': 2,
                    'confidence': 'high',
                    'name_score': n_score,
                    'club_score': c_score,
                    'opponent': opp,
                    'action': 'auto_link',
                }
            continue

        # Tier 3: fuzzy name >= 70 AND fuzzy club >= 70 (both sides have a club).
        if n_score >= 70 and c_score >= 70 and not query_club_empty and not opp_club_empty:
            if best_t3 is None or (n_score + c_score) > (best_t3['name_score'] + best_t3['club_score']):
                best_t3 = {
                    'tier': 3,
                    'confidence': 'medium',
                    'name_score': n_score,
                    'club_score': c_score,
                    'opponent': opp,
                    'action': 'confirm',
                }
            continue

        # Tier 4: fuzzy name >= 80 AND one side's club is missing/empty.
        if n_score >= 80 and (query_club_empty or opp_club_empty):
            if best_t4 is None or n_score > best_t4['name_score']:
                best_t4 = {
                    'tier': 4,
                    'confidence': 'low',
                    'name_score': n_score,
                    'club_score': c_score,
                    'opponent': opp,
                    'action': 'confirm',
                }
            continue

    for candidate in (best_t1, best_t2, best_t3, best_t4):
        if candidate is not None:
            return candidate

    return {
        'tier': None,
        'confidence': 'none',
        'name_score': 0,
        'club_score': 0,
        'opponent': None,
        'action': 'create_new',
    }
