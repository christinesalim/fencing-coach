# Pool Bout Upload — Complete Flow

This document traces the full lifecycle of uploading a pool sheet photo, from the user tapping "Upload" to the data being saved and opponents linked.

## Overview Diagram

```mermaid
sequenceDiagram
    participant User as User (iPhone)
    participant JS as Frontend JS
    participant Flask as Flask (app.py)
    participant Claude as Claude Vision API
    participant Fuzzy as Fuzzy Matching
    participant DB as Database
    participant R2 as Cloudflare R2
    participant Sync as Opponent Sync

    Note over User,Sync: Phase 1 — Upload & Extract
    User->>JS: Taps "Upload Pool Sheet Photo"
    JS->>Flask: POST /api/upload-pool-photo (photo + tournament_id)
    Flask->>Flask: Save photo to uploads/ folder
    Flask->>Claude: Send base64 image + pool grid reading prompt
    Claude-->>Flask: JSON {pool_number, victories, bouts: [...]}
    Flask->>Flask: Delete temp photo file
    Flask->>Fuzzy: Match each opponent name against Opponent table
    Fuzzy-->>Flask: Tier 1-4 matches or "new"
    Flask-->>JS: {extracted_data, opponent_intel}

    Note over User,Sync: Phase 2 — Review & Confirm
    JS->>User: Show editable form with bouts, scores, opponent badges
    User->>User: Fix names, scores, confirm/reject fuzzy matches
    User->>JS: Taps "Confirm & Save"

    Note over User,Sync: Phase 3 — Save & Sync
    JS->>Flask: POST /api/confirm-pool-results (pool_data + confirm_decisions)
    Flask->>DB: Create/update PoolRound + PoolBout rows
    DB-->>Flask: Committed with bout IDs

    loop For each bout
        Flask->>Sync: sync_bout_to_opponent(bout_data)
        Sync->>Fuzzy: Match opponent name + club
        alt Tier 1/2 or user confirmed
            Sync->>DB: Link BoutRecord to existing Opponent
        else No match
            Sync->>DB: Create stub Opponent + BoutRecord
        end
    end

    Flask-->>JS: {success, opponent_intel}
    JS->>User: Page reloads with saved results
```

## Files Involved

```mermaid
graph LR
    subgraph Frontend
        T[tournament_detail.html]
    end

    subgraph "Flask Routes (app.py)"
        Upload["/api/upload-pool-photo<br/>line 941"]
        Confirm["/api/confirm-pool-results<br/>line 1084"]
        Extract["extract_pool_results_from_photo()<br/>line 738"]
        Preview["_build_preview_opponent_intel()<br/>line 1721"]
    end

    subgraph "Database (database.py)"
        Save["save_pool_results_to_db()<br/>line 838"]
        Get["get_pool_results()<br/>line 877"]
        SyncFn["sync_bout_to_opponent()<br/>line 2475"]
    end

    subgraph "Fuzzy Matching"
        Match["match_opponent()<br/>fuzzy_matching.py:96"]
    end

    subgraph External
        Claude[Claude Vision API]
    end

    T -->|photo upload| Upload
    Upload --> Extract
    Extract --> Claude
    Upload --> Preview
    Preview --> Match
    T -->|confirm & save| Confirm
    Confirm --> Save
    Save --> SyncFn
    SyncFn --> Match
    T -->|page load| Get
```

## Database Models

```mermaid
erDiagram
    Tournament ||--o| PoolRound : "has one"
    PoolRound ||--|{ PoolBout : "contains"
    PoolBout ||--o{ BoutVideo : "has clips"
    PoolBout ||--o| BoutRecord : "synced to"
    BoutRecord }o--|| Opponent : "linked to"

    Tournament {
        int id PK
        string name
        date date
        string weapon
        string age_category
    }

    PoolRound {
        int id PK
        int tournament_id FK
        int pool_number
        int position_in_pool
        int victories
        int defeats
        int touches_scored
        int touches_received
        int indicator
    }

    PoolBout {
        int id PK
        int pool_round_id FK
        string opponent_name
        string opponent_club
        int score_for
        int score_against
        string result
        int bout_order
    }

    BoutRecord {
        int id PK
        int opponent_id FK
        int tournament_id
        int pool_bout_id FK
        string bout_type
        int score_for
        int score_against
        string result
    }

    BoutVideo {
        int id PK
        string bout_kind
        int bout_id FK
        string r2_key
    }

    Opponent {
        int id PK
        string canonical_name
        string club
        string club_aliases
    }
```

## Step-by-Step Detail

### 1. Photo Upload (`app.py:941`)

User selects a photo on iPhone. JS sends it as multipart form data:

```
POST /api/upload-pool-photo
Content-Type: multipart/form-data
- photo: [image file]
- tournament_id: 5
```

The endpoint saves the file to `uploads/`, calls `extract_pool_results_from_photo()`, then deletes the temp file in a `finally` block (both success and error paths).

### 2. Claude Vision Extraction (`app.py:738`)

The photo is base64-encoded and sent to `claude-sonnet-4-6` with `max_tokens=2048`. The prompt (`app.py:785-854`) explains:
- How to read a fencing pool grid (rows = fencers, columns = bout results)
- D4 means the row fencer lost and scored 4 touches
- V5 means the row fencer won and scored 5 touches
- How to handle empty, partial, and complete pool sheets
- Extract from SALIM Ethan's row only

Returns JSON with `pool_number`, `victories`, `defeats`, `indicator`, and a `bouts` array with each opponent's name, club, and score.

### 3. Opponent Preview (`app.py:1721`)

Before showing results to the user, each opponent name is fuzzy-matched against the existing `Opponent` table using `thefuzz` (4-tier system in `fuzzy_matching.py`):

| Tier | Confidence | Criteria | Action |
|------|-----------|----------|--------|
| 1 | Exact | Exact name + exact club | Auto-link |
| 2 | High | Name >= 85 + exact club | Auto-link |
| 3 | Medium | Name >= 70 + club >= 70 | Show confirm button |
| 4 | Low | Name >= 80 + one club missing | Show confirm button |
| None | — | Below thresholds | Create new |

### 4. User Review (Frontend JS)

`populateExtractedResults()` renders an editable form with:
- Each bout as a card with editable name, club, score fields
- Intel badges: green (known), yellow with Yes/No buttons (confirm?), grey (new)
- User can fix OCR errors before saving

### 5. Confirm & Save (`database.py:838`)

`save_pool_results_to_db()` handles both first upload and re-upload:

**First upload:** Creates new `PoolRound` + `PoolBout` rows.

**Re-upload (updating scores):** Matches incoming bouts to existing `PoolBout` rows by opponent name (case-insensitive). Updates scores in place, preserving the same `bout_id` — this keeps `BoutVideo` clips attached.

### 6. Opponent Sync (`database.py:2475`)

After pool data is committed, each bout is synced to an `Opponent` record:

```mermaid
flowchart TD
    A[Bout saved to DB] --> B{User confirmed match?}
    B -->|Yes - force_opponent_id set| C[Link to confirmed Opponent]
    B -->|No| D{Fuzzy match result?}
    D -->|Tier 1 or 2| E[Auto-link to matched Opponent]
    D -->|Tier 3, 4, or None| F[Create stub Opponent]
    C --> G[Create BoutRecord]
    E --> G
    F --> G
    G --> H[Update opponent encounter dates]
```

The sync runs outside the main DB transaction — if it fails, the pool data is still saved. Each sync creates a `BoutRecord` that links the `PoolBout` to an `Opponent`, enabling the head-to-head view on opponent profiles.

### 7. Re-upload Flow

```mermaid
flowchart LR
    A[Empty pool sheet] -->|"Upload: names only"| B[PoolRound + PoolBouts created<br/>scores = null]
    B -->|"Upload video clips"| C[BoutVideos attached<br/>by bout_id]
    C -->|"Upload complete pool sheet"| D[Scores updated in place<br/>same bout_id = videos preserved]
```

Key: the `bout_id` stays the same across re-uploads, so video clips remain attached to the correct opponent's bout.
