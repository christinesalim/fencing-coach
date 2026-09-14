# Private Lessons with Cloudflare R2 - Implementation Plan

## Overview

Replace YouTube-based lesson storage with direct video upload to Cloudflare R2. Add tagging (defense/offense/free-form), transcription via Whisper, and search.

---

## 1. Cloudflare R2 Setup

### Bucket Configuration

- Create bucket named `fencing-lessons` in Cloudflare dashboard
- Keep bucket **private** -- all video playback uses presigned URLs with 1-hour expiry
- No custom domain needed; presigned URLs use the R2 endpoint directly

### CORS Policy

```json
[{
  "AllowedOrigins": ["https://your-app-domain.onrender.com", "http://localhost:5001"],
  "AllowedMethods": ["GET", "PUT"],
  "AllowedHeaders": ["*"],
  "MaxAgeSeconds": 3600
}]
```

### Upload Strategy: Server-Side

- For a single-user app with clips under 100MB, server-side upload via Flask is simpler than presigned PUT URLs
- The app already accepts 200MB uploads (`MAX_CONTENT_LENGTH = 200 * 1024 * 1024`)
- Flow: browser sends multipart form to Flask, Flask streams file to R2 via `boto3`
- Mobile progress: use `XMLHttpRequest` with `upload.onprogress` for the browser-to-server leg

### Environment Variables

Add to `.env` and Render:

```
R2_ACCOUNT_ID=<cloudflare_account_id>
R2_ACCESS_KEY_ID=<r2_api_token_access_key>
R2_SECRET_ACCESS_KEY=<r2_api_token_secret>
R2_BUCKET_NAME=fencing-lessons
```

### R2 Object Key Convention

```
lessons/{lesson_id}/{uuid}.{ext}
```

---

## 2. Updated SQLAlchemy Models (in `database.py`)

### Updated `Lesson` model

```python
class Lesson(Base):
    __tablename__ = 'lessons'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # R2 storage fields (replace youtube_url)
    r2_object_key = Column(String(500))       # e.g. "lessons/42/abc123.mp4"
    original_filename = Column(String(255))
    file_size_bytes = Column(Integer)
    duration_seconds = Column(Float)          # extracted via moviepy
    mime_type = Column(String(100))           # e.g. "video/mp4"

    # Legacy field kept nullable for migration
    youtube_url = Column(String(500), nullable=True)

    # Categorization
    category = Column(String(20))             # 'offense', 'defense', or null
    lesson_date = Column(DateTime)            # actual date of the lesson

    # Transcription
    transcript = Column(Text)
    transcription_status = Column(String(20), default='pending')  # pending/processing/complete/failed

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### New `LessonTag` model

```python
class LessonTag(Base):
    __tablename__ = 'lesson_tags'

    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False, index=True)
    tag = Column(String(100), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint('lesson_id', 'tag', name='uq_lesson_tag'),
    )
```

Separate table enables efficient tag queries. Tags stored as normalized lowercase strings.

---

## 3. R2 Client Initialization (in `app.py`)

Lazy-initialized, following the existing `_openai_client` pattern:

```python
_r2_client = None

def get_r2_client():
    global _r2_client
    if _r2_client is None:
        _r2_client = boto3.client('s3',
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
            region_name='auto'
        )
    return _r2_client
```

---

## 4. Flask API Endpoints

### (a) Upload video and create lesson -- `POST /api/lessons`

- Accepts multipart form: `video` file, `title`, `description` (optional), `category`, `lesson_date`, `tags` (comma-separated)
- Saves file temporarily to `uploads/`
- Extracts duration via `moviepy.editor.VideoFileClip`
- Uploads to R2 via `r2_client.upload_file()`
- Transcribes audio via Whisper (see section 5)
- If no description provided: auto-generates one from the transcript via Claude
- Creates `Lesson` row and `LessonTag` rows
- Deletes temp file
- Returns new lesson JSON (includes auto-generated description if applicable)

### (b) List lessons with filtering -- `GET /api/lessons`

- Query params: `category` (offense/defense), `tag`, `q` (search term)
- Tag filtering: join with `lesson_tags`
- Text search: SQL `LIKE`/`ILIKE` across title, description, transcript
- Ordered by `lesson_date DESC`

### (c) Get single lesson -- `GET /api/lessons/<id>`

- Returns full lesson detail including tags and presigned playback URL

### (d) Update lesson metadata -- `PUT /api/lessons/<id>`

- Updates title, description, category, lesson_date

### (e) Delete lesson -- `DELETE /api/lessons/<id>`

- Deletes R2 object via `r2_client.delete_object()`
- Deletes all `LessonTag` rows
- Deletes `Lesson` row

### (f) Manage tags

- `POST /api/lessons/<id>/tags` -- add one or more tags
- `DELETE /api/lessons/<id>/tags/<tag>` -- remove a tag

### (g) Get all unique tags -- `GET /api/tags`

- `SELECT DISTINCT tag FROM lesson_tags ORDER BY tag`
- Powers autocomplete in the UI

### (h) Search lessons -- `GET /api/lessons/search?q=<term>`

- Searches across tags, title, description, transcript
- Simple `ILIKE '%term%'` works for the small dataset (~40 lessons/year)

### (i) Get presigned playback URL -- `GET /api/lessons/<id>/playback-url`

- Separate endpoint to avoid generating unnecessary presigned URLs
- Returns `{ "url": "https://...", "expires_in": 3600 }`

### Backward Compatibility

- Keep existing `POST /api/add-lesson` and `POST /api/delete-lesson` temporarily
- The `/lessons` page route serves the new template

---

## 5. Video Transcription and Auto-Summary Flow

Reuses the existing pattern from `app.py` (`extract_audio_from_video()` + `transcribe()`) and adds a Claude summarization step to auto-generate the description.

```
1. Save uploaded file to uploads/temp_xxx.mp4
2. Extract duration via moviepy (quick)
3. Upload file to R2
4. Extract audio from temp file -> temp audio file
5. Transcribe audio via Whisper
6. Send transcript to Claude for auto-summary -> auto-fill description
7. Save Lesson row with transcript + auto-generated description, set transcription_status='complete'
8. Delete temp files
```

### Auto-Summary and Auto-Tags via Claude

After Whisper transcribes the audio, a single Claude call generates both a description and suggested tags:

```python
def analyze_lesson_transcript(transcript):
    """Generate a summary and suggested tags from a lesson transcript."""
    client = get_claude_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Analyze this fencing lesson coaching transcript and return JSON:

{{
  "title": "<short descriptive title, e.g. 'Parry 4 Riposte - correct form' or 'Fleche timing drill'>",
  "summary": "<2-3 sentence description focusing on the technique taught and key corrections>",
  "category": "offense" | "defense" | null,
  "tags": ["<specific technique tags like: flick, parry 4, riposte, fleche, footwork, disengage, beat attack, etc.>"]
}}

Rules for title:
- Short and specific (under 50 characters)
- Name the technique or drill being practiced
- Include "correct form" or "drill" or "timing" etc. if relevant

Rules for tags:
- Only include tags you're confident about from what the coach is teaching
- Use standard fencing terminology (lowercase)
- Include specific techniques (e.g. "flick", "parry 4 riposte") not vague terms
- Typically 2-5 tags per lesson
- Include the coach's name if mentioned

Rules for category:
- "offense" if the lesson focuses on attacking techniques (attacks, fleche, flick, etc.)
- "defense" if the lesson focuses on defensive techniques (parry, retreat, distance, etc.)
- null if it's mixed or unclear

Transcript:
{transcript}"""
        }]
    )
    # Parse JSON response (same fallback as existing code)
    text = message.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())
```

### How auto-fill works

**Title:**
- If the user leaves title **blank**: auto-generated from transcript (e.g., "Parry 4 Riposte - correct form")
- If the user writes their own: kept as-is
- Always editable after upload

**Date:**
- Defaults to **today's date** in the date picker (lessons are typically uploaded same day)
- User can change it if uploading an older clip

**Description:**
- If the user leaves description **blank**: auto-generated summary fills it in
- If the user writes their own: kept as-is
- Always **editable after upload** via `PUT /api/lessons/<id>`

**Category (offense/defense):**
- If the user doesn't select one: auto-detected from transcript
- If the user selects one: their choice takes priority

**Tags:**
- Auto-suggested tags are **merged with** any tags the user entered manually
- Duplicates are skipped
- User can remove any auto-suggested tags after upload
- Auto-suggested tags appear with a subtle "auto" indicator so the user knows which ones were AI-generated

### Cost per clip

- Whisper transcription: ~$0.018 (3 min average)
- Claude summary + tags: ~$0.001 (single API call)
- **Total: ~$0.02 per clip**

Key: transcribe from the local temp file *before* deleting it, avoiding a round-trip download from R2.

**If transcription fails:** set `transcription_status='failed'` but still save the lesson (video is already in R2). User can retry later. If transcription succeeds but summary fails, save the transcript without a summary -- the user can write their own description.

**Timeout:** For a 5-minute video, Whisper takes 15-30 seconds, Claude summary takes 2-3 seconds. Combined with upload, total request may take 1-2 minutes on mobile. The existing voice memo flow handles similar durations.

---

## 6. Mobile HTML UI (`templates/lessons.html`)

### Upload Section

The upload form is minimal -- most fields are auto-filled from the audio:

- File picker: `<input type="file" accept="video/*,.mp4,.mov,.m4v">`
- Title input -- placeholder: "Auto-generated from audio" (optional, leave blank)
- Lesson date: `<input type="date">` -- **defaults to today**
- Category: two toggle buttons "Offense" / "Defense" (or neither) -- auto-detected if not selected
- Tags: text field with autocomplete from `GET /api/tags` -- auto-suggested tags merged in after processing
- Description textarea -- placeholder: "Auto-generated from audio" (optional, leave blank)
- **Progress bar**: `XMLHttpRequest` with `xhr.upload.onprogress` showing percentage
- Status updates: "Uploading..." → "Transcribing audio..." → "Analyzing lesson..." → "Done!"
- After upload completes: title, description, category, and tags are all populated (auto-filled fields can be edited anytime)

**Ideal quick-upload flow:** Pick a video, tap "Upload" -- everything else fills in automatically. The user only needs to intervene if they want to override something.

### Filter/Search Bar

- Search text input
- Category pills: "All" / "Offense" / "Defense"
- Tag pills: horizontally scrollable, from `GET /api/tags`, tap to toggle filter
- Filters apply via JavaScript, re-fetching `GET /api/lessons?category=...&tag=...&q=...`

### Lesson Library

Each lesson card shows:
- Play button / thumbnail area (tap opens detail view)
- Title and lesson date
- Category badge (blue=offense, green=defense)
- Tag pills
- Duration (e.g., "2:34")
- Truncated description (2 lines)

### Lesson Detail View (modal overlay)

- `<video>` element with `controls`, `src` from presigned URL
- Title, date, category badge
- Editable tags: existing as removable pills, plus "Add tag" input
- Description (editable)
- Transcript section: collapsible, full text, searchable
- Delete button with confirmation
- Close/back button

### CSS

Follow existing design system: blue gradient background, white cards with `border-radius: 20px`, `box-shadow`, Apple system font stack. Progress bar: thin, blue gradient fill. Tag pills: small rounded rectangles.

---

## 7. Migration Plan (YouTube to R2)

### Database Migration

Since the app uses `create_all()` without Alembic, a one-time migration script is needed:

```python
# migrate_lessons.py (run once)
from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    columns = [
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS r2_object_key VARCHAR(500)",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255)",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS duration_seconds FLOAT",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100)",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS category VARCHAR(20)",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS lesson_date TIMESTAMP",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS transcript TEXT",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS transcription_status VARCHAR(20) DEFAULT 'pending'",
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
        "ALTER TABLE lessons ALTER COLUMN youtube_url DROP NOT NULL",
    ]
    for sql in columns:
        try:
            conn.execute(text(sql))
        except Exception as e:
            print(f"Skipping (may already exist): {e}")
    conn.commit()
```

### Data Migration

- Existing lessons with `youtube_url` remain untouched (`r2_object_key = NULL`)
- UI handles both: if `r2_object_key` present, show R2 video player; if only `youtube_url`, show legacy YouTube embed
- Zero data loss, no urgency to re-upload old content
- Optionally add "Re-upload as R2 video" button on legacy cards

---

## 8. Cost Estimate

### R2 Pricing

| Resource | Price | This App |
|----------|-------|----------|
| Storage | $0.015/GB/month | ~0.9 GB year 1 = $0.014/month |
| Class A ops (writes) | $4.50/million | Negligible |
| Class B ops (reads) | $0.36/million | Negligible |
| Egress | **Free** | $0.00 |

### Usage Assumptions

- 40 lessons/year, average 3-minute clip
- ~15MB/minute for 1080p H.264 = ~45MB per clip
- Annual growth: ~1.8 GB/year
- After 3 years: ~5.4 GB

### R2 Free Tier (included with every Cloudflare account)

- 10 GB storage
- 10 million Class B reads/month
- 1 million Class A writes/month
- **This app stays within the free tier for years**

### Whisper Transcription Cost

- $0.006/minute audio
- Average 3-min clip = $0.018 per lesson
- 40 lessons/year = $0.72/year

---

## 9. Cleanup & Lifecycle

- **On lesson deletion**: Delete R2 object before deleting DB row. If R2 delete fails, log error but still delete DB row (orphaned objects are harmless and cheap)
- **No lifecycle rules**: Clips are kept indefinitely as a reference library
- **Backup**: Update `/api/backup` to include lesson metadata (not video binary). R2 has built-in redundancy.
- **Orphan cleanup** (low priority): Optional script to list R2 objects and cross-reference with `lessons` table

---

## 10. New Dependency

Add to `requirements.txt`:

```
boto3
```

`boto3` is the standard Python S3 client. Works with R2 since R2 is S3-compatible.

---

## 11. Implementation Sequence

**Phase 1 -- Infrastructure:**
1. Create R2 bucket in Cloudflare dashboard, generate API token
2. Add env vars to `.env` and Render
3. Add `boto3` to `requirements.txt`
4. Add R2 client initialization to `app.py`

**Phase 2 -- Database:**
5. Update `Lesson` model in `database.py`, add `LessonTag` model
6. Create and run migration script
7. Add new database utility functions (CRUD, tag management, search)

**Phase 3 -- API Endpoints:**
8. Implement `POST /api/lessons` (upload + R2 + transcription)
9. Implement `GET /api/lessons` with filtering
10. Implement `GET /api/lessons/<id>` and `/playback-url`
11. Implement `PUT /api/lessons/<id>`, `DELETE /api/lessons/<id>`
12. Implement tag endpoints and `GET /api/tags`
13. Implement search endpoint

**Phase 4 -- Frontend:**
14. Rebuild `templates/lessons.html` with upload form, progress bar, filter bar, lesson cards, detail modal

**Phase 5 -- Polish:**
15. Update `/api/backup` to include lesson metadata
16. Test on mobile (iOS Safari)
17. Handle edge cases (upload cancellation, network failures, duplicates)

---

## Critical Files

- `database.py` -- Updated `Lesson` model, new `LessonTag` model, all new functions
- `app.py` -- R2 client init, all new API endpoints, transcription integration
- `templates/lessons.html` -- Complete rewrite with new upload, filtering, video player
- `requirements.txt` -- Add `boto3`
- `.env` -- Add R2 credentials
- `migrate_lessons.py` -- One-time migration script (new file)
