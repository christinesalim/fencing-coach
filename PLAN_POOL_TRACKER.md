# Live Pool Tracker — Implementation Plan

**Clickable mockup:** [mockups/pool_tracker.html](mockups/pool_tracker.html) — open directly in a browser. Includes a small nav bar at the top to jump between the 5 views. All design decisions below reflect the final mockup, not the earlier plan iteration.

## Overview

A mobile-first, at-the-strip tool that lets Christine track where Ethan is in the pool bout order and record each bout's score as it finishes, so Ethan can cross-check his pool scores against the ref's paper sheet before signing.

Inputs: a screenshot of the Fencing Time Live pool page (roster + bout order on one screen).
Outputs: a live tracker UI; a per-bout score history in `PoolBout`; a final grid summary (in **pool-number order**, matching the paper sheet) for ref-sheet comparison.

Reuses existing `Tournament` / `PoolRound` / `PoolBout` schema. The existing `extract_pool_results_from_photo` ([app.py:791](app.py#L791)) reads completed paper pool sheets — a different grid-based input — so it can't be reused directly for FTL screenshots. We can reuse its boilerplate (base64 encoding, media-type detection, Claude client call pattern) but need a brand new prompt and extraction function.

---

## Design Decisions (locked, matches mockup)

- **Placement:** Under Tournaments (reuses existing schema). A "Quick Start Pool" button on home auto-creates a draft Tournament named **`Pool — <YYYY-MM-DD>`** and jumps straight into the tracker.
- **Vision input:** One FTL screenshot per pool, extracted in one Vision call. The whole FTL pool page (roster + bout order) fits in a single phone screenshot.
- **Row layout:** `[bout#] [pool#] Right LAST  vs  Left LAST [pool#] [score cell]`. Both fencers' pool numbers inline as small chips next to their last names — no separate pool-number column eating horizontal space. Last names only in the main list (first names dropped) since pool number is a sharper identifier.
- **Ethan highlight:** `★` next to bout number + light-blue row background on his bouts.
- **Ethan's next bout:** Pinned warm-yellow card above the list — "Ethan's next: Bout 9 — XIAO vs SALIM" — distinct from his highlighted rows below.
- **Single bout list (no pending/done split):** All 15 bouts stay in posted order; rows never shuffle when marked done. Each row carries its own visual state so you can scan down the sheet without losing your place. Done rows are dimmed; the score cell changes appearance.
- **Tap behavior (two targets per row):**
  - Tap the fencer-names area → marks that bout **done** (no score required).
  - Tap the score cell → opens the **score modal** (always available: for new entry, for editing a mistyped score, or for scoring a non-Ethan bout).
- **Row visual states:**
  | State | Row | Score cell |
  |---|---|---|
  | Pending (non-Ethan) | White | Blue `+` |
  | Pending (Ethan) | Blue + ★ | Blue `+` |
  | Done, no score | Dimmed | Gray `✓ add score` |
  | Done scored (non-Ethan) | Dimmed | Muted "5–3" |
  | Done scored (Ethan WIN) | Blue + ★ | Green "5–3 V" |
  | Done scored (Ethan LOSS) | Blue + ★ | Red "2–5 D" |
- **Double-strip support:** Each row's state is independent — no sequential "current bout" pointer. Order of completion is unpredictable when refs use 2 strips. (See memory `project_double_strip_pools.md`.)
- **Score modal:** Pre-filled on edit. Shows "Bout N · Editing" in the title. Has a red **"Mark as not done"** button (only when the bout is already done) — reverts the row back to Pending in one tap. No separate "Clear score" button; emptying both inputs and saving achieves the same thing.
- **End-of-pool grid:** Mirrors the ref's paper. One column per opponent, in **pool-number order** (not bout order), skipping Ethan's own column. Each cell shows FIE notation (V5/D2) big + full score (5–3) + bout # for reference. Header labels columns like `#1 BORO`, `#2 ZHU` so your eye jumps straight to the matching cell on the paper. Tap any cell → score modal (edit). Row labeled "SALIM Ethan · Pool #3".
- **Pool indicator:** Computed only from bouts where scores were actually entered. UI shows "Indicator from X of 15 bouts" so partial-data state is visible, not hidden.
- **State durability:** All in-progress state autosaves to the server after each tap. `localStorage` as secondary cache in case of network drop.

---

## UI Mockups

Fully-interactive mockup lives at [mockups/pool_tracker.html](mockups/pool_tracker.html) — covers all 5 views (Upload → Processing → Live tracker → Score modal → End-of-pool grid). The grid in the end-of-pool view uses **pool-number order** matching the ref's paper, not bout order.

Reference-only ASCII of the key screen (live tracker, mid-pool) for anyone reading the plan without opening the mockup:

```
┌──────────────────────────────────────┐
│ POOL 5 · STRIP 6 · 6 of 15 done      │
│ Ethan 2V – 1D so far                 │
├──────────────────────────────────────┤
│ ★ Ethan's next: Bout 9               │
│   XIAO vs SALIM                      │
├──────────────────────────────────────┤
│ 1  │ [1] BOROVIKOV vs ZHU [2]  │5–3 │  ← done, non-Ethan
│ 2  │ [5] XIAO vs HOLBROOK [4]  │ ✓  │  ← done, no score
│ 3★ │ [2] ZHU  vs  SALIM [3]    │2–5V│  ← Ethan WIN (green)
│ 4  │ [4] HOLBROOK vs POLI [6]  │ +  │  ← pending
│ 5★ │ [3] SALIM vs BOROVI [1]   │5–3V│  ← Ethan WIN
│ ... (15 total, all stay in posted order)
└──────────────────────────────────────┘
```

Open the HTML mockup for exact styling, Ethan-highlight colors, and the end-of-pool grid.

---

## Phased Implementation

### Phase 1 — Vision extraction of FTL screenshot ⏳

- [ ] Add `extract_pool_bout_order_from_photo(image_path)` in `app.py` (near existing `extract_pool_results_from_photo` at line 791).
- [ ] Vision prompt returns:
  ```json
  {
    "pool_number": 5,
    "strip": 6,
    "roster": [
      {"pool_num": 1, "last_name": "BOROVIKOV", "first_name": "Alexander", "club": "AFM", "region": "Central California"},
      ...
    ],
    "bouts": [
      {"order": 1, "right_num": 1, "left_num": 2},
      {"order": 2, "right_num": 4, "left_num": 5},
      ...
    ],
    "ethan_pool_num": 3
  }
  ```
- [ ] Match Ethan by **both** first name "Ethan" and last name "SALIM" (case-insensitive, both must match). Belt-and-suspenders because other fencers may share a surname. If no match → return `null`, UI prompts user to tap his row.
- [ ] Add `/api/upload-pool-order-photo` route, modeled on `/api/upload-pool-photo` ([app.py:1087](app.py#L1087)).

### Phase 2 — Schema additions ⏳

- [ ] Add two nullable TEXT columns to `PoolRound` ([database.py:95](database.py#L95)):
  - `roster_json` — serialized roster from Vision extraction
  - `bout_order_json` — full 15-bout list with per-bout status (pending/done)
- [ ] `PoolBout` unchanged; a row is created the first time a score is entered for that bout (score_for/score_against nullable mid-pool).
- [ ] Nullable, so existing `PoolRound` rows stay intact. No migration needed on SQLite; `create_all` auto-adds columns on fresh DB only — manual `ALTER TABLE` for Render Postgres.

### Phase 3 — Live Tracker UI ⏳

- [ ] New template `templates/pool_tracker.html`, mobile-first. Port styles directly from [mockups/pool_tracker.html](mockups/pool_tracker.html).
- [ ] Follow iOS mobile CSS rules from memory (`feedback_ios_mobile_css.md`): `-webkit-appearance:none` on number inputs, `max-width` on flex rows, stacked rows where needed.
- [ ] Header: pool #, strip, running Ethan tally (`2V–1D so far`), "X of 15 done" counter.
- [ ] "Ethan's next bout" pinned card: lowest-order pending bout he's in.
- [ ] **Single bout list** (not pending/done split): all 15 bouts in posted order, each row carries its own visual state. See the state table in Design Decisions.
- [ ] Tap handlers:
  - Names area → mark row done (no score)
  - Score cell → open score modal (new or edit)
- [ ] Row never moves when state changes — only the inline styling updates.
- [ ] Autosave each tap to server via a `/api/pool-tracker/<pool_round_id>/update` endpoint.
- [ ] `localStorage` cache keyed by `pool_round_id` for network-drop resilience.

### Phase 4 — Score entry modal ⏳

- [ ] Modal with two number inputs + Cancel / Save.
- [ ] Pre-fills existing scores when editing a done bout.
- [ ] Title shows `Bout N` for new entry, `Bout N · Editing` for edit.
- [ ] **"Mark as not done"** red button shown only when the bout is already done — reverts the row to Pending in one tap.
- [ ] On save: create or update the `PoolBout` row, mark the bout done in `bout_order_json`, update tally in header.
- [ ] Validates: 0 ≤ score ≤ 5 (épée pool bouts).
- [ ] Works identically for Ethan and non-Ethan bouts.

### Phase 5 — End-of-pool summary (grid) ⏳

- [ ] Triggered when all 15 bouts are marked done, or user taps "Finish Pool & Review" early.
- [ ] **Grid view in pool-number order:** one column per opponent (not including Ethan), ordered by pool number. Column header = `#N LAST` (e.g., `#1 BORO`). Each cell shows V5/D2 big + full score + bout # below. Tap cell → score modal.
- [ ] 4-stat tile row at the top: V–D / Ind / TS / TR.
- [ ] "SALIM Ethan · Pool #3" label above the grid so the row is unambiguous.
- [ ] On "Looks good — save pool": compute V/D/TS/TR/indicator from scored bouts, write to `PoolRound` summary fields.
- [ ] Partial-data note: "Indicator from X of 15 bouts" so the user knows which bouts contributed.
- [ ] Secondary option: link to the existing `/api/upload-pool-photo` flow to upload the ref's final paper pool sheet as a Vision cross-check.

### Phase 6 — Entry points ⏳

- [ ] "Start Pool Tracker" button on `tournament_detail.html` next to the existing "Upload Pool Sheet Photo" option.
- [ ] "Quick Start Pool" button on `index.html` that:
  - Creates a draft `Tournament` row with name **`Pool — <YYYY-MM-DD>`** (today's date)
  - Creates an empty `PoolRound` for it
  - Redirects to the pool tracker upload screen for that pool
- [ ] After the pool is saved, UI nudges the user to rename the draft tournament (small banner at top of tournament detail).

---

## Vision Prompt Sketch

Based on the FTL screenshot format (`IMG_4509.PNG`):

```
This is a screenshot of a Fencing Time Live pool page.

Extract:
1. Pool number ("POOL #X")
2. Strip number ("ON STRIP X")
3. The pool roster — a numbered list of fencers (1-N) showing:
   - pool_num (1-based position)
   - last_name (ALL CAPS surname shown first)
   - first_name
   - club (abbreviation like "AFM", "EBFG", "BAYFC")
   - region (e.g. "Central California")
4. The bout order table — columns are:
   - # (bout number, 1-based)
   - Right Fencer (full name)
   - Left Fencer (full name)
   - # (the LEFT fencer's pool number)
   Return each bout as {order, right_num, left_num} using the pool_num values from the roster.
5. ethan_pool_num — find the fencer whose first_name is "Ethan" AND last_name is "SALIM" (both must match, case-insensitive). Return their pool_num, or null if not found.

Return JSON:
{
  "pool_number": <int>,
  "strip": <int or null>,
  "roster": [{"pool_num":1,"last_name":"...","first_name":"...","club":"...","region":"..."}, ...],
  "bouts": [{"order":1,"right_num":1,"left_num":2}, ...],
  "ethan_pool_num": <int or null>
}
```

Expected pool-of-6 output has 15 bouts in standard FIE order: 1-2, 4-5, 2-3, 5-6, 3-1, 6-4, 2-5, 1-4, 5-3, 1-6, 4-2, 3-6, 5-1, 3-4, 6-2.

---

## Open Questions

1. **Roster name matching fallback** — if "Ethan SALIM" doesn't match (e.g., FTL formatting quirk), fall through to a tap-to-identify step. Confirm the fallback UX.
2. **Ref deviates from posted bout order** — should we support reordering bouts in the UI (drag or swap)? Or is tap-done enough since order of done doesn't matter?
3. **Opponent club matching** — FTL uses abbreviations ("CAP"); your `Opponent` table may have full names. Store raw FTL string, or try to resolve to an `Opponent` row? (Can defer to a Phase 7.)
4. **Pool indicator with partial data** — "Indicator from 5 of 15 bouts" is honest but may confuse. Suppress indicator entirely if < X bouts scored? Show per-fencer indicator only?
5. **Phase 7 feeder** — once stable, pool opponents could auto-populate `Opponent` rows for Opponent Intel. Scope for a later phase.

---

## Not in Scope (for now)

- Live tap-to-increment scoring during a bout (user confirmed: scores entered after bout ends)
- Bout timer (3-min pool bout clock)
- Priority minute coin-flip helper
- Hardcoded FIE pool-order generator (we always start from an FTL screenshot)
- Multi-pool-day stats aggregation
