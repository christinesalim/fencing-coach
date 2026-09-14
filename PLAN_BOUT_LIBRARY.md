# Bout Library - Implementation Plan

## Overview

A video library of bouts between other fencers that Ethan can study. Videos are linked to the tournament they came from and to both opponents, so scouting footage surfaces on opponent intel pages.

This is a small feature — one new model, a handful of endpoints, one template, and reuse of the existing R2 video upload/playback infrastructure.

---

## 1. SQLAlchemy Models (in `database.py`)

Two models — a logical `ScoutBout` (the matchup + teaching notes) and `ScoutVideo` clips attached to it. Multiple clips per bout, each with its own R2 key and optional per-clip note.

### `ScoutBout` model

```python
class ScoutBout(Base):
    __tablename__ = 'scout_bouts'

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)        # nullable
    tournament_name = Column(String(255))               # denormalized for display
    round_name = Column(String(100))                    # "Finals", "Semi-Finals", "Table of 16", "Pool", etc.
    fencer_a_name = Column(String(255), nullable=False)
    fencer_a_id = Column(Integer, index=True)           # nullable FK to Opponent (null if Ethan or unmatched)
    fencer_b_name = Column(String(255), nullable=False)
    fencer_b_id = Column(Integer, index=True)           # nullable FK to Opponent
    score = Column(String(20))                          # e.g. "15-7" or null
    notes = Column(Text)                                # bout-level teaching notes ("how A ducks B's flèche…")
    tags = Column(Text)                                 # JSON array: ["height_mismatch", "lefty_vs_righty", ...]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### `ScoutVideo` model

```python
class ScoutVideo(Base):
    __tablename__ = 'scout_videos'

    id = Column(Integer, primary_key=True)
    scout_bout_id = Column(Integer, nullable=False, index=True)
    r2_key = Column(String(500), nullable=False)
    original_filename = Column(String(255))
    clip_notes = Column(Text)                           # optional per-clip note ("the duck", "the counter")
    sort_order = Column(Integer, default=0)             # display order within the bout
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Database helper functions

- `create_scout_bout(data_dict)` — create bout row; auto-link opponents via `match_opponent` (Tier 1/2 only); return serialized dict
- `get_scout_bout(bout_id)` — single bout with attached video list
- `get_scout_bouts(filters)` — list all, optionally filter by `tournament_id`, `opponent_id`, or `tag`
- `get_scout_bouts_for_opponent(opponent_id)` — all bouts where `fencer_a_id` OR `fencer_b_id` matches
- `update_scout_bout(bout_id, data_dict)` — edit notes/tags/fencer links/score
- `delete_scout_bout(bout_id)` — delete bout + all child videos (caller handles R2 cleanup of every R2 key)
- `add_scout_video(scout_bout_id, r2_key, original_filename, clip_notes=None)` — append a clip to a bout
- `delete_scout_video(video_id)` — delete clip row; return its r2_key so caller can purge R2
- `update_scout_video(video_id, data_dict)` — edit clip_notes / sort_order

Cascade delete: removing a `ScoutBout` deletes all child `ScoutVideo` rows.

---

## 2. Flask Endpoints (in `app.py`)

All `@login_required`. Mutating endpoints use POST (matches the rest of the app).

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/bout-library` | Render bout library page (HTML) |
| POST | `/api/scout-bouts` | Create new bout (JSON body — metadata only, no files) |
| GET | `/api/scout-bouts` | List bouts (JSON), optional `?tournament_id=`, `?opponent_id=`, `?tag=` |
| GET | `/api/scout-bouts/<id>` | Bout details with attached videos (JSON) |
| POST | `/api/scout-bouts/<id>` | Update notes / tags / fencer links / score |
| POST | `/api/scout-bouts/<id>/delete` | Delete bout + cascade delete all child videos + purge R2 objects |
| POST | `/api/scout-bouts/<id>/videos` | Upload one or more video clips for the bout (multipart, `files` field repeated) |
| GET | `/api/scout-videos/<id>/playback` | Presigned R2 URL for a clip |
| POST | `/api/scout-videos/<id>` | Update per-clip notes |
| POST | `/api/scout-videos/<id>/delete` | Delete a single clip + purge its R2 object |

### Upload flow

1. **Create bout first** (`POST /api/scout-bouts`) with the metadata (fencers, tournament, round, score, notes, tags). Auto-link opponents via Tier 1/2 fuzzy match silently; leave Tier 3+ unlinked.
2. **Add clips** (`POST /api/scout-bouts/<id>/videos`) — supports multi-file selection. Each file uploads serially:
   - Upload to R2 at key `scout/{bout_id}_{uuid}{ext}`
   - Insert a `ScoutVideo` row pointing at that key
   - Return the new clip dict
3. Client renders progress as "Uploading N clips…" and acquires a Screen Wake Lock for the duration of the batch (mirrors Ethan's bout-clip upload).
4. "+ Add Clip" on an existing bout uses the same `/api/scout-bouts/<id>/videos` endpoint.

### Mobile-safety reminders for the file input

- `accept="video/*"` and `multiple` (no `capture="environment"` — that forces the camera)
- Reuse the wake-lock helper functions from tournament_detail.html (`acquireBoutUploadWakeLock` / `releaseBoutUploadWakeLock`) — extract them to a shared scope or duplicate
- Single 500MB max file size limit (matches existing `MAX_CONTENT_LENGTH`)

---

## 3. UI

### `templates/bout_library.html` — Main page

**Top filter row** (mobile-friendly): a search input that fuzz-searches fencer names, tournament dropdown, opponent dropdown (auto-populated from `get_all_opponents`), tag pill filter. Filtering is server-rendered or in-page JS; either is fine.

**"+ New Bout" floating button (FAB)** opens a modal:
- Fencer A name (text) + Fencer B name (text) — auto-suggest from existing opponents as you type
- Tournament: dropdown of existing tournaments + "Other / not tracked" → free-text fallback
- Round name: dropdown (Finals, Semi-Finals, Table of 16, Table of 32, Pool, Other)
- Score (optional, free text)
- Bout-level **teaching notes** textarea ("What should Ethan notice?")
- Tag pills (tappable): Height Mismatch, Lefty vs Righty, Aggressive vs Defensive, Distance Fighter, Counter-Attacker, Close-In Fighting (multi-select)
- File input: `accept="video/*"`, `multiple`, NO `capture="environment"`
- "Create & Upload" button → POSTs `/api/scout-bouts` first, then iterates over `input.files` to POST each to `/api/scout-bouts/<id>/videos`. Shows "Uploading N clips…" status and holds the screen wake lock until all complete.

**Bout list below the FAB**, sorted newest-first, grouped by tournament:
- Card header: "Fencer A vs Fencer B — Round — Score" (e.g. "YE Andrew vs USHAKOV Richard — Finals — 15-14")
- Tournament name + date below header
- Tag pill row
- Bout-level teaching notes (truncated to ~3 lines, "Show more" expand)
- Stack of clip chips: `Clip 1 [Watch] [🗑]` / `Clip 2 [Watch] [🗑]` / etc. (matches Ethan's bout-clip UI for consistency)
- Per-clip notes shown subtly under each chip when set ("the duck", "counter-attack")
- "+ Add Clip" pill at end of clip stack (multi-select, same wake-lock + serial-upload pattern)
- Linked-opponent badges below header when `fencer_a_id` or `fencer_b_id` is non-null — clickable to that opponent's intel page
- "Edit" pencil to open the modal in edit mode (re-uses the same modal)
- "Delete bout" link (with `confirm()`)

### Opponent Intel integration (Phase 2)

**`templates/opponent_profile.html`** and **`templates/opponent_intel.html`** both gain a "Scouting Videos" section:
- Query `get_scout_bouts_for_opponent(opponent_id)`
- On `opponent_profile.html` (full profile): expanded list of bout cards (same shape as bout-library cards), with link to bout-library page filtered to this opponent
- On `opponent_intel.html` (game-day glance): **collapsible** section "▾ Scouting Videos (N)", collapsed by default. When expanded, shows a compact list: "vs USHAKOV Richard — Finals — Beta Fencing GP" + clip count. Tap → opens the bout-library card or starts the first clip directly.
- If the opponent appears in fencer_a slot: the "vs" label uses fencer_b's name (and vice versa).

### Navigation

Add a "Bout Library" card to `templates/index.html` (4th-or-later slot, e.g. 🎬 icon). Description: "Study videos of opponents and other fencers' bouts."

---

## 4. Implementation Sequence

**Phase 1 — Core library:**
1. Add `ScoutBout` and `ScoutVideo` models to `database.py` with runtime ADD-COLUMN/CREATE-TABLE migration
2. Add helper functions (create/get/list/update/delete bout + clip helpers, plus `get_scout_bouts_for_opponent`)
3. Auto-link Tier 1/2 opponents on bout create (silent — Tier 3+ left unlinked)
4. Add all `/api/scout-bouts/*` and `/api/scout-videos/*` endpoints to `app.py`
5. Build `bout_library.html` template (filter row + FAB modal + bout cards with multi-clip stack + multi-file upload)
6. Add 🎬 "Bout Library" nav card to `index.html`

**Phase 2 — Opponent intel integration:**
7. Add "Scouting Videos" section to `opponent_profile.html` (expanded list)
8. Add collapsible "Scouting Videos (N)" section to `opponent_intel.html` (collapsed by default)
9. Filter the bout-library page by `?opponent_id=` so the intel-page link drills down

Phases 1 + 2 ship in one cycle since the user requested both together.

---

## 5. Effort Estimate

This is a **small feature** because:
- One new model (simple, flat)
- R2 upload/playback is copy-paste from existing `_upload_bout_video` + `api_get_bout_video_playback`
- One new template following existing card/form patterns
- No AI processing needed
- No new dependencies

Phase 1 is ~2-3 hours of agent work. Phase 2 is ~1 hour on top.

---

## 6. Critical Files

- `database.py` — Add `ScoutVideo` model + helpers
- `app.py` — Add endpoints
- `templates/bout_library.html` — New page
- `templates/index.html` — Nav link
- `templates/opponent_profile.html` — Scouting videos section (Phase 2)
- `templates/opponent_intel.html` — Scouting videos section (Phase 2)
