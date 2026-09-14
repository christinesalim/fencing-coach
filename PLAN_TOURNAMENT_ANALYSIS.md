# Tournament Analysis Features - Implementation Plan

## Overview

Three separate features, each serving a different moment:
1. **Quick DE Prep Tips** — 5 actionable tips right after pools, read on phone at the tournament
2. **Practice Drills** — Drills linked to tournament issues, for training sessions
3. **Full Post-Tournament Analysis** — Deep tactical breakdown for review at home

---

## Feature 1: Quick DE Prep Tips

### Database Model

```python
class DEPrepTips(Base):
    __tablename__ = 'de_prep_tips'
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)
    tips_json = Column(Text)          # JSON array of 5 tip objects
    generated_at = Column(DateTime, default=datetime.utcnow)
```

Each tip structure:
```json
[
  {"priority": 1, "category": "finishing", "tip": "You lost three bouts 5-4..."},
  {"priority": 2, "category": "mental", "tip": "..."}
]
```

### Claude Prompt

```
You are Coach Ziad's assistant analyzing pool results for Ethan, a Y-12 epee fencer, right before his Direct Elimination (DE) rounds.

Tournament: {tournament_name}
Date: {tournament_date}

Pool Results:
Record: {victories}V-{defeats}D | Indicator: {indicator} | TS: {ts} | TR: {tr}

Individual Bouts:
{for each bout: "vs {opponent_name} ({opponent_club}): {score_for}-{score_against} {result}"}

Generate exactly 5 short, actionable tips for Ethan to use in the upcoming DE rounds. These will be read quickly on a phone between rounds at the tournament.

Rules:
- Analyze PATTERNS in the scores (close losses, blowouts, comfortable wins, scoring trends)
- Use epee-specific terminology (no right-of-way in epee; focus on: distance, timing, point control, remise, counter-attack, fleche, single-light touches)
- Be specific to what the data shows — do NOT give generic advice
- Each tip must be 1-2 sentences maximum, written as a direct instruction
- Order by importance (most critical first)
- Assign each tip a category: "finishing" (closing out close bouts), "distance" (blade/foot distance), "timing" (tempo/patience), "mental" (focus/composure), "defense" (avoiding touches), "tactical" (strategy/patterns)

Return JSON array:
[
  {"priority": 1, "category": "<category>", "tip": "<specific actionable tip>"},
  {"priority": 2, "category": "<category>", "tip": "<specific actionable tip>"},
  {"priority": 3, "category": "<category>", "tip": "<specific actionable tip>"},
  {"priority": 4, "category": "<category>", "tip": "<specific actionable tip>"},
  {"priority": 5, "category": "<category>", "tip": "<specific actionable tip>"}
]
```

### API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/tournaments/<id>/de-prep-tips` | Generate DE prep tips from pool data |
| GET | `/api/tournaments/<id>/de-prep-tips` | Retrieve saved tips |

### UI Design

On `tournament_detail.html`, positioned directly below Pool Results card:

- **When pool data exists but no tips**: "Generate DE Prep Tips" button (prominent, `btn-primary`)
- **When tips exist**: White card with 5 color-coded tips:
  - Left border color by category: green=finishing, blue=distance, orange=timing, red=mental, purple=defense, teal=tactical
  - Priority number as bold circle
  - Tip text in 15px for phone readability
  - Small category label pill
- **Regenerate link** at bottom for re-generating after pool edits

### Trigger Behavior

Tips are NOT auto-generated on pool save (to avoid delays during a tournament). After pool results are confirmed, the "Generate DE Prep Tips" button appears. One tap generates them.

---

## Feature 2: Practice Drills Section

### Database Model

```python
class Drill(Base):
    __tablename__ = 'drills'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    helps_with = Column(Text)           # what issue this addresses
    category = Column(String(30))       # distance/timing/mental/finishing/defense/footwork/point_control
    difficulty = Column(String(15))     # beginner/intermediate/advanced
    duration_minutes = Column(Integer)
    source = Column(String(20), default='ai')  # 'ai' or 'manual'
    tournament_id = Column(Integer, index=True)  # which tournament triggered this (nullable)
    tournament_context = Column(Text)   # "Recommended because: you lost three 5-4 bouts at..."
    practiced_at = Column(DateTime)     # null = not practiced yet
    practice_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Claude Prompt

```
You are a fencing coach designing practice drills for Ethan, a Y-12 epee fencer. His coach is Ziad.

Analyze Ethan's tournament results and recommend specific practice drills to address weaknesses.

Tournament: {tournament_name} ({tournament_date})
Pool Results: {victories}V-{defeats}D | Indicator: {indicator}

Bouts:
{bout details}

{if previous_tournaments exist:}
Previous Tournament Patterns:
{summary of recent tournaments' records and indicators}

Design 4-6 practice drills. Each drill should:
- Target a SPECIFIC issue visible in the results
- Be appropriate for a Y-12 epee fencer
- Be something Ethan can practice with Coach Ziad or at home
- Use real fencing drill names/formats where possible

Return JSON array:
[
  {
    "name": "<drill name, e.g. 'Last Touch Pressure Drill'>",
    "description": "<2-3 sentences explaining how to do the drill>",
    "helps_with": "<what specific issue from the tournament this addresses>",
    "category": "<distance/timing/mental/finishing/defense/footwork/point_control>",
    "difficulty": "<beginner/intermediate/advanced>",
    "duration_minutes": <5-20>,
    "tournament_context": "<e.g. 'Recommended because: you lost three 5-4 bouts at Challenge by the Bay'>"
  }
]
```

### API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/drills` | Render drills page (HTML) |
| GET | `/api/drills` | List drills with filters (`?category=`, `?practiced=true/false`) |
| POST | `/api/drills` | Create a manual drill |
| POST | `/api/drills/<id>/practiced` | Mark as practiced |
| POST | `/api/drills/<id>/unpracticed` | Unmark as practiced |
| POST | `/api/drills/<id>/delete` | Delete a drill |
| POST | `/api/tournaments/<id>/generate-drills` | Generate AI drill recommendations |
| GET | `/api/tournaments/<id>/drills` | Get drills linked to a tournament |

### UI Design

**`templates/drills.html`** — New page from home navigation.

- **Category filter**: Horizontally scrollable pills (All, Distance, Timing, Mental, Finishing, Defense, Footwork, Point Control)
- **Status toggle**: All / To Practice / Practiced

**Drill cards**:
- Name as bold header
- Category pill (colored) + difficulty badge (green/yellow/red) + duration ("10 min")
- Description text
- "Helps with" in italics
- Tournament context in small grey text, linked to tournament
- "Mark Practiced" button -- when practiced, card gets green checkmark, moves to bottom
- Practice count if > 1 ("Practiced 3x")

**Add Drill form**: Collapsible at top with name, description, helps_with, category, difficulty, duration fields.

**On tournament detail page**: "Generate Practice Drills" button below DE tips. After generation, shows link "View X recommended drills" to filtered drills page.

**Home navigation**: Add "Practice Drills" card to `index.html`.

---

## Feature 3: Full Post-Tournament Analysis

### Database Model

```python
class TournamentAnalysis(Base):
    __tablename__ = 'tournament_analyses'
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True, unique=True)
    analysis_json = Column(Text)        # structured analysis sections
    generated_at = Column(DateTime, default=datetime.utcnow)
```

Analysis structure:
```json
{
  "overall_assessment": "text...",
  "scoring_patterns": {"summary": "...", "details": ["...", "..."]},
  "wins_analysis": {"summary": "...", "details": ["...", "..."]},
  "losses_analysis": {"summary": "...", "details": ["...", "..."]},
  "mental_game": {"summary": "...", "details": ["...", "..."]},
  "comparison_to_past": {"summary": "...", "details": ["...", "..."]},
  "areas_to_improve": [
    {"area": "Finishing close bouts", "explanation": "...", "priority": "high"}
  ],
  "strengths_shown": ["...", "..."],
  "coach_summary": "2-3 sentence summary for Coach Ziad"
}
```

### Claude Prompt

```
You are an experienced epee fencing analyst reviewing a Y-12 fencer's tournament performance. The fencer is Ethan (coached by Ziad). Provide a thorough tactical analysis for review at home after the tournament.

Tournament: {tournament_name}
Date: {tournament_date}
Location: {tournament_location}
Level: {tournament_level}

Pool Results:
Record: {victories}V-{defeats}D
Indicator: {indicator} (TS: {ts}, TR: {tr})
Pool Position: {position_in_pool}

Individual Bouts:
{for each bout: "Bout {n}: vs {opponent_name} ({opponent_club}) -- {score_for}-{score_against} {'WIN' if won else 'LOSS'}"}

{if previous_tournaments exist:}
Previous Tournament Results (most recent first):
{for each: "{name} ({date}): {victories}V-{defeats}D, Indicator {indicator}"}

Provide a detailed analysis in JSON format:
{
  "overall_assessment": "<2-3 sentence big-picture summary>",
  "scoring_patterns": {"summary": "<1-2 sentences>", "details": ["<specific observation referencing scores>"]},
  "wins_analysis": {"summary": "<what went right>", "details": ["<observation>"]},
  "losses_analysis": {"summary": "<patterns in losses>", "details": ["<observation referencing scores and opponents>"]},
  "mental_game": {"summary": "<composure assessment from scoring patterns>", "details": ["<observation>"]},
  "comparison_to_past": {"summary": "<trend vs recent tournaments, or 'First recorded tournament'>", "details": ["<trend>"]},
  "areas_to_improve": [{"area": "<specific area>", "explanation": "<why, referencing data>", "priority": "high|medium|low"}],
  "strengths_shown": ["<strength>"],
  "coach_summary": "<2-3 sentences for Coach Ziad -- what to focus on in lessons>"
}

Rules:
- Reference SPECIFIC bout scores and opponent names
- Use epee-specific terminology (no right-of-way)
- For mental game, analyze scoring sequences and patterns
- areas_to_improve should have 3-5 items, ordered by priority
- Be honest but constructive -- this is a 11-12 year old fencer
- coach_summary gives Ziad actionable lesson focus areas
```

### API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/tournaments/<id>/analysis` | Generate full analysis |
| GET | `/api/tournaments/<id>/analysis` | Retrieve saved analysis |

### UI Design

On `tournament_detail.html`, below the drills section:

- **When no analysis exists**: "Analyze Tournament" button (`btn-secondary`, white with blue border). Subtitle: "Full tactical breakdown for review at home."
- **When analysis exists**: Large card with collapsible sections:
  - **Overall Assessment** -- always visible, bold
  - **Scoring Patterns** -- collapsible, default open
  - **Wins Analysis** -- collapsible, green left border
  - **Losses Analysis** -- collapsible, red left border
  - **Mental Game** -- collapsible, orange left border
  - **Comparison to Past** -- collapsible, blue left border (hidden if no history)
  - **Areas to Improve** -- always visible, priority badges (red=high, yellow=medium, green=low)
  - **Strengths Shown** -- green background, checkmark bullets
  - **Coach Summary** -- highlighted blue box, "For Coach Ziad:"
- **Regenerate** link at bottom

---

## Tournament Detail Page Layout Order

1. Pool Results card (existing)
2. **DE Prep Tips card** (Feature 1) -- game-day, prominent
3. **Practice Drills** link/generate (Feature 2) -- links to drills page
4. **Full Analysis card** (Feature 3) -- home-review, detailed
5. Tournament Info card (existing)

---

## Implementation Sequence

**Phase 1 -- Database (all three features):**
1. Add `DEPrepTips`, `Drill`, `TournamentAnalysis` models to `database.py`
2. Add all helper functions
3. Add imports to `app.py`

**Phase 2 -- Quick DE Prep Tips:**
4. Add `generate_de_prep_tips()` to `app.py`
5. Add POST/GET endpoints
6. Update `tournament_detail.html` with tips card
7. Test with sample pool data

**Phase 3 -- Full Post-Tournament Analysis:**
8. Add `generate_tournament_analysis()` to `app.py`
9. Add POST/GET endpoints
10. Add analysis section to `tournament_detail.html`
11. Test with and without past tournament data

**Phase 4 -- Practice Drills:**
12. Add `generate_drill_recommendations()` to `app.py`
13. Add all drill API endpoints
14. Create `templates/drills.html`
15. Add drill section to `tournament_detail.html`
16. Add "Practice Drills" nav card to `index.html`

---

## Cost Estimate

| Feature | Est. Input Tokens | Est. Output Tokens | Cost per Call |
|---------|-------------------|-------------------|--------------|
| DE Prep Tips | ~600 | ~400 | ~$0.005 |
| Drill Recommendations | ~800 | ~1000 | ~$0.009 |
| Full Analysis | ~1200 | ~2000 | ~$0.015 |

**Total per tournament (all three)**: ~$0.03
**Annual (15-20 tournaments)**: ~$0.45-0.60/year

No new dependencies needed.

---

## Critical Files

- `database.py` -- Add 3 new models + helper functions
- `app.py` -- Add 3 Claude prompt functions, 6+ new API endpoints, 1 new page route
- `templates/tournament_detail.html` -- Add DE tips card, drills section, analysis section
- `templates/drills.html` -- New template for drills page
- `templates/index.html` -- Add "Practice Drills" nav card
