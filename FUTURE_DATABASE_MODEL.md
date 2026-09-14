# Future Database Model for Tournament Tracking & ML Analysis

## Current Tables (Already Implemented)

### `sessions`
- id (primary key)
- date
- filename
- transcript
- advice_json

### `tips`
- id (primary key)
- category
- text
- created_at

---

## Proposed Additional Tables for Tournament Tracking

### `tournaments`
Stores information about each tournament

```sql
- id (primary key)
- name (e.g., "NAC Chicago 2024")
- location
- date
- weapon (foil/epee/sabre)
- age_category (e.g., "Y14", "Cadet", "Junior")
- level (e.g., "Regional", "National", "International")
- notes (optional text field)
```

### `pool_rounds`
Tracks performance in pool rounds

```sql
- id (primary key)
- tournament_id (foreign key → tournaments)
- pool_number
- position_in_pool (1st, 2nd, 3rd, etc.)
- victories
- defeats
- touches_scored
- touches_received
- indicator (touches_scored - touches_received)
- notes
```

### `pool_bouts`
Individual bouts within pool rounds

```sql
- id (primary key)
- pool_round_id (foreign key → pool_rounds)
- opponent_name
- opponent_club (optional)
- score_for (your son's score)
- score_against (opponent's score)
- result (won/lost)
- bout_order (1st bout, 2nd bout, etc.)
- notes (optional - specific observations)
```

### `elimination_rounds`
Direct elimination (DE) rounds

```sql
- id (primary key)
- tournament_id (foreign key → tournaments)
- round_name (e.g., "Table of 64", "Table of 32", "Table of 16", "Quarter-finals", "Semi-finals", "Finals")
- opponent_name
- opponent_club (optional)
- opponent_seed (optional)
- score_for
- score_against
- result (won/lost)
- final_placement (optional - e.g., "1st", "2nd", "Top 8")
- notes
```

### `tactical_observations`
Link specific tips/patterns to bouts for ML analysis

```sql
- id (primary key)
- bout_id (can link to pool_bouts OR elimination_rounds via polymorphic association)
- bout_type (enum: 'pool' or 'elimination')
- observation_category (links to tip categories: patience_and_control, when_ahead, etc.)
- what_happened (text description)
- was_successful (boolean)
- timestamp_in_bout (optional - when in the bout did this happen)
- related_tip_id (optional foreign key → tips)
```

### `performance_metrics`
Aggregate statistics for ML analysis

```sql
- id (primary key)
- tournament_id (foreign key → tournaments)
- total_bouts
- victories
- defeats
- win_rate
- average_score_for
- average_score_against
- average_point_differential
- comebacks (bouts won from behind)
- leads_lost (bouts lost from ahead)
- strong_starts (ahead after first 5 touches)
- strong_finishes (outscored opponent in final period)
- calculated_at (timestamp)
```

### `error_tracking`
Track specific recurring errors for coaching

```sql
- id (primary key)
- bout_id (polymorphic - pool or elimination)
- bout_type (enum: 'pool' or 'elimination')
- error_type (e.g., "forced_touch", "predictable_attack", "gave_up_lead", "poor_distance")
- score_when_happened (e.g., "3-2" to track if errors happen when ahead/behind)
- description
- related_tip_id (optional - which tip could have prevented this)
```

### `opponents`
Core opponent profiles with detailed tracking

```sql
- id (primary key)
- canonical_name (standardized name)
- first_name
- last_name
- name_aliases (JSONB - alternative spellings)
- club
- club_aliases (JSONB - historical clubs)
- division (e.g., "Central California")
- handedness (left/right/unknown)
- height_category (very_tall/tall/average/short/very_short)
- build (stocky/average/lean/athletic)
- speed_rating (very_fast/fast/average/slow)
- primary_style (aggressive/defensive/counter_attacker/distance_fighter/infighter/tactician)
- secondary_style
- style_confidence (0-1, confidence in style classification)
- photo_url
- photo_uploaded_at
- first_encountered (date)
- last_encountered (date)
- created_at
- updated_at
```

### `bout_opponents`
Links bouts to canonical opponent records (polymorphic)

```sql
- id (primary key)
- opponent_id (foreign key → opponents)
- bout_type (enum: 'pool' or 'elimination')
- pool_bout_id (foreign key → pool_bouts, nullable)
- elimination_round_id (foreign key → elimination_rounds, nullable)
- created_at
```

### `opponent_tactical_notes`
Tactical observations about opponents

```sql
- id (primary key)
- opponent_id (foreign key → opponents)
- bout_type (optional: 'pool' or 'elimination')
- pool_bout_id (optional foreign key → pool_bouts)
- elimination_round_id (optional foreign key → elimination_rounds)
- tournament_id (optional foreign key → tournaments)
- category (favorite_action/weakness/tell/what_worked/what_failed/physical_trait/mental_trait/general)
- observation (text)
- times_validated (how many times this held true)
- times_invalidated (how many times this was wrong)
- confidence_score (calculated: validated / (validated + invalidated))
- source (manual/voice_memo/ai_extracted/photo_note)
- voice_memo_id (optional foreign key → opponent_voice_memos)
- observed_at
- created_at
- updated_at
```

### `opponent_voice_memos`
Voice memos specifically about opponents

```sql
- id (primary key)
- opponent_id (foreign key → opponents)
- bout_type (optional: 'pool' or 'elimination')
- pool_bout_id (optional foreign key → pool_bouts)
- elimination_round_id (optional foreign key → elimination_rounds)
- tournament_id (optional foreign key → tournaments)
- filename
- file_path
- duration_seconds
- transcript
- transcribed_at
- extracted_observations (JSONB array of tactical notes)
- extraction_model (e.g., "claude-sonnet-4-6")
- extracted_at
- status (pending/transcribing/extracting/complete/failed)
- error_message
- recorded_at
- created_at
```

### `opponent_match_candidates`
Pending opponent matches from photo extraction

```sql
- id (primary key)
- extracted_name (name from photo)
- extracted_club (club from photo)
- photo_type (pool_sheet/bracket/results/other)
- tournament_id (foreign key → tournaments)
- matched_opponent_id (foreign key → opponents, nullable)
- match_confidence (0-1 confidence score)
- match_method (exact/fuzzy/club_match/manual)
- candidate_opponents (JSONB array of alternatives)
- status (pending/auto_matched/needs_review/confirmed/new_opponent/rejected)
- created_at
- resolved_at
```

### `bout_alerts`
Alerts for upcoming bouts against known opponents

```sql
- id (primary key)
- opponent_id (foreign key → opponents)
- tournament_id (foreign key → tournaments)
- round_type (pool/de_64/de_32/etc.)
- strip_number
- scheduled_time
- alert_title (e.g., "Facing Dylan JI - Pool Bout 3")
- head_to_head_summary (e.g., "1-2 record (last win: NAC 2024)")
- key_tactics (JSONB - top 3-5 tactical notes)
- recommended_tips (JSONB - relevant coaching tips)
- status (pending/shown/dismissed/completed)
- bout_type (filled after bout: pool/elimination)
- pool_bout_id (optional foreign key → pool_bouts)
- elimination_round_id (optional foreign key → elimination_rounds)
- created_at
- shown_at
- dismissed_at
```

### `opponent_head_to_head` (Materialized View)
Fast head-to-head lookups

```sql
- opponent_id
- canonical_name
- club
- handedness
- primary_style
- total_bouts
- wins
- losses
- total_touches_scored
- total_touches_received
- first_encounter (date)
- last_encounter (date)
```

---

## Relationships & Design Decisions

### Why This Structure?

1. **Hierarchical**: Tournament → Pool/DE Rounds → Individual Bouts
2. **Flexible**: Can track both pool and elimination bouts separately
3. **ML-Ready**: Structured data makes it easy to:
   - Calculate win rates in different scenarios
   - Track patterns (errors when ahead, success rates by opponent type)
   - Correlate tactical observations with outcomes
   - Identify which tips are most/least followed

4. **Coaching-Focused**: Links observations directly to tips for targeted improvement

### Key Design Patterns

**Polymorphic Associations**
- `tactical_observations` and `error_tracking` can link to either pool or elimination bouts
- Uses `bout_type` field to distinguish

**Denormalized Metrics**
- `performance_metrics` table stores calculated stats
- Improves query performance for ML analysis
- Recalculated after each tournament

---

## ML Analysis Possibilities

With this schema, you can analyze:

### Pattern Recognition
- **When do errors happen?**
  - When ahead vs behind
  - Early vs late in bout
  - First bout vs later bouts

- **Which tips are ignored?**
  - Compare tactical_observations with tips
  - Identify recurring mistakes linked to specific tip categories

### Performance Prediction
- **Tournament outcome prediction**
  - Based on pool performance, predict DE results
  - Compare opponent styles to past performance

### Tactical Analysis
- **What works?**
  - Success rate by tactical approach
  - Which tips correlate with wins
  - Best strategies against specific opponent types

### Progress Tracking
- **Improvement over time**
  - Win rate trends
  - Error reduction over tournaments
  - Tip adherence improvement

---

## Photo-Based Data Entry with Claude Vision

### Overview

Instead of manually typing pool results, you can take a photo of the pool sheet and let Claude Vision extract all the data automatically. This makes data entry fast and accurate - perfect for busy tournament days!

### How It Works

1. **Take a photo** of the pool results sheet (like the one showing Ethan's results)
2. **Upload to the app** via mobile interface
3. **Claude Vision analyzes** the image and extracts:
   - Pool number (e.g., "Pool #7")
   - Strip number (e.g., "Strip 13")
   - Fencer name and club (e.g., "SALIM Ethan - AFM / Central California")
   - All bout results against opponents with scores
   - Summary statistics (V, V/M, TS, TR, Indicator)
4. **Review and confirm** extracted data (edit if needed)
5. **Save to database** - all pool_rounds and pool_bouts records created automatically

### Example: From Your Photo

From Ethan's Pool #7 results, Claude Vision would extract:

**Pool Round Data:**
```json
{
  "pool_number": 7,
  "strip_number": 13,
  "fencer_name": "SALIM Ethan",
  "fencer_club": "AFM / Central California",
  "position_in_pool": 5,
  "victories": 1,
  "defeats": 4,
  "victory_rate": 0.20,
  "touches_scored": 19,
  "touches_received": 23,
  "indicator": -4
}
```

**Individual Bout Data:**
```json
{
  "bouts": [
    {
      "bout_order": 1,
      "opponent_name": "JI Dylan",
      "opponent_club": "LAIFC / Southern California",
      "score_for": 4,
      "score_against": 5,
      "result": "lost"
    },
    {
      "bout_order": 2,
      "opponent_name": "KATZEL Charles",
      "opponent_club": "EBFG / Northern California",
      "score_for": 4,
      "score_against": 5,
      "result": "lost"
    },
    {
      "bout_order": 3,
      "opponent_name": "CHO Lincoln",
      "opponent_club": "BAYFC / Central California",
      "score_for": 5,
      "score_against": 3,
      "result": "won"
    },
    {
      "bout_order": 4,
      "opponent_name": "ARULKUMAR Rihaan",
      "opponent_club": "BFA / Central California",
      "score_for": 4,
      "score_against": 5,
      "result": "lost"
    },
    {
      "bout_order": 5,
      "opponent_name": "LEUNG Joon",
      "opponent_club": "MFC / Central California",
      "score_for": 2,
      "score_against": 5,
      "result": "lost"
    }
  ]
}
```

### Implementation Code

```python
import base64
import json

def extract_pool_results_from_photo(image_path, tournament_id):
    """Extract pool results from a photo using Claude Vision API."""

    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # Determine image type
    ext = image_path.suffix.lower()
    if ext == '.jpg' or ext == '.jpeg':
        media_type = "image/jpeg"
    elif ext == '.png':
        media_type = "image/png"
    elif ext == '.webp':
        media_type = "image/webp"
    else:
        raise ValueError(f"Unsupported image format: {ext}")

    # Call Claude Vision API
    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
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
                    "content": """This is a photo of a fencing pool results sheet.
Extract the following information in JSON format:

{
  "pool_number": <number>,
  "strip_number": <number or null>,
  "fencer_name": "<highlighted fencer's full name>",
  "fencer_club": "<club abbreviation and location>",
  "position_in_pool": <final position number (1-6)>,
  "victories": <total V>,
  "defeats": <total number of bouts - V>,
  "victory_rate": <V/M ratio as decimal>,
  "touches_scored": <TS>,
  "touches_received": <TR>,
  "indicator": <Ind>,
  "bouts": [
    {
      "bout_order": <1-6>,
      "opponent_name": "<full name>",
      "opponent_club": "<club and location>",
      "score_for": <fencer's score>,
      "score_against": <opponent's score>,
      "result": "won" or "lost"
    }
  ]
}

IMPORTANT:
- The highlighted/main fencer is the one whose row is being tracked
- Extract ALL opponent bouts from that fencer's row
- V5 means Victory with score 5, D4 means Defeat with score 4
- Score format like "V5" against opponent means: fencer scored 5, look at opponent's cell for their score
- If you see D4 in the fencer's cell, it means the fencer lost scoring 4 points
- Calculate defeats as: total_bouts - victories
- Return null for any field that's unclear or unreadable"""
                }
            ],
        }],
    )

    # Parse JSON response
    try:
        result = json.loads(message.content[0].text)
    except json.JSONDecodeError:
        # Sometimes Claude wraps JSON in markdown code blocks
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())

    return result


def save_pool_results_to_db(tournament_id, pool_data):
    """Save extracted pool results to database."""
    db = get_db()

    try:
        # Create pool_round record
        pool_round = PoolRound(
            tournament_id=tournament_id,
            pool_number=pool_data['pool_number'],
            position_in_pool=pool_data['position_in_pool'],
            victories=pool_data['victories'],
            defeats=pool_data['defeats'],
            touches_scored=pool_data['touches_scored'],
            touches_received=pool_data['touches_received'],
            indicator=pool_data['indicator'],
            notes=f"Strip {pool_data['strip_number']}" if pool_data.get('strip_number') else None
        )
        db.add(pool_round)
        db.flush()  # Get the pool_round.id

        # Create pool_bout records for each opponent
        for bout in pool_data['bouts']:
            pool_bout = PoolBout(
                pool_round_id=pool_round.id,
                opponent_name=bout['opponent_name'],
                opponent_club=bout['opponent_club'],
                score_for=bout['score_for'],
                score_against=bout['score_against'],
                result=bout['result'],
                bout_order=bout['bout_order']
            )
            db.add(pool_bout)

        db.commit()
        return pool_round.id

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
```

### Flask API Endpoint

```python
@app.route('/api/upload-pool-photo', methods=['POST'])
def upload_pool_photo():
    """Handle pool results photo upload and extraction."""
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo uploaded'}), 400

    tournament_id = request.form.get('tournament_id')
    if not tournament_id:
        return jsonify({'error': 'Tournament ID required'}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Save photo temporarily
    filename = secure_filename(file.filename)
    filepath = app.config['UPLOAD_FOLDER'] / filename
    file.save(filepath)

    try:
        # Extract data from photo
        pool_data = extract_pool_results_from_photo(filepath, tournament_id)

        # Return extracted data for user confirmation
        # (Don't save to DB yet - let user review first)
        return jsonify({
            'success': True,
            'extracted_data': pool_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up uploaded photo
        if filepath.exists():
            filepath.unlink()


@app.route('/api/confirm-pool-results', methods=['POST'])
def confirm_pool_results():
    """Save confirmed pool results to database."""
    data = request.get_json()
    tournament_id = data.get('tournament_id')
    pool_data = data.get('pool_data')

    if not all([tournament_id, pool_data]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        pool_round_id = save_pool_results_to_db(tournament_id, pool_data)
        return jsonify({
            'success': True,
            'pool_round_id': pool_round_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### Mobile UI Flow

```html
<!-- Tournament page with photo upload -->
<div class="pool-entry">
    <h2>Add Pool Results</h2>

    <div class="upload-options">
        <label for="poolPhoto" class="upload-btn">
            📷 Take Photo of Pool Sheet
        </label>
        <input type="file" id="poolPhoto" accept="image/*" capture="environment">
    </div>

    <div id="extractedResults" style="display: none;">
        <h3>Confirm Pool Results</h3>
        <p class="instruction">Review and edit if needed:</p>

        <div class="pool-summary">
            <div class="field">
                <label>Pool #:</label>
                <input type="number" id="poolNumber" />
            </div>
            <div class="field">
                <label>Position:</label>
                <input type="number" id="position" />
            </div>
            <div class="field">
                <label>Record:</label>
                <span id="record">1V - 4D</span>
            </div>
            <div class="field">
                <label>Indicator:</label>
                <input type="number" id="indicator" />
            </div>
        </div>

        <div class="bout-results">
            <h4>Bout Results</h4>
            <div id="boutsList">
                <!-- Dynamically populated with extracted bouts -->
            </div>
        </div>

        <div class="actions">
            <button onclick="savePoolResults()" class="btn-primary">
                ✓ Confirm & Save
            </button>
            <button onclick="cancelPoolEntry()" class="btn-secondary">
                Cancel
            </button>
        </div>
    </div>
</div>
```

### Benefits

1. **Speed**: 10 seconds vs. 5 minutes of manual typing
2. **Accuracy**: No transcription errors
3. **Convenience**: Snap photo right after pool, enter data while waiting for DEs
4. **Complete Data**: Captures all opponent names and clubs automatically
5. **No Extra API Cost**: Uses existing Anthropic API key

### Cost Per Photo

- Claude Vision pricing: ~$3 per 1M input tokens
- Typical pool sheet photo: ~1,500 tokens
- **Cost per photo: ~$0.005 (half a cent)**
- Very affordable even for weekly tournaments!

### Handling Edge Cases

The system can handle:
- **Blurry photos**: Claude will flag uncertain fields as `null`
- **Partial results**: Works even if some bout scores aren't filled in yet
- **Different formats**: Adapts to various tournament software layouts
- **Handwritten notes**: Can read most handwriting in the notes section

### Extracting Final Tournament Rankings

Claude Vision can also extract final standings from tournament results pages like the one showing Ethan's 28th place finish:

```python
def extract_tournament_results_from_photo(image_path):
    """Extract final tournament standings from results photo."""

    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # Determine image type
    ext = image_path.suffix.lower()
    if ext in ['.jpg', '.jpeg']:
        media_type = "image/jpeg"
    elif ext == '.png':
        media_type = "image/png"
    else:
        media_type = "image/webp"

    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
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
                    "content": """This is a photo of final tournament standings/rankings.
Extract the following in JSON format:

{
  "tournament_name": "<full event name>",
  "weapon": "foil" | "epee" | "sabre",
  "age_category": "<e.g., Y-12, Y-14, Cadet, etc.>",
  "total_fencers": <number>,
  "fencer_result": {
    "name": "<fencer name if highlighted/specified>",
    "club": "<club name>",
    "division": "<division/region>",
    "final_placement": <place number>,
    "advanced_to_de": true | false
  },
  "notable_results": [
    {
      "placement": <1-3 for podium>,
      "name": "<fencer name>",
      "club": "<club>"
    }
  ]
}

If you cannot determine a specific fencer to focus on, set fencer_result to null.
Extract podium finishers (top 3) in notable_results."""
                }
            ],
        }],
    )

    # Parse response
    try:
        result = json.loads(message.content[0].text)
    except json.JSONDecodeError:
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())

    return result
```

**Example output from Ethan's results photo:**

```json
{
  "tournament_name": "Y-12 Men's Épée",
  "weapon": "epee",
  "age_category": "Y-12",
  "total_fencers": 47,
  "fencer_result": {
    "name": "SALIM Ethan",
    "club": "Academy Of Fencing Masters (AFM)",
    "division": "Central California",
    "final_placement": 28,
    "advanced_to_de": true
  },
  "notable_results": [
    {
      "placement": 1,
      "name": "CHAN Nathan",
      "club": "Academy Of Fencing Masters (AFM)"
    },
    {
      "placement": 2,
      "name": "JU Sheng",
      "club": "Bayside Fencing Club"
    },
    {
      "placement": 3,
      "name": "LO Stefan",
      "club": "Bayside Fencing Club"
    }
  ]
}
```

This data automatically populates:
- Tournament record with full metadata
- Final placement in `elimination_rounds` table
- Context about competition level (47 fencers)

### Extracting Direct Elimination (DE) Brackets

Claude Vision can extract DE bracket information from tournament bracket photos:

```python
def extract_de_results_from_photo(image_path):
    """Extract direct elimination bracket results from photo."""

    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = image_path.suffix.lower()
    if ext in ['.jpg', '.jpeg']:
        media_type = "image/jpeg"
    elif ext == '.png':
        media_type = "image/png"
    else:
        media_type = "image/webp"

    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3072,
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
                    "content": """This is a photo of a direct elimination (DE) fencing bracket.
Extract all bouts for a specific fencer (if identifiable) in JSON format:

{
  "fencer_name": "<target fencer name>",
  "fencer_club": "<club>",
  "initial_seed": <seed number>,
  "de_bouts": [
    {
      "round_name": "<e.g., Table of 64, Table of 32, Table of 16, etc.>",
      "opponent_name": "<full name>",
      "opponent_club": "<club>",
      "opponent_seed": <seed number>,
      "score_for": <fencer's score>,
      "score_against": <opponent's score>,
      "result": "won" | "lost",
      "referee": "<referee name if shown>",
      "time": "<time if shown>"
    }
  ]
}

IMPORTANT:
- Extract ALL bouts for the fencer from earliest to latest round
- Determine round names from bracket structure (Table of 64 = round of 64, Table of 32 = round of 32, etc.)
- Seed numbers are shown in parentheses like (36) or (#36)
- BYE means the fencer advanced without fencing
- Score format is typically "15-7" where first number is winner's score
- Look for highlighted or bolded names to identify the target fencer"""
                }
            ],
        }],
    )

    # Parse response
    try:
        result = json.loads(message.content[0].text)
    except json.JSONDecodeError:
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())

    return result
```

**Example output from Ethan's DE bracket:**

```json
{
  "fencer_name": "SALIM Ethan",
  "fencer_club": "AFM / Central California",
  "initial_seed": 36,
  "de_bouts": [
    {
      "round_name": "Table of 64",
      "opponent_name": "LUCAS Aiden",
      "opponent_club": "AFM / Central California",
      "opponent_seed": 29,
      "score_for": 15,
      "score_against": 7,
      "result": "won",
      "referee": "SIM Ian (BFA / Central California)",
      "time": null
    },
    {
      "round_name": "Table of 32",
      "opponent_name": "YI Alexander",
      "opponent_club": "SWORDSFS / Southern California",
      "opponent_seed": 4,
      "score_for": 7,
      "score_against": 15,
      "result": "lost",
      "referee": "LEUNG Dylan (MFC / Central California)",
      "time": "4:26 PM"
    }
  ]
}
```

### Saving DE Results to Database

```python
def save_de_results_to_db(tournament_id, de_data):
    """Save extracted DE results to database."""
    db = get_db()

    try:
        # Create elimination_round records for each bout
        for bout in de_data['de_bouts']:
            elim_round = EliminationRound(
                tournament_id=tournament_id,
                round_name=bout['round_name'],
                opponent_name=bout['opponent_name'],
                opponent_club=bout['opponent_club'],
                opponent_seed=bout.get('opponent_seed'),
                score_for=bout['score_for'],
                score_against=bout['score_against'],
                result=bout['result'],
                notes=f"Ref: {bout['referee']}" if bout.get('referee') else None
            )
            db.add(elim_round)

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
```

### Key Insights from Ethan's DE Bracket

From this bracket photo, we can extract valuable tactical information:

1. **Strong First Round Performance**: 15-7 victory shows confidence
2. **Clubmate Matchup**: Beat Lucas Aiden (also AFM) - familiarity helped
3. **Tough Draw**: Faced #4 seed YI Alexander in Table of 32
4. **Competitive Loss**: 7-15 against top seed - respectable score
5. **Tournament Progress**: Made it to Table of 32 (top 32 out of 47)

### Analytics Opportunities

With DE bracket data, you can analyze:
- **Seed Performance**: How does Ethan perform vs. higher/lower seeds?
- **Score Patterns**: Does he start strong or finish strong in DE bouts?
- **Club Matchups**: Performance against clubmates vs. unknowns
- **Upset Potential**: When does he beat higher seeds?
- **Consistency**: Score differentials in wins vs. losses

### Combined Pool + DE Analysis

When you have both pool and DE results from photos, the system can:
1. Track progression from pool seeding → DE performance
2. Identify if pool performance predicts DE success
3. Compare tactical execution in pools vs. high-pressure DE bouts
4. Link coaching tips to specific bout outcomes

**Example Analysis:**
- Pool: 1V-4D, 28th seed → needed strong DE performance
- DE R64: Decisive 15-7 win → executed game plan well
- DE R32: Competitive 7-15 loss to #4 → held his own against top opponent

This type of context helps identify: "Ethan performs better in DE pressure situations than in pools"

### Future Enhancement: Video Extraction

Could also extract pool results from a video walkthrough where you:
1. Record a video panning across the pool sheet
2. Claude Vision analyzes video frames
3. Extracts complete results from multiple pools in one video

---

## Opponent Intelligence System

### Overview

The opponent intelligence system tracks every opponent Ethan faces, capturing their fighting style, physical characteristics, tactical patterns, and what works/doesn't work against them. When he faces them again, the system provides pre-bout alerts with key intel.

### Key Features

1. **Automatic Opponent Recognition**: When pool sheets/brackets are photographed, the system matches opponent names to existing database records
2. **Tactical Notes**: Capture observations about opponents (what worked, weaknesses, tells, favorite actions)
3. **Voice Memos**: Record quick post-bout notes that get transcribed and analyzed
4. **Pre-Bout Alerts**: When facing a known opponent, get instant reminders of previous encounters and key tactics
5. **Head-to-Head Statistics**: Track record against each opponent, point differentials, and trends
6. **ML Insights**: Analyze performance patterns against different styles, identify improvement trends

### How It Works

#### 1. Photo-Based Opponent Detection

When you upload a pool sheet photo:

```python
def extract_and_match_opponents(image_path, tournament_id):
    """Extract pool data and match opponents to database."""

    # Step 1: Extract pool results (existing functionality)
    pool_data = extract_pool_results_from_photo(image_path)

    # Step 2: For each opponent, find matches in database
    for bout in pool_data['bouts']:
        matches = NameMatcher().find_matches(
            name=bout['opponent_name'],
            club=bout['opponent_club']
        )

        if matches and matches[0]['confidence'] > 0.85:
            # High confidence match - auto-link and generate alert
            link_bout_to_opponent(bout, matches[0]['opponent_id'])
            generate_pre_bout_alert(matches[0]['opponent_id'], tournament_id)
        else:
            # Low confidence - flag for review
            create_match_candidate(bout, matches, tournament_id)
```

**Name Matching Algorithm**:
- Normalizes names ("JI Dylan" vs "Dylan JI")
- Uses fuzzy string matching (Levenshtein distance)
- Phonetic matching for first names
- Club-based disambiguation
- Confidence scoring (0-1)

#### 2. Pre-Bout Alerts

When a known opponent is detected in pools/brackets:

```
+--------------------------------------------------+
| [!] OPPONENT INTEL: Dylan JI                     |
|--------------------------------------------------|
| HEAD TO HEAD: 1 win, 2 losses                   |
| Last faced: NAC Chicago (Feb 2024) - Lost 4-5  |
| Trend: You've improved (losses getting closer)  |
|                                                  |
| STYLE: Aggressive counter-attacker              |
| Physical: Tall, right-handed, very fast         |
|                                                  |
| KEY TACTICS:                                     |
| ✓ Stay patient, let him attack first (works 70%)|
| ✓ Short attacks when he's advancing             |
| ⚠ Struggles with infighting (his weakness)      |
| ℹ Bounces before big attacks (tell)             |
|                                                  |
| REVIEW TIPS: [Patience] [Distance Management]   |
|                                                  |
| [GOT IT]        [ADD NOTE]          [FULL INFO]  |
+--------------------------------------------------+
```

Alert automatically includes:
- Head-to-head record and trend
- Most reliable tactical notes (sorted by confidence)
- What worked in last encounter
- Opponent's style and physical traits
- Relevant coaching tips to review

#### 3. Post-Bout Voice Memos

After a bout, record quick tactical observations:

```python
def process_opponent_voice_memo(audio_file, opponent_id, bout_id):
    """Process voice memo about an opponent."""

    # Step 1: Transcribe with Whisper
    transcript = openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )

    # Step 2: Extract tactical observations with Claude
    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{
            "role": "user",
            "content": f"""
            This is a voice memo recorded after a fencing bout.

            Transcript: {transcript}

            Extract tactical observations about the opponent.
            Categorize each as:
            - favorite_action: Actions they love to do
            - weakness: Things they struggle with
            - tell: Predictive patterns
            - what_worked: Things that worked against them
            - what_failed: Things that didn't work
            - physical_trait: Physical observations
            - mental_trait: Mental/psychological notes

            Return JSON array of observations with category and text.
            """
        }]
    )

    # Step 3: Store extracted notes for user review
    extracted_notes = parse_claude_response(message)

    return extracted_notes
```

**Example extraction**:

Voice memo: *"Dylan was really aggressive today, kept bouncing before his big attacks. When I stayed patient and let him come to me, I could counter him easily. But when I tried to attack directly, he got me every time. He's definitely weak when I close the distance quickly."*

Extracted notes:
```json
[
  {
    "category": "tell",
    "observation": "Bounces before big attacks",
    "confidence": 0.8
  },
  {
    "category": "what_worked",
    "observation": "Stay patient and let him attack first, then counter",
    "confidence": 0.9
  },
  {
    "category": "what_failed",
    "observation": "Direct attacks don't work",
    "confidence": 0.9
  },
  {
    "category": "weakness",
    "observation": "Weak when opponent closes distance quickly",
    "confidence": 0.7
  }
]
```

#### 4. Tactical Note Confidence Tracking

Each tactical note tracks how often it's been validated:

```sql
-- Example: "Stay patient, let him attack first"
times_validated: 2      -- Worked twice
times_invalidated: 0    -- Never failed
confidence_score: 1.0   -- 2/(2+0) = 100% reliable
```

When you face the opponent again:
- Mark notes as validated (it worked again) or invalidated (it didn't work this time)
- Confidence scores update automatically
- Most reliable tactics float to the top

#### 5. Opponent Profile Page

```
+--------------------------------------------------+
|         OPPONENT PROFILE: Dylan JI               |
|--------------------------------------------------|
| [PHOTO]    Dylan JI                              |
|            LAIFC / Southern California           |
|            Right-handed | Tall | Fast            |
|                                                  |
| FIGHTING STYLE                                   |
| Primary: Counter-attacker                        |
| Secondary: Aggressive                            |
|                                                  |
| HEAD TO HEAD                    [See All Bouts]  |
| +--------+--------+--------+                     |
| | WINS   | LOSSES | WIN %  |                     |
| |   1    |   2    |  33%   |                     |
| +--------+--------+--------+                     |
|                                                  |
| TREND: ↗ Improving (last 3: L L W)              |
|                                                  |
| BOUT HISTORY                                     |
| Dec 2024 NAC  | Pool  | W 5-3  | [View Notes]    |
| Nov 2024 SYC  | Pool  | L 4-5  | [View Notes]    |
| Oct 2024 RC   | DE-32 | L 8-15 | [View Notes]    |
|                                                  |
| TACTICAL NOTES (by confidence)                   |
| ✓ Stay patient, let him attack first            |
|   Validated: 2x | Confidence: 100%              |
| ✓ Short attacks when advancing                   |
|   Validated: 1x | Confidence: High              |
| ⚠ Struggles with infighting                     |
|   Not yet validated                             |
| ℹ Bounces before big attacks                     |
|   Observed: 1x | Confidence: Low                |
|                                                  |
| VOICE MEMOS (2 total)                            |
| Dec 2024 NAC - 0:45 - [PLAY] [TRANSCRIPT]       |
| Oct 2024 RC  - 1:12 - [PLAY] [TRANSCRIPT]       |
|                                                  |
| [EDIT PROFILE]  [+ ADD NOTE]  [RECORD MEMO]      |
+--------------------------------------------------+
```

### ML-Powered Insights

#### Style Analysis

Analyzes win rates against different opponent styles:

```python
{
  "overall_win_rate": 0.60,
  "style_breakdown": [
    {"style": "defensive", "win_rate": 0.75, "bouts": 8},
    {"style": "aggressive", "win_rate": 0.55, "bouts": 11},
    {"style": "counter_attacker", "win_rate": 0.30, "bouts": 10}
  ],
  "best_against": ["defensive"],
  "struggles_against": ["counter_attacker"],
  "recommendations": [
    "Practice more against counter-attackers (only 30% win rate)",
    "Your patience tips work well against defensive opponents"
  ]
}
```

#### Improvement Trends

Tracks if Ethan improves against repeat opponents:

```python
{
  "repeat_opponents_analyzed": 5,
  "improving_against": 3,
  "declining_against": 1,
  "improvement_rate": 0.60,
  "details": [
    {
      "opponent": "Dylan JI",
      "times_faced": 3,
      "trend": "improving",
      "first_half_wr": 0.0,
      "second_half_wr": 0.5
    }
  ]
}
```

#### Bout Difficulty Prediction

Predicts how challenging an upcoming bout will be:

```python
{
  "opponent": "Dylan JI",
  "difficulty_score": 0.65,
  "difficulty_rating": "Challenging",
  "factors": {
    "h2h_record": 0.67,        # Lost 2 of 3
    "style_matchup": 0.70,     # Struggles vs counter-attackers
    "physical": 0.60,          # Tall opponent, slight disadvantage
    "trend": "improving"        # But getting better against him
  },
  "recommendation": "Challenging bout but trend is positive. Focus on patience and distance management tactics that worked last time."
}
```

### Integration with Photo Extraction

The opponent system integrates seamlessly with existing photo extraction:

**1. Upload Pool Sheet Photo**
   - Claude Vision extracts pool data (already designed)
   - For each opponent: name, club, score

**2. Automatic Opponent Matching**
   - System checks each opponent name against database
   - High confidence matches (>85%): Auto-link, generate alert
   - Low confidence matches (<85%): Flag for review

**3. User Confirmation Screen**
   ```
   MATCHED (auto-linked):
   ✓ Dylan JI (LAIFC) - 95% confident [1-2 record]

   NEEDS REVIEW:
   ? "C. KATZEL" (EBFG)
     Did you mean: Charles KATZEL (72%) or Chris KATZ (45%)?
     [Select Match] [Create New]

   NEW OPPONENTS:
   + Lincoln CHO (BAYFC) - Not in database
     [Create Profile] [Skip]
   ```

**4. Alerts Generated**
   - For each known opponent: Pre-bout alert created
   - Alerts appear when viewing pool/bracket
   - Include H2H stats, tactics, recommended tips

### API Endpoints

```python
# Opponent Management
GET    /api/opponents                      # List all opponents
GET    /api/opponents/<id>                 # Get opponent profile
POST   /api/opponents                      # Create opponent
PUT    /api/opponents/<id>                 # Update opponent
POST   /api/opponents/<id>/merge           # Merge duplicates

# Tactical Notes
GET    /api/opponents/<id>/notes           # Get tactical notes
POST   /api/opponents/<id>/notes           # Add note
POST   /api/opponents/<id>/notes/<id>/validate  # Validate/invalidate note

# Voice Memos
POST   /api/opponents/<id>/voice-memo      # Upload voice memo
GET    /api/voice-memos/<id>/status        # Check processing status
POST   /api/voice-memos/<id>/confirm       # Confirm extracted notes

# Alerts
POST   /api/alerts/check                   # Check for opponent matches
GET    /api/alerts/active                  # Get active alerts
GET    /api/alerts/<id>                    # Get full alert details
POST   /api/alerts/<id>/dismiss            # Dismiss alert

# ML Insights
GET    /api/insights/style-analysis        # Win rate by opponent style
GET    /api/insights/opponent-trend/<id>   # Trend vs specific opponent
GET    /api/insights/difficulty/<tournament_id>  # Predict bout difficulty
GET    /api/insights/improvement           # Overall improvement analysis
```

### Database Schema

See updated opponent tables above:
- `opponents`: Core opponent profiles
- `bout_opponents`: Links bouts to opponents
- `opponent_tactical_notes`: Observations and tactics
- `opponent_voice_memos`: Post-bout voice recordings
- `opponent_match_candidates`: Pending photo matches
- `bout_alerts`: Pre-bout intelligence alerts
- `opponent_head_to_head`: Materialized view for H2H stats

### Implementation Phases

**Phase 1: Core Tracking** (Essential)
- Database tables for opponents and tactical notes
- Manual opponent entry and profile viewing
- Link bouts to opponents manually

**Phase 2: Photo Integration** (High Priority)
- Name matching algorithm
- Auto-detect opponents from pool photos
- Match confirmation UI

**Phase 3: Alerts** (High Priority)
- Generate pre-bout alerts
- Display alerts with H2H and tactics
- Link to relevant coaching tips

**Phase 4: Voice Memos** (Medium Priority)
- Record post-bout observations
- Transcribe and extract tactics
- Review/confirm extracted notes

**Phase 5: ML Insights** (Nice to Have)
- Style performance analysis
- Improvement trend tracking
- Bout difficulty prediction

### Cost Considerations

**Per Tournament (typical)**:
- Pool sheet photo: ~$0.005 (Claude Vision)
- DE bracket photo: ~$0.005 (Claude Vision)
- 2-3 voice memos: ~$0.015 (Whisper + Claude)
- **Total per tournament: ~$0.03 (3 cents)**

Very affordable even for weekly tournaments!

---

## Migration Path

### Phase 1 (Current)
- ✅ Tips and coaching sessions

### Phase 2 (Next)
- Add tournament tracking tables
- Simple data entry forms (tournament results)

### Phase 3
- Add tactical observations during/after bouts
- Link observations to existing tips

### Phase 4
- Build ML analysis dashboard
- Automated pattern recognition
- Predictive insights

---

## Example Queries for ML Analysis

### Find most common errors when ahead
```python
errors_when_ahead = db.query(ErrorTracking).filter(
    ErrorTracking.score_when_happened.like('%ahead%')
).group_by(ErrorTracking.error_type).all()
```

### Calculate success rate when following specific tip category
```python
tactical_obs = db.query(TacticalObservation).filter(
    TacticalObservation.observation_category == 'patience_and_control',
    TacticalObservation.was_successful == True
).count()
```

### Identify strongest/weakest parts of tournament
```python
# Pool vs DE performance comparison
pool_win_rate = calculate_win_rate(pool_bouts)
de_win_rate = calculate_win_rate(elimination_rounds)
```

---

## Implementation Priority

1. **Essential for tournament tracking:**
   - tournaments
   - pool_rounds, pool_bouts
   - elimination_rounds

2. **Important for analysis:**
   - tactical_observations
   - error_tracking
   - performance_metrics

3. **Nice to have:**
   - opponent_analysis

Start simple, add complexity as needed!

---

## Alternative: Simpler Model

If you want to start even simpler:

```sql
tournaments (id, name, date, location)
bouts (id, tournament_id, opponent, score_for, score_against, round_type, notes)
observations (id, bout_id, category, description, successful)
```

This minimal version still allows basic ML analysis while being easier to implement.

---

Would you like me to implement this database model now, or wait until you're ready to add tournament tracking?
