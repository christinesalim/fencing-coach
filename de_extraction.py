"""DE bracket photo extraction using Claude Vision API."""

import os
import json
import base64
from pathlib import Path
import anthropic


_claude_client = None


def get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _claude_client


# Mapping between round names and the number of fencers in that round.
# "Table of N" rounds map to N. Semi-Finals = 4 fencers, Finals = 2.
_ROUND_TO_SIZE = {
    'finals': 2, 'final': 2, 'table of 2': 2,
    'semi-finals': 4, 'semifinals': 4, 'semis': 4, 'table of 4': 4,
    'quarterfinals': 8, 'quarter-finals': 8, 'quarters': 8, 'table of 8': 8,
    'table of 16': 16,
    'table of 32': 32,
    'table of 64': 64,
    'table of 128': 128,
    'table of 256': 256,
}

# Canonical round name for each round size — used after normalization
_SIZE_TO_ROUND = {
    2: 'Finals',
    4: 'Semi-Finals',
    8: 'Table of 8',
    16: 'Table of 16',
    32: 'Table of 32',
    64: 'Table of 64',
    128: 'Table of 128',
    256: 'Table of 256',
}


def _round_size(round_name):
    """Return the number of fencers in a round, or None if unknown."""
    if not round_name:
        return None
    return _ROUND_TO_SIZE.get(str(round_name).strip().lower())


def _canonical_round_name(round_name):
    """Normalize aliases (e.g., 'Table of 4' → 'Semi-Finals')."""
    size = _round_size(round_name)
    return _SIZE_TO_ROUND.get(size, round_name)


def _placement_for_eliminated_in(round_size):
    """Final placement label for a fencer eliminated in a given round."""
    if round_size is None:
        return 'Unknown'
    return {2: '2nd', 4: '3T'}.get(round_size, f'Top {round_size}')


def _derive_final_placement(path, bracket_size):
    """Compute the final_placement_range from the fencer's path.

    Lost in semi → '3T'. Lost in finals → '2nd'. Won finals → '1st'.
    Lost in earlier round → 'Top N' where N is the size of that round.
    """
    if not path:
        return 'Unknown' if not bracket_size else f'Top {bracket_size}'
    last = path[-1]
    last_round_size = _round_size(last.get('round_name'))
    result = (last.get('result') or '').lower()
    if last_round_size == 2:  # Finals
        return '1st' if result == 'won' else '2nd'
    if result == 'lost':
        return _placement_for_eliminated_in(last_round_size)
    # Won the last bout shown but didn't reach finals — they advanced past it
    if last_round_size and last_round_size > 2:
        return _placement_for_eliminated_in(last_round_size // 2)
    return 'Unknown'


def _maybe_prepend_bye_rounds(path, bracket_size, seed):
    """If bracket_size implies earlier rounds and the fencer's first listed round
    is later, prepend BYE rows. Only safe for top-half seeds (≤ bracket_size/2)
    where a BYE is the standard tableau pairing.
    """
    if not bracket_size or not path:
        return path
    first_round_size = _round_size(path[0].get('round_name'))
    if not first_round_size or first_round_size >= bracket_size:
        return path
    if seed is None or seed > bracket_size // 2:
        # Without a top-half seed we can't safely assume earlier byes.
        return path
    extras = []
    size = bracket_size
    while size > first_round_size:
        extras.append({
            'round_name': _SIZE_TO_ROUND.get(size, f'Table of {size}'),
            'opponent_name': 'BYE',
            'opponent_seed': None,
            'opponent_club': None,
            'score_for': None,
            'score_against': None,
            'result': 'won',
        })
        size //= 2
    return extras + list(path)


def _normalize_path(path):
    """Apply round-name canonicalization to every bout in a path list."""
    if not path:
        return path
    out = []
    for bout in path:
        b = dict(bout)
        b['round_name'] = _canonical_round_name(b.get('round_name'))
        out.append(b)
    return out


def _parse_json_response(text):
    """Parse JSON from Claude response, handling markdown code blocks."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())


def _get_media_type(image_path):
    """Determine media type from file extension."""
    ext = Path(image_path).suffix.lower()
    if ext in ('.jpg', '.jpeg'):
        return "image/jpeg"
    elif ext == '.png':
        return "image/png"
    elif ext == '.webp':
        return "image/webp"
    else:
        raise ValueError(f"Unsupported image format: {ext}")


def extract_de_bracket_from_photo(image_path, our_fencer_name="SALIM Ethan"):
    """Extract DE bracket data from a single screenshot using Claude Vision."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    media_type = _get_media_type(image_path)

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": f"""You are analyzing a screenshot of a fencing Direct Elimination (DE) bracket from FencingTimeLive.

YOUR TASK: Find "{our_fencer_name}" in the bracket and trace ONLY their path through the rounds. Do NOT extract every bout — just this fencer's bouts.

HOW TO READ THE BRACKET:
- The bracket flows LEFT to RIGHT. Each column has a HEADER (e.g., "Table of 16", "Table of 8", "Semi-Finals", "Finals").
- Each bout is a PAIR of two fencers stacked vertically, connected by bracket lines.
- The WINNER advances RIGHT to the next column, where they are paired with a NEW opponent.
- Numbers in parentheses like (4) or (36) are SEEDS from pool ranking.
- Scores appear as "15-7" etc. DE bouts go to 15 touches.
- "BYE" means automatic advance, no bout fenced.

BRACKET SIZE — IMPORTANT
- The bracket size is the size of the LEFTMOST column visible. Read its header text literally.
  - "Table of 16" → bracket_size = 16
  - "Table of 8"  → bracket_size = 8
  - "Semi-Finals" (with no earlier column) → bracket_size = 4 (the visible mini-bracket only)
  - "Finals"     → bracket_size = 2
- Common values: 4, 8, 16, 32, 64, 128, 256. Whatever the header says.
- DO NOT round up or guess — if the leftmost column says "Table of 16", return 16, not 32.

STEP BY STEP:
1. Find "{our_fencer_name}" in the leftmost column (first round shown).
2. Identify who they are paired with. That is their first opponent in this view.
3. Read the score. Did our fencer win or lose?
4. If they WON, follow the bracket line RIGHT to the next column. Find who they are now paired with — that is a DIFFERENT person, their next opponent.
5. Repeat until they lose, the bracket ends, or no more rounds are visible.

ROUND NAMES — return them exactly as they appear in the column header:
- "Table of 16", "Table of 8", "Semi-Finals", "Finals" (preserve the literal header text).
- If a column shows only the round structure (e.g., a 4-fencer mini-bracket) without a "Table of N" label, use "Semi-Finals" / "Finals" as appropriate.

CRITICAL VALIDATION:
- Each round MUST have a DIFFERENT opponent. If you wrote the same opponent name twice, you misread the bracket — go back and re-trace the lines.
- The opponent in the next round is the WINNER of a different earlier bout, NOT the same person from the previous round.
- If you see "BYE" as the opponent in any round, record it as `"opponent_name": "BYE"` with null scores and `result: "won"`.

Return JSON:
{{
  "bracket_metadata": {{
    "leftmost_column_header": "<exact header text from the leftmost column>",
    "bracket_size": <integer — same number as in the leftmost header>,
    "software_detected": "FencingTimeLive" | "unknown",
    "visible_rounds": ["<header text>", ...]
  }},
  "our_fencer": {{
    "name": "<exact name as shown>",
    "seed": <number or null>,
    "club": "<club or null>"
  }},
  "bouts": [
    {{
      "round_name": "<exact column header>",
      "opponent_name": "<LAST First or BYE>",
      "opponent_club": "<club or null>",
      "opponent_seed": <number or null>,
      "score_for": <our fencer's score or null>,
      "score_against": <opponent's score or null>,
      "result": "won" | "lost"
    }}
  ],
  "final_placement_range": "<e.g., Top 16, Top 8, Top 4, 3T, 2nd, 1st, or Unknown>",
  "other_visible_bouts": <count of other bouts visible but not extracted>
}}

If "{our_fencer_name}" is not visible in this screenshot, return:
{{"our_fencer": null, "error": "Fencer not found in this screenshot"}}"""
                }
            ],
        }],
    )

    return _parse_json_response(message.content[0].text)


def _dedup_fencer_path(bouts):
    """Post-processing safety net: remove duplicate opponents in consecutive rounds."""
    if not bouts:
        return bouts

    seen_opponents = set()
    deduped = []
    for bout in bouts:
        opponent = bout.get('opponent_name', '').strip().upper()
        if opponent and opponent != 'BYE' and opponent in seen_opponents:
            # Same opponent in consecutive rounds = extraction error, skip it
            continue
        if opponent and opponent != 'BYE':
            seen_opponents.add(opponent)
        deduped.append(bout)
    return deduped


def _bout_has_score(bout):
    return bout.get('score_for') is not None and bout.get('score_against') is not None


def _better_bout(existing, candidate):
    """Pick the better of two bouts for the same round. Prefer non-null scores
    and longer (more complete) opponent club strings."""
    if existing is None:
        return candidate
    # Prefer the entry with scores filled in
    if _bout_has_score(candidate) and not _bout_has_score(existing):
        return candidate
    if _bout_has_score(existing) and not _bout_has_score(candidate):
        return existing
    # Both filled or both null — prefer the longer opponent_club (more complete affiliation)
    e_club = (existing.get('opponent_club') or '')
    c_club = (candidate.get('opponent_club') or '')
    if len(c_club) > len(e_club):
        merged = dict(existing)
        merged['opponent_club'] = c_club
        return merged
    return existing


def merge_de_bracket_extractions(extractions, our_fencer_name):
    """Deterministic Python merge of per-image extractions into one fencer path.

    Combines bouts across photos by canonical round name, takes the max
    bracket_size as authoritative, normalizes round-name aliases (Table of 4 →
    Semi-Finals), prepends BYE rows for top-half seeds when an earlier round is
    implied by bracket_size, and derives final_placement_range from the path.
    """
    valid = [e for e in extractions if e.get('our_fencer')]
    warnings = []
    if not valid:
        return {
            "tournament_bracket": {"bracket_size": 0, "total_bouts_extracted": 0, "completeness": 0, "rounds": {}},
            "our_fencer": {"name": our_fencer_name, "seed": None, "path": [], "final_placement_range": "Unknown"},
            "warnings": ["Fencer not found in any screenshot"],
            "duplicate_bouts_removed": 0,
        }

    # Canonical bracket size = max across all photos. Each photo reports the
    # size of its leftmost column; the largest of those is the true bracket
    # size (later photos can't shrink it).
    sizes = []
    for ext in valid:
        meta = ext.get('bracket_metadata') or {}
        size = meta.get('bracket_size') or meta.get('estimated_bracket_size')
        if size:
            sizes.append(int(size))
        else:
            # Fall back to inferring from the visible round names
            for rn in (meta.get('visible_rounds') or []):
                rs = _round_size(rn)
                if rs:
                    sizes.append(rs)
    bracket_size = max(sizes) if sizes else 0

    if len(set(sizes)) > 1:
        warnings.append(
            f"Photos disagree on bracket size ({sorted(set(sizes))}); using {bracket_size} (largest)"
        )

    # Canonical fencer info — prefer entries with seed and club populated
    fencer_name = our_fencer_name
    fencer_seed = None
    fencer_club = None
    for ext in valid:
        f = ext.get('our_fencer') or {}
        if f.get('name'):
            fencer_name = f['name']
        if f.get('seed') is not None and fencer_seed is None:
            fencer_seed = f['seed']
        c = (f.get('club') or '')
        if c and len(c) > len(fencer_club or ''):
            fencer_club = c

    # Combine bouts per canonical round, picking the most complete entry for each
    by_round = {}
    total_input_bouts = 0
    for ext in valid:
        for bout in (ext.get('bouts') or []):
            total_input_bouts += 1
            cname = _canonical_round_name(bout.get('round_name'))
            if not cname:
                continue
            normalized = dict(bout)
            normalized['round_name'] = cname
            by_round[cname] = _better_bout(by_round.get(cname), normalized)

    # Order rounds by descending size (Table of 64 → ... → Finals)
    ordered = sorted(by_round.values(), key=lambda b: -(_round_size(b.get('round_name')) or 0))

    # Drop accidental duplicate opponents in consecutive rounds (vision misreads)
    deduped = _dedup_fencer_path(ordered)
    duplicates_removed = len(ordered) - len(deduped)

    # If bracket_size implies earlier rounds and the fencer's first listed round
    # is later, prepend BYEs (only when seed places them in the top half).
    final_path = _maybe_prepend_bye_rounds(deduped, bracket_size, fencer_seed)
    if len(final_path) > len(deduped):
        warnings.append(
            f"Inferred {len(final_path) - len(deduped)} BYE round(s) for top-seeded fencer"
        )

    final_placement = _derive_final_placement(final_path, bracket_size)

    return {
        "tournament_bracket": {
            "bracket_size": bracket_size,
            "total_bouts_extracted": len(final_path),
            "completeness": 0,
            "rounds": {},
        },
        "our_fencer": {
            "name": fencer_name,
            "seed": fencer_seed,
            "club": fencer_club,
            "path": final_path,
            "final_placement_range": final_placement,
        },
        "warnings": warnings,
        "duplicate_bouts_removed": duplicates_removed,
    }


def extract_full_de_bracket(image_paths, our_fencer_name, tournament_id):
    """Orchestrate full DE bracket extraction from any number of images.

    Calls Vision once per image, then merges deterministically in Python.
    No second Claude call — merge is fast and reproducible.
    """
    extractions = [extract_de_bracket_from_photo(p, our_fencer_name) for p in image_paths]
    return merge_de_bracket_extractions(extractions, our_fencer_name)
