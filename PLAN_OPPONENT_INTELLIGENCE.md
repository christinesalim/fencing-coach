# Opponent Intelligence System - Implementation Plan

## Overview

Let Ethan look up opponents by name or traits (tall, left-handed, etc.), view tactical intel before bouts, and build up opponent profiles over time. Manual data entry for now; integrates with pool/DE photo extraction later.

---

## Status (2026-04-20)

| Phase | Item | Status |
|---|---|---|
| 1 | `Opponent` / `OpponentTacticalNote` / `BoutRecord` models + DB helpers | ✅ Done |
| 1 | `fuzzy_matching.py` with `thefuzz` + `python-Levenshtein` + 4-tier `match_opponent` | ✅ Done |
| 2 | All `/api/opponents/*` CRUD + notes + search + filter + manual bouts endpoints | ✅ Done |
| 2 | Page routes `/opponents`, `/opponents/<id>`, `/opponents/<id>/intel` | ✅ Done |
| 3 | `opponents.html` (list + search + trait filter + create modal) | ✅ Done |
| 3 | `opponent_profile.html` (view/edit + notes + H2H + manual bout) | ✅ Done |
| 3 | `opponent_intel.html` (pre-bout glance view with WHAT WORKS / WATCH OUT FOR / WEAKNESSES) | ✅ Done |
| 3 | `index.html` nav card | ✅ Done |
| 4 | `sync_bout_to_opponent` hooked into `save_pool_results_to_db` + `save_de_results_to_db` | ✅ Done |
| 4 | `backfill_bout_records.py` one-time walker | ✅ Done |
| 4 | `backfill_opponent_names.py` for first/last parsing | ✅ Done |
| 4 | Opponent-intel preview badges on pool/DE upload result pages (green/yellow/grey) | ✅ Done |
| 4 | Tournament-detail bout badges → opponent `/intel` | ✅ Done |
| 4 | "Confirm match" UI for Tier 3/4 fuzzy candidates | ✅ Done |
| 5c | Final-results photo extraction (new — see §5c) | ✅ Done |
| 5b | FencingTracker search + profile scrape (see §5b) | ⏳ Pending |
| — | Merge-two-opponents tool for near-duplicate stubs | ✅ Done |
| — | Club-alias auto-append on confirmed matches | ✅ Done |

---

## 1. SQLAlchemy Models (in `database.py`)

### `Opponent` model

```python
class Opponent(Base):
    __tablename__ = 'opponents'

    id = Column(Integer, primary_key=True)
    canonical_name = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100), index=True)
    name_aliases = Column(Text)       # JSON array of alternative spellings
    club = Column(String(255))
    club_aliases = Column(Text)       # JSON array
    division = Column(String(100))
    handedness = Column(String(10))   # left/right/unknown
    height_category = Column(String(20))  # very_tall/tall/average/short/very_short
    build = Column(String(20))        # stocky/average/lean/athletic
    speed_rating = Column(String(20)) # very_fast/fast/average/slow
    primary_style = Column(String(30))    # aggressive/defensive/counter_attacker/distance_fighter/infighter/tactician
    secondary_style = Column(String(30))
    photo_url = Column(String(500))
    first_encountered = Column(DateTime)
    last_encountered = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Use `Text` for JSON fields (not `JSONB`) since the app supports SQLite for local dev. Store `canonical_name` as `"LASTNAME Firstname"` (fencing convention).

### `OpponentTacticalNote` model

```python
class OpponentTacticalNote(Base):
    __tablename__ = 'opponent_tactical_notes'

    id = Column(Integer, primary_key=True)
    opponent_id = Column(Integer, nullable=False, index=True)
    category = Column(String(30))  # favorite_action/weakness/tell/what_worked/what_failed/physical_trait/mental_trait/general
    observation = Column(Text, nullable=False)
    times_validated = Column(Integer, default=0)
    times_invalidated = Column(Integer, default=0)
    source = Column(String(20), default='manual')
    observed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Confidence score is computed on read as `validated / (validated + invalidated)`.

### `BoutRecord` model (opponent-centric bout history)

```python
class BoutRecord(Base):
    __tablename__ = 'bout_records'

    id = Column(Integer, primary_key=True)
    opponent_id = Column(Integer, nullable=False, index=True)
    tournament_id = Column(Integer, index=True)       # FK to Tournament, nullable
    tournament_name = Column(String(255))             # denormalized for manual entries
    tournament_date = Column(DateTime, index=True)    # indexed for chronological sort
    bout_type = Column(String(15))                    # pool / elimination
    pool_bout_id = Column(Integer, index=True)        # nullable; links back to PoolBout row
    elimination_round_id = Column(Integer, index=True) # nullable; links back to EliminationRound row
    score_for = Column(Integer)
    score_against = Column(Integer)
    result = Column(String(5))                        # won / lost
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Populated automatically by the auto-sync flow (section 3b) when pool/DE photos are uploaded. Manual entries (for bouts that predate the app) leave `pool_bout_id` / `elimination_round_id` / `tournament_id` as `NULL`.

### Database helper functions

- `create_opponent(data_dict)` -- returns serialized opponent dict
- `get_opponent(opponent_id)` -- single opponent with notes
- `update_opponent(opponent_id, data_dict)`
- `delete_opponent(opponent_id)` -- cascade-deletes notes and bout records
- `search_opponents_by_name(query)` -- fuzzy search (see section 3)
- `search_opponents_by_traits(filters_dict)` -- filter by handedness, height, style, etc.
- `get_all_opponents()` -- list view
- `add_tactical_note(opponent_id, data_dict)`
- `update_tactical_note(note_id, data_dict)`
- `delete_tactical_note(note_id)`
- `get_tactical_notes(opponent_id)`
- `add_bout_record(opponent_id, data_dict)`
- `get_head_to_head(opponent_id)` -- compute wins/losses/touches from bout_records
- `lookup_opponents_by_names(name_list)` -- batch fuzzy lookup

---

## 2. Flask API Endpoints (in `app.py`)

### Opponent CRUD

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/opponents` | Render opponents list page (HTML) |
| GET | `/opponents/<id>` | Render single opponent profile page (HTML) |
| POST | `/api/opponents` | Create opponent (JSON body) |
| GET | `/api/opponents` | List all opponents (JSON) |
| GET | `/api/opponents/<id>` | Get opponent with notes + head-to-head (JSON) |
| POST | `/api/opponents/<id>` | Update opponent (JSON body) |
| POST | `/api/opponents/<id>/delete` | Delete opponent |

### Tactical Notes

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/opponents/<id>/notes` | Add tactical note |
| POST | `/api/opponents/<id>/notes/<note_id>` | Update tactical note |
| POST | `/api/opponents/<id>/notes/<note_id>/delete` | Delete tactical note |
| POST | `/api/opponents/<id>/notes/<note_id>/validate` | Increment `times_validated` |
| POST | `/api/opponents/<id>/notes/<note_id>/invalidate` | Increment `times_invalidated` |

The validate/invalidate endpoints let the fencer tap "this was true" or "this was wrong" after a bout.

### Search

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/opponents/search?q=<name>` | Fuzzy name search |
| GET | `/api/opponents/filter?handedness=left&height=tall` | Trait filter |
| POST | `/api/opponents/lookup` | Batch: `{"names": ["JI Dylan", "KATZEL Charles"]}` |

### Pre-bout Intel

| GET | `/api/opponents/<id>/intel` | Consolidated intel package: profile, top tactical notes (by confidence), head-to-head record |

---

## 3. Fuzzy Opponent Matching

### The problem

Fencing names appear in many formats:
- `"SALIM Ethan"` (USFA convention: LAST First)
- `"Ethan Salim"` (natural order)
- `"SALIM, E."` (abbreviated)
- `"salim ethan"` (case variations)
- `"SALLIM Ethan"` (misspelling)

Club names also vary: `"AFM"` vs `"Academy of Fencing Masters"` vs `"Academy Fencing Masters"`.

### Match key: `(name, club)`

Both `PoolBout` and `EliminationRound` already capture `opponent_club` alongside `opponent_name`. Using both fields together drastically cuts false matches compared to name alone — two fencers with the same last name at different clubs are the common collision case.

### Solution: `thefuzz` library

Add `thefuzz` and `python-Levenshtein` to `requirements.txt`. Lightweight, no ML dependencies.

### Matching tiers (confidence-based)

```python
def match_opponent(query_name, query_club, threshold=70):
    1. Normalize both fields: strip, lowercase, remove commas/periods
    2. TIER 1 (auto-link): exact match on (canonical_name, club) case-insensitive
    3. TIER 2 (auto-link): fuzzy name match >= 85 AND exact club match
    4. TIER 3 (confirm in UI): fuzzy name >= 70 AND fuzzy club >= 70
       - Matches "AFM" vs "Academy of Fencing Masters" via club_aliases
    5. TIER 4 (confirm in UI): fuzzy name >= 80 AND club missing on one side
    6. NO MATCH: below thresholds -> offer "Create new opponent" with prefilled fields
```

### Name scoring (within each tier)

Score against `canonical_name` + every `name_alias` using the max of:
- `thefuzz.fuzz.ratio` (full string)
- `thefuzz.fuzz.token_sort_ratio` (order-independent — handles "SALIM Ethan" vs "Ethan Salim")
- `thefuzz.fuzz.partial_ratio` (substring — handles "SALIM, E." matching "SALIM Ethan")

### Club scoring

Same three-metric approach against `club` + `club_aliases`. A confirmed match auto-appends the observed spelling to `club_aliases` so future matches upgrade to Tier 1.

### Identical-name-same-club edge case

Rare but real (two fencers with the same name at the same club). Default behavior: merge into one opponent profile — styles and notes will still be mostly applicable. Add a "Split Opponent" tool later if it becomes a real problem.

### Performance

With < 1000 opponents, in-memory fuzzy matching is fast (< 100ms). No need for `pg_trgm` or other database extensions. Add a composite index on `(last_name, club)` for the Tier 1 lookup.

---

## 3b. Auto-Sync from Pool/DE Bouts

Every `PoolBout` and `EliminationRound` save triggers an opponent sync so head-to-head history builds itself instead of requiring manual re-entry.

### Flow

```python
def sync_bout_to_opponent(bout, bout_type, tournament):
    1. Match (bout.opponent_name, bout.opponent_club) using the tier system above
    2. If TIER 1 or 2 (auto-link):
       - Create BoutRecord(opponent_id=match.id, tournament_name, tournament_date,
                          bout_type, score_for, score_against, result)
       - Update opponent.last_encountered
    3. If TIER 3 or 4 (confirm):
       - Queue a pending_match row; user confirms from the tournament page
    4. If NO MATCH:
       - Auto-create Opponent stub (name + club only) and a BoutRecord
       - User can enrich the profile (traits, notes) later
```

### Where it hooks in

- `save_pool_bouts(...)` in `database.py` — after inserting each `PoolBout` row
- `save_elimination_rounds(...)` in `database.py` — after inserting each `EliminationRound` row
- Backfill command: a one-time script `backfill_bout_records.py` to sync all existing pool/DE rows into `BoutRecord`

### Why BoutRecord stays separate from PoolBout/EliminationRound

- `BoutRecord` is the opponent-centric view (one row per opponent-bout link); `PoolBout`/`EliminationRound` are the tournament-centric view
- Decoupling lets us keep the pool/DE schemas untouched and fix matching errors (merge/split opponents) without corrupting tournament data
- Stores `pool_bout_id` / `elimination_round_id` as nullable FKs for traceback; `NULL` means manually-entered historical bout

---

## 4. Mobile HTML UI

### `templates/opponents.html` -- Opponent List / Search Page

- **Search card at top:**
  - Text input for name search (fuzzy, debounced 300ms on keyup)
  - Expandable "Filter by traits" with dropdowns: Handedness, Height, Style, Speed
  - "Search" button
- **Results list:** Cards showing opponent name, club, trait badges (pills), mini head-to-head record (e.g., "2W-1L")
- **Floating "+" button** in bottom-right to add new opponent

### `templates/opponent_profile.html` -- Single Opponent

- **Profile card (editable):**
  - Name, Club, Division
  - Physical traits: Handedness, Height, Build (dropdowns)
  - Fencing traits: Speed, Primary Style, Secondary Style (dropdowns)
  - First/Last encountered dates
  - "Save Changes" button
- **Head-to-Head card:**
  - Summary line: "4 bouts across 3 tournaments — 2W-2L, +18/-15 touches"
  - Trend indicator: "Last 3: W-W-L"
  - Bout list **sorted newest-first**, **grouped by tournament** (pool + DE at the same event collapse under one header with date)
  - Each bout row: round (pool/DE), score, result
  - "Add Bout Result" button (for manually-entered historical bouts)
- **Tactical Notes card:**
  - Grouped by category (favorite_action, weakness, tell, what_worked, what_failed, general)
  - Each note shows: observation text, confidence badge, source badge
  - Validate/Invalidate buttons (thumbs up / thumbs down)
  - "Add Note" button per category
  - Inline edit and delete
- **"Delete Opponent" button** at bottom with confirmation

### `templates/opponent_intel.html` -- Pre-Bout Intel View

Optimized for quick reading on a phone between bouts:

- Large opponent name
- Head-to-head summary: "You're 2-1 against this fencer"
- **"WHAT WORKS"** (green) -- `what_worked` notes, sorted by confidence
- **"WATCH OUT FOR"** (orange/red) -- `favorite_action`, `tell` notes
- **"WEAKNESSES TO EXPLOIT"** (blue) -- `weakness` notes
- Physical summary: "Left-handed, tall, aggressive style, fast"
- Last encounter: "Last faced at NAC Chicago, Feb 2026 -- Won 5-3"
- Small "Edit Notes" link to full profile

### Pool/DE Lookup Flow

- **"Lookup Opponents" card** on opponents page
- Text area: "Paste or type opponent names (one per line)"
- "Lookup" button
- Results: matched opponents with confidence score, or "New opponent" with "Create Profile" button
- Matched opponents show mini intel card (clickable to full intel view)

### Navigation

Add "Opponent Intel" link to `index.html` alongside "View All Tips" and "Private Lessons".

---

## 5. Integration with Pool/DE Photo Extraction

When pool/DE photos are processed and opponent names extracted:

1. Call `lookup_opponents_by_names([list of extracted names])`
2. For each name:
   - If matched (fuzzy score >= 70): Show intel card with "View Intel" button
   - If no match: Show "New Opponent" with auto-filled name/club and "Create Profile" button
3. UI shows color-coded badges:
   - Green = known opponent, high-confidence match
   - Yellow = fuzzy match needs confirmation
   - Grey = unknown opponent

**Modify `/api/upload-pool-photo` endpoint:**

```python
# After extraction, add opponent lookup:
opponent_names = [bout['opponent_name'] for bout in pool_data['bouts']]
opponent_matches = lookup_opponents_by_names(opponent_names)

return jsonify({
    'success': True,
    'extracted_data': pool_data,
    'opponent_intel': opponent_matches  # NEW
})
```

Same pattern for `/api/upload-de-bracket`.

---

## 5b. FencingTracker Integration

Enrich opponent profiles with external data from FencingTracker.com. Their site has an undocumented JSON search API and detailed HTML profile pages we can scrape.

### Search API

POST `https://fencingtracker.com/search` (must use non-www domain — `www.` redirects strip the POST body):

```python
import requests

def search_fencing_tracker(name, limit=5):
    resp = requests.post(
        "https://fencingtracker.com/search",
        json={"query": name, "limit": limit},
        headers={"User-Agent": "Mozilla/5.0"}
    )
    return resp.json()
    # Returns: [{"club": "AFM", "name": "Ethan-Salim", "usfa_id": 100805112}, ...]
```

- Returns `name`, `club`, `usfa_id` for each match
- Partial name matching works (e.g., "Salim" matches "Salim", "Salima", etc.)
- Use the `usfa_id` to construct profile URLs

### Profile Data (HTML scrape)

Profile URL pattern: `https://www.fencingtracker.com/p/{usfa_id}/{First}-{Last}`

Three pages with useful data:

| Page | URL suffix | Data available |
|------|-----------|----------------|
| Summary | (none) | Club, division, weapon, ratings, podium finishes |
| History | `/history` | Win/loss stats (pool & DE), tournament list with placements, score analysis (easy wins, close bouts, big losses) |
| Strength | `/strength` | Numeric strength rating, confidence range, historical trend |

Parse with BeautifulSoup. Key fields to extract:
- **Win ratio** (pool and DE separately)
- **Recent tournament results** (name, date, placement, field size)
- **Strength rating** (DE and pool)
- **Score tendencies** (% easy wins, % close bouts, % big losses)

### Data flow

```
1. Opponent name from pool/DE extraction
   ↓
2. POST fencingtracker.com/search → get usfa_id + club
   ↓
3. Match to existing Opponent record (fuzzy match on name + club)
   ↓
4. Fetch /p/{usfa_id}/{Name}/history → parse stats
   ↓
5. Store usfa_id on Opponent model + cache scraped stats
```

### Model changes

Add to `Opponent` model:
```python
usfa_id = Column(Integer, index=True)           # FencingTracker/USFA ID
ft_strength_de = Column(Integer)                 # FencingTracker DE strength rating
ft_strength_pool = Column(Integer)               # FencingTracker pool strength rating
ft_win_ratio = Column(Float)                     # Overall win ratio from FT
ft_last_synced = Column(DateTime)                # When we last pulled FT data
```

### New endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/opponents/<id>/ft-lookup` | Search FencingTracker by opponent name, link usfa_id |
| POST | `/api/opponents/<id>/ft-sync` | Fetch latest stats from FencingTracker profile |
| GET | `/api/ft-search?q=<name>` | Proxy search to FencingTracker (avoids CORS from frontend) |

### UI integration

- **Opponent profile page**: "Link to FencingTracker" button → searches by name, shows matches, user picks correct one → saves `usfa_id`
- **Once linked**: Show FT stats card (strength rating, win ratio, recent results) on profile and intel pages
- **Auto-lookup**: When new opponents are created from pool/DE extraction, auto-search FencingTracker in the background and pre-link if there's a high-confidence single match (same name + same club)
- **Pre-bout intel page**: Show FT strength comparison (Ethan's rating vs opponent's)

### Caching

- Cache FT data on the Opponent record (`ft_last_synced`)
- Re-fetch at most once per day (or on manual "Refresh" tap)
- Avoids hammering FT on every page load

### Dependencies

Add `beautifulsoup4` and `lxml` to `requirements.txt` for HTML parsing.

---

## 5c. Final Results Photo Extraction

FencingTimeLive (`fencingtimelive.com`) publishes the complete standings of every tournament Ethan competes in. A screenshot of the Final Results page gives us:

- Ethan's final rank + total fencers in the event
- Top 4 podium (for tournament context)
- Every other competitor's name + club + division (seeds richer opponent match pool for future tournaments)

Reusing the existing Claude-Vision photo-extraction pipeline avoids building a scraper. Matches the current upload flow Ethan already knows from pool and DE brackets.

### Scope

**New endpoint** in `app.py`:
- `POST /api/upload-final-results` — multipart form accepting **one OR multiple images** (long fields are often split across several screenshots on iPhone). Claude Vision processes every uploaded image in one call and merges the extracted rows into a single sorted standings list, deduping any rows that appear in both (edge of one screenshot + start of next). Returns `{ethan_rank, total_fencers, podium: [...], full_field: [...]}`.
- `POST /api/confirm-final-results` — commits the extracted data to the tournament + opponent stubs

Follow the multi-image pattern already used by `/api/upload-de-bracket` + `extract_full_de_bracket` in `de_extraction.py` — the Vision prompt lists all images, asks for deduplicated rows, and flags suspected gaps (e.g. "rank 17–20 missing, possibly a scroll between screenshots").

**Database changes** (`database.py`):
- `Tournament` already has `final_rank` and maybe `total_fencers`; add the latter if missing
- `TournamentPodium` (new, small): `id`, `tournament_id` (indexed), `place` ("1", "2", "3T"), `opponent_name`, `opponent_club`, `division`, `country`
- Alternative: store podium as a JSON field on `Tournament` (simpler, no new table)

**Claude Vision prompt**: reuse the pattern from `extract_pool_sheet` / `extract_full_de_bracket`. Asks for:
- The fencer named "SALIM Ethan" → return their rank and the total count
- The top 4 places (1, 2, 3T, 3T) with name/club/division
- Optional: full field (all rows) if expanding to seed opponents

Return format:
```json
{
  "ethan_rank": "28T",
  "total_fencers": 36,
  "event_name": "Y-12 Men's Épée",
  "podium": [
    {"place": "1", "name": "JU Shang", "club": "Bayside Fencing Club", "division": "Central California"},
    {"place": "2", "name": "SAMOYLOV Daniel", "club": "Academy Of Fencing Masters (AFM)", "division": "Central California"},
    {"place": "3T", "name": "PARK Sihoon", "club": "LA International Fencing", "division": "Southern California"},
    {"place": "3T", "name": "KHUSHRAJ Rohan", "club": "Bayside Fencing Club", "division": "Central California"}
  ],
  "full_field": [ ... ]  // optional: every row
}
```

**UI** (`templates/tournament_detail.html`):
- "Upload Final Results" photo button next to existing "Upload Pool" / "Upload DE" buttons
- Extraction preview modal same pattern as pool/DE: shows extracted rank + podium + warnings, asks for Confirm
- After confirm: a new "Podium" card on the tournament page (1st / 2nd / 3T / 3T) plus Ethan's `final_rank of total_fencers` stat

**Opponent population**:
- Push `full_field` (if extracted) through `lookup_opponents_by_names` during confirm
- For each name with no match (tier None): auto-create a stub `Opponent` (same pattern as `sync_bout_to_opponent`) with `source` marker `"final_results_roster"` so we can distinguish from bout-sourced stubs
- For the 4 podium fencers: create or link their `Opponent` and flag them via a new `OpponentTacticalNote` (category `achievement`) like "Placed 3T at Y-12 2026-04-20 Central California event" — gives future intel readers context on who the threats are

### Tradeoff with §5b FencingTracker

- §5c is **simpler, manual, and single-event**: one screenshot per tournament
- §5b is **automated but higher-lift**: scraping two different page structures, name-matching against USFA IDs, daily cache invalidation
- They're complementary — §5c gets podium + Ethan's rank in a few minutes of work; §5b is the path to per-opponent strength ratings over time

Suggest shipping §5c first; revisit §5b when manual photo upload feels annoying or you want per-opponent DE strength.

### Out of scope (§5c)

- Extracting pool-round rank vs DE rank separately (the final rank is the combined DE placement)
- Cross-linking fencers across tournaments via last-name matching (opponent sync already handles that)
- Automatic upload — still a manual photo step

---

## 6. Cost Estimate

### Runtime cost

- **Fuzzy matching**: $0.00 -- runs entirely in Python
- **Opponent lookup from photos**: No additional API cost beyond photo extraction
- **New dependencies**: `thefuzz` and `python-Levenshtein` -- free, lightweight
- **Database**: No additional cost, same PostgreSQL/SQLite
- **Per tournament**: ~$0.01-0.02 (just photo extraction, same as before)

### New dependencies for `requirements.txt`

```
thefuzz
python-Levenshtein
beautifulsoup4
lxml
```

---

## 7. Implementation Sequence

**Phase 1 -- Foundation:** ✅ DONE
1. Add `Opponent`, `OpponentTacticalNote`, `BoutRecord` models to `database.py` ✅
2. Add all database helper functions ✅
3. Add `thefuzz` and `python-Levenshtein` to `requirements.txt` ✅
4. Implement fuzzy matching function ✅

**Phase 2 -- API layer:** ✅ DONE
5. Add all `/api/opponents/*` endpoints to `app.py` ✅
6. Add page-rendering routes (`/opponents`, `/opponents/<id>`, `/opponents/<id>/intel`) ✅

**Phase 3 -- UI:** ✅ DONE
7. Build `opponents.html` (list + search) ✅
8. Build `opponent_profile.html` (view/edit + notes) ✅
9. Build `opponent_intel.html` (pre-bout view) ✅
10. Add navigation link to `index.html` ✅

**Phase 4 -- Integration:** ⚠️ MOSTLY DONE
11. Wire `sync_bout_to_opponent` into `save_pool_results_to_db` + `save_de_results_to_db` ✅
12. Build "Confirm match" UI for Tier 3/4 pending matches ⏳ Pending
13. Write `backfill_bout_records.py` one-time script for existing pool/DE history ✅
14. Add opponent intel preview to pool/DE upload result pages ✅
14b. `backfill_opponent_names.py` to parse `first_name`/`last_name` from legacy rows ✅ (added after initial plan)

**Phase 5 -- Final Results Photo Extraction (§5c):** ⏳ Pending
15. Add `TournamentPodium` (or JSON field) + `total_fencers` to `Tournament`
16. `POST /api/upload-final-results` + `POST /api/confirm-final-results` with Claude Vision prompt
17. Upload button + preview modal + "Podium" card on `tournament_detail.html`
18. Auto-populate opponent stubs from `full_field`; flag top-4 with an `achievement` tactical note

**Phase 6 -- FencingTracker Integration (§5b):** ⏳ Pending
19. Add `usfa_id`, `ft_strength_de`, `ft_strength_pool`, `ft_win_ratio`, `ft_last_synced` to `Opponent`
20. Build FencingTracker search + scrape functions (search API, profile HTML parsing)
21. Add `/api/ft-search`, `/api/opponents/<id>/ft-lookup`, `/api/opponents/<id>/ft-sync` endpoints
22. Add "Link to FencingTracker" UI on opponent profile page
23. Auto-lookup FT on new opponent creation from pool/DE extraction
24. Show FT stats on pre-bout intel page with strength comparison

**Nice-to-have (post-MVP):** ⏳ Backlog
- Merge-two-opponents tool for near-duplicate stubs
- Club-alias auto-append on confirmed fuzzy matches
- Split-opponent tool for identical-name-same-club collisions

---

## Key Design Decisions

- **`thefuzz` over other approaches**: Handles fencing name variations (LAST First vs First Last, abbreviations, misspellings) without training data. `token_sort_ratio` is ideal for 2-3 token names in varying order.
- **`Text` for JSON columns**: Works on both SQLite (local) and PostgreSQL (production). Matches existing `advice_json` pattern.
- **Separate `BoutRecord` table**: Doesn't block on full tournament tracking implementation. Can be migrated later.
- **Server-rendered pages with vanilla JS**: Matches existing architecture. No framework overhead for a single-user app.

---

## Critical Files

- `database.py` -- Add 3 models + all helper functions
- `app.py` -- Add CRUD endpoints, search, lookup, intel, page routes
- `templates/opponents.html` -- List + search page
- `templates/opponent_profile.html` -- Profile view/edit + notes
- `templates/opponent_intel.html` -- Pre-bout intel (game-day view)
- `templates/index.html` -- Add navigation link
- `fencing_tracker.py` -- FencingTracker search API + profile scraper
- `requirements.txt` -- Add `thefuzz`, `python-Levenshtein`, `beautifulsoup4`, `lxml`
