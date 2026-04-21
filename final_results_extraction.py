"""Final Results photo extraction using Claude Vision API.

Mirrors the multi-image pattern from `de_extraction.py`. Accepts one or more
screenshots of a FencingTimeLive Final Results / standings page and returns a
merged payload with the tracked fencer's rank, total field size, event name,
the top-4 podium, and any warnings about suspected gaps between screenshots.
"""

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
    """Parse JSON from Claude response, handling markdown code fences."""
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


def _normalize_rank(rank):
    """Coerce a rank value into string form (preserve 'T' ties, drop Nones)."""
    if rank is None:
        return None
    if isinstance(rank, (int, float)):
        return str(int(rank))
    s = str(rank).strip()
    return s or None


def _normalize_podium_entry(entry):
    """Best-effort coerce one podium row into {place, name, club, division}."""
    if not isinstance(entry, dict):
        return None
    place = entry.get('place')
    name = entry.get('name')
    if place is None and name is None:
        return None
    return {
        'place': _normalize_rank(place),
        'name': (name or '').strip() or None,
        'club': (entry.get('club') or '').strip() or None,
        'division': (entry.get('division') or '').strip() or None,
    }


def extract_final_results(image_paths, our_fencer_name, tournament_id=None):
    """Claude Vision call against one or more final-standings screenshots.

    Parameters
    ----------
    image_paths : list[str | pathlib.Path]
        One or more screenshots of the Final Results / standings page.
    our_fencer_name : str
        USFA-format ``"LASTNAME Firstname"`` name to locate in the standings.
    tournament_id : int, optional
        Included for call-site parity with ``extract_full_de_bracket``; not
        currently used by the prompt but passed through for future telemetry.

    Returns
    -------
    dict
        ``{event_name, ethan_rank, total_fencers, podium: [...], warnings: [...]}``
        where each field may be ``None`` / empty if Claude couldn't find it.
    """
    if not image_paths:
        return {
            'event_name': None,
            'ethan_rank': None,
            'total_fencers': None,
            'podium': [],
            'warnings': ['No images provided'],
        }

    # Build the Vision content array: one image block per screenshot + a
    # trailing text block with the prompt. Matches the shape used by
    # `extract_full_de_bracket` / `extract_pool_results_from_photo`.
    content = []
    for i, path in enumerate(image_paths):
        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _get_media_type(path),
                "data": image_data,
            },
        })

    n = len(image_paths)
    segment_note = (
        "This image is the full standings page."
        if n == 1
        else f"Images 1 through {n} are consecutive segments of the SAME standings page — "
             "use later segments to extend earlier ones."
    )

    prompt_text = f"""You are analyzing screenshot(s) of a FencingTimeLive Final Results / standings page.

{segment_note}

TASK:
1. Identify the event name (often a heading near the top, e.g. "Y-12 Men's Épée", "Cadet Women's Foil").
2. Find the row for "{our_fencer_name}" and report their rank (may include a "T" tie indicator, e.g. "28T") and the total number of fencers in the event.
3. Return the top 4 places (ranks 1, 2, 3T, 3T) with name, club, and division.
4. If multiple screenshots are provided:
   - MERGE rows — any rank that appears in two screenshots must be returned only ONCE.
   - FLAG gaps in a "warnings" list, e.g. if ranks 15–16 are visible on one image and ranks 21+ on the next, add "Ranks 17–20 missing between screenshots".
   - If Ethan's row isn't visible in any segment, set ethan_rank to null and add a warning.
5. Name format: keep the USFA convention ("LASTNAME Firstname"). For the fencer lookup, match "{our_fencer_name}" fuzzily — spelling variations, capitalization, and comma-separated formats ("LASTNAME, Firstname") should all be accepted.
6. Only return the TOP 4 in the `podium` array — NOT every row. Leave `full_field` out.

Return JSON with this exact shape (no extra keys):
{{
  "event_name": "<e.g. 'Y-12 Men's Épée' or null if not visible>",
  "ethan_rank": "<e.g. '28T' or '5' or null>",
  "total_fencers": <integer or null>,
  "podium": [
    {{"place": "1", "name": "LASTNAME Firstname", "club": "<club>", "division": "<division>"}},
    {{"place": "2", "name": "LASTNAME Firstname", "club": "<club>", "division": "<division>"}},
    {{"place": "3T", "name": "LASTNAME Firstname", "club": "<club>", "division": "<division>"}},
    {{"place": "3T", "name": "LASTNAME Firstname", "club": "<club>", "division": "<division>"}}
  ],
  "warnings": ["<zero or more short strings describing gaps or unclear rows>"]
}}

Notes:
- If a field is unknown, use null (not an empty string).
- Podium may have fewer than 4 entries if the page only shows some of the top finishers — return whatever is visible.
- Do not include Ethan's row in the podium unless he actually placed in the top 4.
- Leave division as null if not displayed.
"""
    content.append({"type": "text", "text": prompt_text})

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3072,
        messages=[{"role": "user", "content": content}],
    )

    raw = message.content[0].text
    parsed = _parse_json_response(raw)

    # Normalize the response — Claude occasionally returns integers instead of
    # strings for rank, or omits nullable fields entirely.
    event_name = parsed.get('event_name')
    if isinstance(event_name, str):
        event_name = event_name.strip() or None

    total_fencers = parsed.get('total_fencers')
    if isinstance(total_fencers, str):
        try:
            total_fencers = int(total_fencers.strip())
        except ValueError:
            total_fencers = None
    elif total_fencers is not None and not isinstance(total_fencers, int):
        try:
            total_fencers = int(total_fencers)
        except (TypeError, ValueError):
            total_fencers = None

    podium_raw = parsed.get('podium') or []
    if not isinstance(podium_raw, list):
        podium_raw = []
    podium = []
    for row in podium_raw[:4]:
        normalized = _normalize_podium_entry(row)
        if normalized:
            podium.append(normalized)

    warnings = parsed.get('warnings') or []
    if not isinstance(warnings, list):
        warnings = []
    warnings = [str(w) for w in warnings if w]

    return {
        'event_name': event_name,
        'ethan_rank': _normalize_rank(parsed.get('ethan_rank')),
        'total_fencers': total_fencers,
        'podium': podium,
        'warnings': warnings,
    }
