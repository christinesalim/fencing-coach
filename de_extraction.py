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
- The bracket flows LEFT to RIGHT. Each column is a round: Table of 64 → Table of 32 → Table of 16 → etc.
- Each bout is a PAIR of two fencers stacked vertically, connected by bracket lines.
- The WINNER advances RIGHT to the next column, where they are paired with a NEW opponent.
- Numbers in parentheses like (4) or (36) are SEEDS from pool ranking.
- Scores appear as "15-7" etc. DE bouts go to 15 touches.
- "BYE" means automatic advance, no bout fenced.

STEP BY STEP:
1. Find "{our_fencer_name}" in the leftmost column (first round).
2. Identify who they are paired with (the other name in their bracket pair). That is their Round 1 opponent.
3. Read the score. Did our fencer win or lose?
4. If they WON, follow the bracket line RIGHT to the next column. Find who they are now paired with — that is a DIFFERENT person, their Round 2 opponent.
5. Repeat until they lose or the bracket ends.

CRITICAL VALIDATION:
- Each round MUST have a DIFFERENT opponent. If you wrote the same opponent name twice, you misread the bracket — go back and re-trace the lines.
- The opponent in Round 2 is the WINNER of a different Round 1 bout, NOT the same person from Round 1.

Return JSON:
{{
  "bracket_metadata": {{
    "estimated_bracket_size": <64 | 32 | 128>,
    "software_detected": "FencingTimeLive" | "unknown",
    "visible_rounds": ["Table of 64", "Table of 32", ...]
  }},
  "our_fencer": {{
    "name": "<exact name as shown>",
    "seed": <number or null>,
    "club": "<club or null>"
  }},
  "bouts": [
    {{
      "round_name": "Table of 64",
      "opponent_name": "<LAST First>",
      "opponent_club": "<club or null>",
      "opponent_seed": <number or null>,
      "score_for": <our fencer's score>,
      "score_against": <opponent's score>,
      "result": "won" | "lost"
    }}
  ],
  "final_placement_range": "Top 64" | "Top 32" | "Top 16" | "Top 8" | "Top 4" | "2nd" | "1st",
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


def merge_de_bracket_extractions(extractions, our_fencer_name):
    """Merge multiple per-image extractions into a single fencer path."""
    # Filter out extractions where fencer wasn't found
    valid = [e for e in extractions if e.get('our_fencer')]
    if not valid:
        return {
            "tournament_bracket": {"bracket_size": 0, "total_bouts_extracted": 0, "completeness": 0, "rounds": {}},
            "our_fencer": {"name": our_fencer_name, "seed": None, "path": [], "final_placement_range": "Unknown"},
            "warnings": ["Fencer not found in any screenshot"],
            "duplicate_bouts_removed": 0
        }

    # For a single extraction, just reformat and dedup
    if len(valid) == 1:
        ext = valid[0]
        bouts = _dedup_fencer_path(ext.get('bouts', []))
        return {
            "tournament_bracket": {
                "bracket_size": ext.get('bracket_metadata', {}).get('estimated_bracket_size', 0),
                "total_bouts_extracted": len(bouts),
                "completeness": 0,
                "rounds": {}
            },
            "our_fencer": {
                "name": ext.get('our_fencer', {}).get('name', our_fencer_name),
                "seed": ext.get('our_fencer', {}).get('seed'),
                "path": bouts,
                "final_placement_range": ext.get('final_placement_range', 'Unknown')
            },
            "warnings": [],
            "duplicate_bouts_removed": len(ext.get('bouts', [])) - len(bouts)
        }

    # Multiple extractions: merge via Claude (text-only, cheap)
    extraction_parts = []
    for i, ext in enumerate(valid):
        extraction_parts.append(f"Screenshot {i + 1}: {json.dumps(ext)}")

    extractions_text = "\n\n".join(extraction_parts)

    prompt = f"""You are merging DE bracket paths for "{our_fencer_name}" extracted from multiple
progressive screenshots of the same tournament bracket. Later screenshots show more
completed rounds.

{extractions_text}

Merge into a single path for {our_fencer_name}. Rules:
1. Each round should appear ONCE with the best available data (prefer non-null scores)
2. Later screenshots take priority for scores and results
3. Each bout MUST have a DIFFERENT opponent — if the same opponent appears in two
   rounds, keep only the first occurrence (the later one is an extraction error)
4. Order bouts chronologically: Table of 64 → Table of 32 → Table of 16 → etc.

Return JSON:
{{
  "tournament_bracket": {{
    "bracket_size": <64 | 32 | 128>,
    "total_bouts_extracted": <number>,
    "completeness": 0,
    "rounds": {{}}
  }},
  "our_fencer": {{
    "name": "<exact name>",
    "seed": <number or null>,
    "path": [
      {{
        "round_name": "Table of 64",
        "opponent_name": "<LAST First>",
        "opponent_seed": <number or null>,
        "opponent_club": "<club or null>",
        "score_for": <number or null>,
        "score_against": <number or null>,
        "result": "won" | "lost"
      }}
    ],
    "final_placement_range": "<placement>"
  }},
  "warnings": ["<any issues found>"],
  "duplicate_bouts_removed": <count>
}}"""

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    result = _parse_json_response(message.content[0].text)

    # Safety net: dedup even after merge
    if result.get('our_fencer', {}).get('path'):
        original_len = len(result['our_fencer']['path'])
        result['our_fencer']['path'] = _dedup_fencer_path(result['our_fencer']['path'])
        removed = original_len - len(result['our_fencer']['path'])
        result['duplicate_bouts_removed'] = result.get('duplicate_bouts_removed', 0) + removed

    return result


def extract_full_de_bracket(image_paths, our_fencer_name, tournament_id):
    """Orchestrate full DE bracket extraction from multiple images.

    1. Extract each image individually
    2. If single image, do a simplified merge to get our_fencer path
    3. If multiple images, merge all extractions
    """
    extractions = []
    for path in image_paths:
        extraction = extract_de_bracket_from_photo(path, our_fencer_name)
        extractions.append(extraction)

    # For large brackets with 6+ images, merge in two phases
    if len(extractions) > 5:
        # Phase 1: merge in groups of 3
        merged_groups = []
        for i in range(0, len(extractions), 3):
            group = extractions[i:i + 3]
            if len(group) == 1:
                merged_groups.append(group[0])
            else:
                merged = merge_de_bracket_extractions(group, our_fencer_name)
                merged_groups.append(merged)
        # Phase 2: final merge of groups
        # Convert merged results back to extraction format for re-merging
        result = merge_de_bracket_extractions(merged_groups, our_fencer_name)
    else:
        result = merge_de_bracket_extractions(extractions, our_fencer_name)

    return result
