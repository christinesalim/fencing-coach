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


def extract_de_bracket_from_photo(image_path):
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
                    "text": """You are analyzing a screenshot of a fencing Direct Elimination (DE) bracket
displayed on a phone or tablet screen.

Extract EVERY visible bout in this screenshot, including partial/cut-off bouts
at the edges. Return JSON:

{
  "screenshot_metadata": {
    "estimated_total_bracket_size": <64 | 32 | 128 | etc.>,
    "visible_rounds": ["Table of 64", "Table of 32", ...],
    "position_hint": "top-left" | "top-right" | "bottom-left" | "bottom-right" | "center" | "left-half" | "right-half",
    "bracket_format": "single_elimination",
    "software_detected": "FencingTime" | "EnGarde" | "USAFencing" | "unknown"
  },
  "bouts": [
    {
      "bout_id_hint": "<round>-<approximate_position>",
      "round_name": "Table of 64" | "Table of 32" | "Table of 16" | "Table of 8" | "Semi-finals" | "Finals",
      "bracket_position": <1-based position within that round, top to bottom>,
      "fencer_top": {
        "name": "<LAST First>",
        "club": "<club or null>",
        "seed": <number or null>,
        "score": <number or null>
      },
      "fencer_bottom": {
        "name": "<LAST First>",
        "club": "<club or null>",
        "seed": <number or null>,
        "score": <number or null>
      },
      "winner": "top" | "bottom" | null,
      "is_bye": true | false,
      "is_partial": true | false,
      "referee": "<name or null>",
      "time": "<time or null>"
    }
  ],
  "cut_off_names": ["<any names visible but whose bout is not fully readable>"]
}

IMPORTANT:
- Extract ALL visible bouts, not just one fencer's path
- "bracket_position" counts from top of bracket: position 1 is the topmost bout in that round
- For byes, set is_bye=true, the advancing fencer in fencer_top, and fencer_bottom name as "BYE"
- If a bout is partially cut off at the edge of the screenshot, set is_partial=true and fill in what you can see
- Seed numbers appear in parentheses like (4) or #4
- The winner typically has the higher score, or their name may be bold/highlighted
- Score format varies: "15-7", "V15-7", or just the scores next to each name
- If you cannot read a name or score, use null"""
                }
            ],
        }],
    )

    return _parse_json_response(message.content[0].text)


def merge_de_bracket_extractions(extractions, our_fencer_name):
    """Merge multiple per-image extractions into a single bracket using Claude."""
    # Build the merge prompt with all extractions
    extraction_parts = []
    for i, ext in enumerate(extractions):
        extraction_parts.append(f"Screenshot {i + 1}: {json.dumps(ext)}")

    extractions_text = "\n\n".join(extraction_parts)

    prompt = f"""You are merging DE bracket data extracted from multiple screenshots of the same
fencing tournament bracket. The screenshots may overlap -- some bouts may appear in
multiple screenshots. Later screenshots may show the SAME bracket with MORE results
filled in (progressive updates as the tournament progresses).

Here are the extractions from {len(extractions)} screenshots:

{extractions_text}

Merge these into a single complete bracket. Rules:
1. DEDUPLICATE: If the same bout appears in multiple screenshots (same fencer
   names and round), keep the version with more complete data (non-null scores,
   non-partial). Later screenshots take priority since they have more results.
2. RESOLVE CONFLICTS: If two screenshots show different scores for the same bout,
   prefer the one marked is_partial=false, or the later screenshot.
3. RENUMBER: Assign correct bracket_position values (1-based, top to bottom) for
   each round.
4. VALIDATE TREE: Winners of adjacent bouts in round N should appear as fencers
   in round N+1. Flag any inconsistencies.
5. Identify the fencer named "{our_fencer_name}" (or closest match) and mark
   their path through the bracket.

Return:
{{
  "tournament_bracket": {{
    "bracket_size": <64 | 32 | 128>,
    "total_bouts_extracted": <number>,
    "completeness": <0.0-1.0, fraction of expected bouts that were captured>,
    "rounds": {{
      "Table of 64": [ ...bouts ordered by bracket_position... ],
      "Table of 32": [ ...bouts... ]
    }}
  }},
  "our_fencer": {{
    "name": "<matched name>",
    "seed": <number or null>,
    "path": [
      {{
        "round_name": "Table of 64",
        "opponent_name": "<name>",
        "opponent_seed": <number or null>,
        "opponent_club": "<club or null>",
        "score_for": <number or null>,
        "score_against": <number or null>,
        "result": "won" | "lost"
      }}
    ],
    "final_placement_range": "Top 32" | "Top 16" | "Top 8" | "Top 4" | "2nd" | "1st"
  }},
  "warnings": ["<any inconsistencies or missing data>"],
  "duplicate_bouts_removed": <count>
}}"""

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    return _parse_json_response(message.content[0].text)


def extract_full_de_bracket(image_paths, our_fencer_name, tournament_id):
    """Orchestrate full DE bracket extraction from multiple images.

    1. Extract each image individually
    2. If single image, do a simplified merge to get our_fencer path
    3. If multiple images, merge all extractions
    """
    extractions = []
    for path in image_paths:
        extraction = extract_de_bracket_from_photo(path)
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
