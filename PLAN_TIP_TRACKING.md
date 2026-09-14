# Tip Deduplication and Improvement Tracking - Design Notes

## Problem

When uploading voice memos from multiple tournaments, the same advice often appears repeatedly. Currently these become duplicate line items in the tips list. Instead, we should:

1. Deduplicate tips and track how often they recur
2. Let Ethan track which tips he's actually using
3. Show improvement over time

---

## Database Changes

### Update `tips` table — add tracking fields:

```python
class Tip(Base):
    __tablename__ = 'tips'
    id = Column(Integer, primary_key=True)
    category = Column(String(50), index=True)
    text = Column(Text, unique=True)
    times_seen = Column(Integer, default=1)        # how many times this advice appeared
    last_seen_at = Column(DateTime)                # last tournament it came up
    times_used = Column(Integer, default=0)        # times Ethan reported using it
    times_not_used = Column(Integer, default=0)    # times Ethan reported not using it
    status = Column(String(20), default='active')  # active / mastered / archived
    created_at = Column(DateTime, default=datetime.utcnow)
```

### New `tip_events` table — log each occurrence:

```python
class TipEvent(Base):
    __tablename__ = 'tip_events'
    id = Column(Integer, primary_key=True)
    tip_id = Column(Integer, index=True)
    tournament_id = Column(Integer, index=True)    # which tournament triggered this
    event_type = Column(String(20))                # 'extracted' / 'used' / 'not_used'
    notes = Column(Text)                           # optional context
    created_at = Column(DateTime, default=datetime.utcnow)
```

This gives a full history: "This tip was extracted at 3 tournaments. Ethan used it at 2 of them."

---

## Smart Deduplication During Extraction

When Claude extracts tips from a voice memo, before adding each tip:

1. Check for exact text match (existing behavior)
2. If no exact match, use Claude to check for semantic similarity against existing tips:

```
Given this new tip: "{new_tip}"

And these existing tips in the same category:
{list of existing tips}

Is the new tip saying essentially the same thing as any existing tip?
Return JSON: {"is_duplicate": true/false, "matching_tip_index": <index or null>}
```

If duplicate:
- Don't add new row
- Increment `times_seen` on the matching tip
- Update `last_seen_at`
- Log a `tip_event` with type 'extracted' and the tournament_id

If not duplicate:
- Add as a new tip with `times_seen=1`

---

## Recurring Badges (Tips UI)

Display badges based on `times_seen`:

| times_seen | Badge | Visual |
|-----------|-------|--------|
| 1 | none | normal tip |
| 2 | "x2" | small grey badge |
| 3 | "x3" | yellow badge |
| 4+ | "x{n}" with flame | red/orange badge, bold text |

Tips sorted within each category: recurring tips first (highest `times_seen`), then by most recent.

---

## Improvement Tracking (Post-Tournament Review)

### After each tournament, show a "Review Your Tips" screen:

- List all active tips
- For each tip, two buttons: "Used it" (thumbs up) / "Didn't use it" (thumbs down)
- This is a quick 1-2 minute review done after the tournament

### What happens when you tap:

**"Used it"**:
- Increment `times_used` on the tip
- Log `tip_event` with type 'used' and tournament_id
- If `times_used >= 3` and tip has been used in last 3 consecutive tournaments → auto-suggest marking as "mastered"

**"Didn't use it"**:
- Increment `times_not_used` on the tip
- Log `tip_event` with type 'not_used' and tournament_id
- If tip is recurring (times_seen >= 3) AND not_used is high → flag as "needs focus"

---

## Tip Status System

Each tip has a status:

| Status | Meaning | Visual |
|--------|---------|--------|
| `active` | Currently relevant, needs attention | Normal display |
| `mastered` | Ethan is consistently using this | Green checkmark, moved to bottom or separate "mastered" section |
| `archived` | No longer relevant (coach changed approach, etc.) | Hidden by default |

### Mastery criteria (suggested, not automatic):

A tip can be marked as "mastered" when:
- `times_used >= 3` — Ethan has reported using it at 3+ tournaments
- Recent usage — used in the most recent tournament
- User confirms the suggestion

Show a subtle prompt: "You've used this tip at your last 3 tournaments. Mark as mastered?"

### Mastered tips section:

At the bottom of the tips page, a collapsible "Mastered" section showing tips with green checkmarks. These are wins — proof of improvement. Good for confidence before a tournament.

---

## Tips Page UI Updates

### Sort order (within each category):
1. Needs focus: recurring + not used (red/orange badges)
2. Active: normal tips sorted by recency
3. Mastered: green checkmarks, collapsible section

### Tip card additions:
- Recurring badge (x2, x3, flame for 4+)
- Usage indicator: "Used 3/4 tournaments" as small text
- "Needs focus" flag if recurring but not used
- "Mastered" checkmark if consistently used

### Post-tournament review:
- Button on tournament detail page: "Review Tips for This Tournament"
- Opens a simple screen with all active tips and thumbs up/down buttons
- Quick to complete, builds the usage data over time

---

## Connection to Other Features

### DE Prep Tips (Feature 1 from Tournament Analysis plan):
- When generating DE prep tips, reference which coaching tips are recurring but NOT being used
- "You keep getting advice to be patient at 4-4, but haven't been using it — make this your #1 focus"

### Opponent Intel:
- Pre-bout intel can highlight relevant tips: "Against aggressive fencers, remember: [recurring tip about patience]"

### Full Analysis:
- Post-tournament analysis can reference tip usage: "You reported using 3 of 5 active tips. The two you didn't use (distance management, patience) align with your 5-4 losses."

---

## Implementation Sequence

1. Add `times_seen`, `last_seen_at`, `times_used`, `times_not_used`, `status` columns to `tips` table (migration script needed for existing data)
2. Add `TipEvent` model
3. Update `save_session_to_db()` to use smart deduplication (Claude semantic check)
4. Add recurring badges to tips page UI
5. Add post-tournament tip review screen
6. Add mastery tracking and suggestions
7. Update tip sorting (recurring first, mastered last)

---

## Cost Estimate

- Smart deduplication: ~$0.002 per extraction (one small Claude call to check similarity)
- Everything else is local logic, no API cost
- Annual: negligible (<$0.50/year)
