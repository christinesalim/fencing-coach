# Fencing Coach App - Complete Summary

**For:** Ethan Salim, Y-12 épée fencer at Academy of Fencing Masters (AFM), Central California
**Created:** April 2026
**Repository:** https://github.com/christinesalim/fencing-coach

---

## What This App Does

A mobile-first web application that helps track and organize fencing coaching feedback and tournament performance.

### Currently Working Features

1. **Voice Memo Processing**
   - Upload .m4a, .mp3, .wav audio files OR video files (.mp4, .mov, etc.)
   - Automatic transcription using OpenAI Whisper
   - AI extraction of actionable fencing tips using Claude Sonnet 4
   - Organized into 6 categories:
     - Patience and Control
     - Distance Management
     - Reading Opponent
     - When Ahead
     - Attack Execution
     - Defense and Retreat

2. **Tip Management**
   - View all tips organized by category
   - Edit tips (fix terminology, clarify wording)
   - Delete tips you don't need
   - Automatic deduplication across sessions
   - Print-friendly view for fencing notebook

3. **Mobile Access**
   - Deployed on Render: accessible from anywhere
   - Progressive Web App (PWA): "Add to Home Screen" on iPhone
   - Persistent PostgreSQL database (survives restarts/tournaments)
   - Automatic backups (downloadable JSON exports)

### Planned Features (Designed, Not Yet Implemented)

1. **Tournament Tracking**
   - Photo-based data entry using Claude Vision API
   - Upload photos of pool sheets, DE brackets, final results
   - Automatic extraction of:
     - Pool round scores and opponents
     - Direct elimination results
     - Final tournament placement and indicator
   - Track progress across tournaments

2. **Opponent Intelligence System**
   - Automatic opponent recognition from photos
   - Track opponent styles, handedness, tactics
   - Record what works/doesn't work against each opponent
   - Pre-bout alerts when facing known opponents
   - Confidence scoring for tactical notes
   - Voice memo integration for post-bout observations
   - Head-to-head statistics

3. **Private Lesson Library**
   - Store Friday lesson videos with Coach Ziad
   - YouTube unlisted videos (free, unlimited storage)
   - Transcribe audio for searchability
   - Tag techniques, drills, corrections
   - Track progression over time
   - Optional key clips for technique review

4. **Machine Learning Analysis**
   - Performance trends across tournaments
   - Pattern recognition in wins/losses
   - Tactical effectiveness analysis
   - Opponent difficulty prediction
   - Style matchup insights

---

## Technical Stack

### Current Implementation

**Backend:**
- Python 3 with Flask web framework
- SQLAlchemy ORM for database abstraction
- PostgreSQL (production on Render)
- SQLite (local development)

**AI Services:**
- OpenAI Whisper API: Audio transcription ($0.006/minute)
- Anthropic Claude Sonnet 4: Text analysis and advice extraction
- Anthropic Claude Vision: Photo-based tournament data extraction (planned)

**Frontend:**
- Mobile-first HTML/CSS
- Progressive Web App capabilities
- Print-optimized tip view

**Infrastructure:**
- Render.com hosting (free tier)
- PostgreSQL database (free tier, 1GB)
- GitHub auto-deployment
- Environment variable management

**Dependencies:**
```
flask
openai
anthropic
python-dotenv
moviepy (video audio extraction)
psycopg2-binary (PostgreSQL adapter)
sqlalchemy
```

### Database Schema (Current)

**sessions** - Training sessions with uploaded files
- id, date, filename, transcript, advice_json

**tips** - Individual fencing tips
- id, category, text (unique), created_at

### Future Database Tables (Designed)

See [FUTURE_DATABASE_MODEL.md](FUTURE_DATABASE_MODEL.md) for complete schema including:
- tournaments, pool_rounds, pool_bouts, elimination_rounds
- opponents, bout_opponents, opponent_tactical_notes, opponent_voice_memos
- bout_alerts, opponent_head_to_head (materialized view)

---

## Cost Analysis (with all planned features)

**Per Tournament:**
- Voice memo transcription: $0.03-0.06 (5-10 min audio)
- Tip extraction: $0.001-0.002 (Claude API)
- Photo processing (3 photos): $0.015 (pool, DE, results)
- Opponent analysis: $0.01 (for multiple opponents)
- **Total: ~$0.05-0.10 per tournament**

**Per Private Lesson:**
- Video transcription: $0.10 (60 min lesson)
- Lesson analysis: $0.002
- Video storage: $0 (YouTube unlisted)
- **Total: ~$0.10 per lesson**

**Estimated Annual Cost:** $15-20
- ~20 tournaments/year: $2
- ~40 lessons/year: $4
- Hosting: Free (Render free tier)
- Storage: Free (PostgreSQL 1GB + YouTube)

---

## Key Files

### Application Code
- [app.py](app.py) - Flask web server, upload handling, API endpoints
- [database.py](database.py) - SQLAlchemy models and database operations
- [requirements.txt](requirements.txt) - Python dependencies

### Documentation
- [DEPLOY_TO_RENDER.md](DEPLOY_TO_RENDER.md) - Deployment instructions
- [FUTURE_DATABASE_MODEL.md](FUTURE_DATABASE_MODEL.md) - Complete database design and implementation code for planned features
- [APP_SUMMARY.md](APP_SUMMARY.md) - This file

### Templates
- templates/index.html - Upload interface
- templates/tips.html - View and manage tips

### Configuration
- .env - API keys (not committed)
- .gitignore - Excludes voice recordings, personal data

---

## How to Use

### Upload Voice Memos
1. Record coaching feedback on iPhone
2. Open Fencing Coach app (from home screen)
3. Tap "Choose Audio File"
4. Select voice memo or video
5. Wait 30-60 seconds for processing
6. View organized tips

### Manage Tips
- Tap "View All Tips" to see organized advice
- Tap ✏️ to edit any tip
- Tap 🗑️ to delete tips
- Tap "Print" to save as PDF for fencing notebook

### Backup Data
- Navigate to /api/backup endpoint
- Downloads JSON file with all sessions and tips
- Automatic timestamp in filename

### Local Development
```bash
cd /Users/Christine/Fencing
source venv/bin/activate
python app.py
# App runs on http://localhost:5001
```

### Deploy Updates
```bash
cd /Users/Christine/Fencing
git add .
git commit -m "Description of changes"
git push
# Render auto-deploys within 2-3 minutes
```

---

## Example Tournament Data

**South Point Fencing Club Y12 Épée - March 2026**
- Pool #7: 1V-4D, finished 5th in pool, -4 indicator
- DE Round 64: Won 15-7 vs LUCAS, Aiden (unranked)
- DE Round 32: Lost 7-15 vs YI, Alexander (#4 seed)
- Final Placement: 28th out of 47 fencers

This data was extracted from photos and will be the foundation for the tournament tracking system.

---

## Why Two API Services?

**OpenAI (Whisper):**
- Industry-leading speech-to-text accuracy
- Handles fencing terminology well
- Supports multiple audio/video formats
- $0.006 per minute of audio

**Anthropic (Claude):**
- Excellent at understanding nuanced coaching feedback
- Structured data extraction (JSON categories)
- Vision API for photo-based tournament entry
- Better context understanding for tactical analysis

Using both gives best results: perfect transcription + intelligent analysis.

---

## Design Decisions

1. **Mobile-First:** Designed for iPhone use at tournaments
2. **Photo-Based Entry:** Minimize manual data entry using Claude Vision
3. **Persistent Storage:** PostgreSQL ensures data survives across tournaments
4. **External Video Storage:** YouTube unlisted for cost-effective lesson videos
5. **Automatic Deduplication:** Prevent duplicate tips across sessions
6. **Confidence Tracking:** Validate tactical notes over multiple bouts
7. **Fuzzy Name Matching:** Recognize opponents despite spelling variations
8. **Print-Friendly:** Easy to print tips for physical fencing notebook

---

## Next Steps (When Ready to Implement)

1. **Tournament Tracking Phase 1:**
   - Add tournament and pool_rounds tables to database.py
   - Create photo upload endpoint in app.py
   - Implement Claude Vision extraction for pool results
   - Build tournament entry UI

2. **Opponent Intelligence Phase 1:**
   - Add opponents and opponent_tactical_notes tables
   - Implement automatic opponent recognition from pool photos
   - Create opponent profile view
   - Add pre-bout alert system

3. **Private Lesson Library Phase 1:**
   - Create lessons table
   - Add YouTube URL field
   - Implement video transcription
   - Build lesson tagging system

---

## Support and Monitoring

- **Render Dashboard:** https://dashboard.render.com
- **GitHub Repository:** https://github.com/christinesalim/fencing-coach
- **Logs:** Available in Render dashboard
- **Free Tier Notes:** App sleeps after 15min inactivity, wakes in 30-60sec

---

## Contact

For questions about the app architecture or planned features, refer to:
- This summary
- [FUTURE_DATABASE_MODEL.md](FUTURE_DATABASE_MODEL.md) for detailed implementation plans
- [DEPLOY_TO_RENDER.md](DEPLOY_TO_RENDER.md) for deployment guidance

Good luck at your competitions! 🤺
