#!/usr/bin/env python3
"""Flask web app for fencing tips - upload voice memos and get tips."""

import os
import json
import uuid
import base64
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, request, render_template, jsonify, Response, session, redirect, url_for
from werkzeug.utils import secure_filename
import openai
import anthropic
from dotenv import load_dotenv
from database import (
    load_data_from_db,
    save_session_to_db,
    update_tip_in_db,
    delete_tip_from_db,
    restore_data_to_db,
    get_lessons_from_db,
    add_lesson_to_db,
    delete_lesson_from_db,
    add_lesson_r2,
    get_lessons_filtered,
    get_lesson,
    update_lesson,
    delete_lesson_r2,
    add_tags_to_lesson,
    remove_tag_from_lesson,
    get_all_tags,
    create_tournament,
    get_tournaments,
    get_tournament,
    update_tournament,
    delete_tournament,
    save_pool_results_to_db,
    get_pool_results,
    save_de_prep_tips,
    get_de_prep_tips,
    save_de_results_to_db,
    get_de_results,
    delete_de_results,
    save_de_summary,
    get_de_summary,
    save_tournament_summary,
    get_tournament_summary,
    update_tournament_final_results,
    bout_exists,
    add_bout_video,
    get_bout_video,
    delete_bout_video,
    create_opponent,
    get_opponent,
    update_opponent,
    delete_opponent,
    get_all_opponents,
    search_opponents_by_name,
    search_opponents_by_traits,
    add_tactical_note,
    update_tactical_note,
    delete_tactical_note,
    get_tactical_notes,
    add_bout_record,
    get_head_to_head,
    increment_note_validated,
    increment_note_invalidated,
    lookup_opponents_by_names,
    sync_bout_to_opponent,
)
from de_extraction import extract_full_de_bracket
from final_results_extraction import extract_final_results

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size (for videos)
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.aac', '.ogg', '.flac'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}

# API clients — initialized lazily so missing env vars don't crash startup
_openai_client = None
_claude_client = None
_r2_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client

def get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _claude_client

def get_r2_client():
    global _r2_client
    if _r2_client is None:
        import boto3
        _r2_client = boto3.client('s3',
            endpoint_url=f"https://{os.environ.get('R2_ACCOUNT_ID', '')}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID', ''),
            aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY', ''),
            region_name='auto'
        )
    return _r2_client


def extract_audio_from_video(video_path):
    """Extract audio from video file and save as temporary audio file."""
    import subprocess
    import shutil

    audio_path = video_path.with_suffix('.mp3')

    # Try ffmpeg directly first (handles iPhone HEVC/Dolby Vision better than moviepy)
    ffmpeg_bin = shutil.which('ffmpeg')
    if not ffmpeg_bin:
        # Fall back to moviepy's bundled ffmpeg
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

    if ffmpeg_bin:
        try:
            result = subprocess.run(
                [ffmpeg_bin, '-i', str(video_path), '-vn', '-acodec', 'libmp3lame',
                 '-q:a', '4', '-y', str(audio_path)],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and audio_path.exists():
                return audio_path
        except Exception:
            pass

    # Fall back to moviepy
    try:
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            from moviepy import VideoFileClip

        video = VideoFileClip(str(video_path))
        video.audio.write_audiofile(str(audio_path), verbose=False, logger=None)
        video.close()
        return audio_path
    except Exception as e:
        raise Exception(f"Failed to extract audio from video: {str(e)}")


def transcribe(file_path):
    """Transcribe audio/video file using Whisper."""
    file_ext = file_path.suffix.lower()
    audio_path = file_path
    extracted_audio = False

    # If it's a video, extract audio first
    if file_ext in ALLOWED_VIDEO_EXTENSIONS:
        audio_path = extract_audio_from_video(file_path)
        extracted_audio = True

    try:
        with open(audio_path, "rb") as f:
            result = get_openai_client().audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        return _fix_fencing_terms(result)
    finally:
        # Clean up extracted audio file
        if extracted_audio and audio_path.exists():
            audio_path.unlink()


# Fencing terms Whisper commonly mistranscribes
_FENCING_TERM_FIXES = {
    'flash': 'flèche', 'flesh': 'flèche', 'fleche': 'flèche',
    'circle sticks': 'circle six', 'circle six repost': 'circle six riposte',
    'repost': 'riposte',
    'on guard': 'en garde', 'on guard!': 'en garde!',
    'touche': 'touché',
}


def _fix_fencing_terms(transcript):
    """Fix common Whisper mistranscriptions of fencing terminology."""
    import re
    for wrong, right in _FENCING_TERM_FIXES.items():
        transcript = re.sub(
            r'\b' + re.escape(wrong) + r'\b',
            right,
            transcript,
            flags=re.IGNORECASE
        )
    return transcript


def extract_fencing_advice(transcript, filename):
    """Extract actionable fencing advice from transcript."""
    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": (
                    f"The following is a transcript of fencing coaching feedback from '{filename}'.\n\n"
                    f"{transcript}\n\n"
                    "Extract actionable fencing advice and categorize it. Focus on:\n"
                    "- Not forcing touches/actions when they aren't there\n"
                    "- Retreating when you can see an attack building and can't stop it\n"
                    "- Staying ahead when up by a few points\n"
                    "- Being patient and not giving away touches\n"
                    "- Distance management\n"
                    "- Reading the opponent\n"
                    "- Tactical awareness\n\n"
                    "Return a JSON object with these categories as keys, each containing an array of "
                    "concise, actionable bullet points (1-2 sentences each). Only include categories "
                    "that have relevant advice in this transcript. Use these exact category names:\n"
                    "- patience_and_control\n"
                    "- distance_management\n"
                    "- reading_opponent\n"
                    "- when_ahead\n"
                    "- attack_execution\n"
                    "- defense_and_retreat\n\n"
                    "Example format:\n"
                    '{\n  "patience_and_control": ["Don\'t force actions when they aren\'t there"],\n'
                    '  "when_ahead": ["When up by points, be more careful - you don\'t need to go"]\n}'
                ),
            }
        ],
    )
    try:
        return json.loads(message.content[0].text)
    except json.JSONDecodeError:
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())


def analyze_lesson_transcript(transcript):
    """Generate title, summary, category, and tags from a lesson transcript."""
    client = get_claude_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Analyze this fencing lesson coaching transcript and return JSON:

{{
  "title": "<short descriptive title, under 50 chars, e.g. 'Parry 4 Riposte - correct form'>",
  "summary": "<2-3 sentence description focusing on the technique taught and key corrections>",
  "category": "offense" or "defense" or null,
  "tags": ["<specific fencing technique tags like: flick, parry 4, riposte, fleche, footwork>"]
}}

Rules for tags:
- Only include tags you're confident about from what the coach is teaching
- Use standard fencing terminology (lowercase)
- Include specific techniques, not vague terms
- Typically 2-5 tags per lesson

Transcript:
{transcript}"""
        }]
    )
    text = message.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == os.environ.get('APP_PASSWORD', ''):
            session.permanent = True
            session['logged_in'] = True
            next_page = request.args.get('next', '/')
            return redirect(next_page)
        error = 'Incorrect password'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/tips')
@login_required
def tips():
    """View all tips."""
    data = load_data_from_db()
    return render_template('tips.html', data=data)


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    """Handle file upload and processing."""
    if 'audio' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['audio']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Save file
    filename = secure_filename(file.filename)
    filepath = app.config['UPLOAD_FOLDER'] / filename
    file.save(filepath)

    try:
        # Process the file
        transcript = transcribe(filepath)
        advice = extract_fencing_advice(transcript, filename)

        # Save to database
        session = save_session_to_db(filename, transcript, advice)

        # Clean up uploaded file
        filepath.unlink()

        # Get updated data
        data = load_data_from_db()

        return jsonify({
            'success': True,
            'session': session,
            'combined_advice': data['combined_advice']
        })

    except Exception as e:
        # Clean up file on error
        if filepath.exists():
            filepath.unlink()
        return jsonify({'error': str(e)}), 500


@app.route('/api/data')
@login_required
def get_data():
    """Get all data as JSON."""
    return jsonify(load_data_from_db())


@app.route('/api/backup')
@login_required
def backup():
    """Full database backup as downloadable JSON."""
    data = load_data_from_db()
    data['exported_at'] = datetime.utcnow().isoformat()

    filename = f'fencing_backup_{datetime.utcnow():%Y%m%d_%H%M%S}.json'
    return Response(
        json.dumps(data, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/api/restore', methods=['POST'])
@login_required
def restore():
    """Restore database from a backup JSON file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'File must be a .json backup'}), 400

    try:
        data = json.loads(file.read().decode('utf-8'))
        result = restore_data_to_db(data)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/lessons')
@login_required
def lessons():
    """Private lessons page."""
    return render_template('lessons.html')


@app.route('/api/add-lesson', methods=['POST'])
@login_required
def add_lesson():
    data = request.get_json()
    title = data.get('title', '').strip()
    youtube_url = data.get('youtube_url', '').strip()
    description = data.get('description', '').strip()

    if not title or not youtube_url:
        return jsonify({'error': 'Title and YouTube URL are required'}), 400

    try:
        lesson = add_lesson_to_db(title, youtube_url, description)
        return jsonify({'success': True, 'lesson': lesson})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-lesson', methods=['POST'])
@login_required
def delete_lesson():
    data = request.get_json()
    lesson_id = data.get('id')
    if not lesson_id:
        return jsonify({'error': 'Missing lesson id'}), 400
    try:
        success = delete_lesson_from_db(lesson_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Lesson not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons/upload', methods=['POST'])
@login_required
def api_upload_lesson():
    """Upload video and create lesson with R2 storage."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file uploaded'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Get optional form fields
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip() or None
    lesson_date_str = request.form.get('lesson_date', '').strip()
    tags_str = request.form.get('tags', '').strip()

    user_tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []

    # Parse lesson date
    lesson_date = None
    if lesson_date_str:
        try:
            lesson_date = datetime.strptime(lesson_date_str, '%Y-%m-%d')
        except ValueError:
            pass

    # Save file temporarily
    original_filename = secure_filename(file.filename)
    file_ext = Path(original_filename).suffix.lower()
    temp_filename = f"{uuid.uuid4()}{file_ext}"
    filepath = app.config['UPLOAD_FOLDER'] / temp_filename
    file.save(filepath)

    try:
        file_size = filepath.stat().st_size

        # Extract duration via moviepy
        duration = None
        try:
            try:
                from moviepy.editor import VideoFileClip
            except ImportError:
                from moviepy import VideoFileClip
            clip = VideoFileClip(str(filepath))
            duration = clip.duration
            clip.close()
        except Exception:
            pass

        # Determine mime type
        mime_map = {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.avi': 'video/x-msvideo',
                    '.mkv': 'video/x-matroska', '.m4v': 'video/x-m4v'}
        mime_type = mime_map.get(file_ext, 'video/mp4')

        # Generate R2 object key and upload
        r2_key = f"lessons/{uuid.uuid4()}{file_ext}"
        bucket = os.environ.get('R2_BUCKET_NAME', 'fencing-lessons')
        get_r2_client().upload_file(str(filepath), bucket, r2_key)

        # Transcribe audio
        transcript = None
        transcription_status = 'pending'
        try:
            transcript = transcribe(filepath)
            transcription_status = 'complete'
        except Exception:
            transcription_status = 'failed'

        # Auto-analyze if transcript available
        auto_title = None
        auto_summary = None
        auto_category = None
        auto_tags = []
        if transcript:
            try:
                analysis = analyze_lesson_transcript(transcript)
                auto_title = analysis.get('title')
                auto_summary = analysis.get('summary')
                auto_category = analysis.get('category')
                auto_tags = analysis.get('tags', [])
            except Exception:
                pass

        # Merge auto-fill with user-provided values
        final_title = title if title else (auto_title or original_filename)
        final_description = description if description else (auto_summary or '')
        final_category = category if category else auto_category

        # Merge tags (user + auto, deduplicated)
        all_tags = list(set([t.lower() for t in user_tags] + [t.lower() for t in auto_tags]))

        # Create lesson record
        lesson_data = {
            'title': final_title,
            'description': final_description,
            'r2_object_key': r2_key,
            'original_filename': original_filename,
            'file_size_bytes': file_size,
            'duration_seconds': duration,
            'mime_type': mime_type,
            'category': final_category,
            'lesson_date': lesson_date,
            'transcript': transcript,
            'transcription_status': transcription_status,
            'tags': all_tags,
        }
        lesson = add_lesson_r2(lesson_data)

        return jsonify({'success': True, 'lesson': lesson})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up temp file
        if filepath.exists():
            filepath.unlink()


@app.route('/api/lessons/list')
@login_required
def api_list_lessons():
    """List lessons with optional filtering."""
    category = request.args.get('category')
    tag = request.args.get('tag')
    search = request.args.get('q')
    return jsonify(get_lessons_filtered(category=category, tag=tag, search=search))


@app.route('/api/lessons/<int:lesson_id>')
@login_required
def api_get_lesson(lesson_id):
    """Get a single lesson with tags."""
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({'error': 'Lesson not found'}), 404
    return jsonify(lesson)


@app.route('/api/lessons/<int:lesson_id>/playback-url')
@login_required
def api_lesson_playback_url(lesson_id):
    """Generate a presigned R2 URL for video playback."""
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({'error': 'Lesson not found'}), 404
    if not lesson.get('r2_object_key'):
        return jsonify({'error': 'No R2 video for this lesson'}), 404
    try:
        url = get_r2_client().generate_presigned_url(
            'get_object',
            Params={
                'Bucket': os.environ.get('R2_BUCKET_NAME', 'fencing-lessons'),
                'Key': lesson['r2_object_key']
            },
            ExpiresIn=3600
        )
        return jsonify({'url': url, 'expires_in': 3600})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons/<int:lesson_id>/update', methods=['POST'])
@login_required
def api_update_lesson(lesson_id):
    """Update lesson metadata."""
    data = request.get_json()
    try:
        lesson = update_lesson(lesson_id, data)
        if not lesson:
            return jsonify({'error': 'Lesson not found'}), 404
        return jsonify({'success': True, 'lesson': lesson})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons/<int:lesson_id>/delete', methods=['POST'])
@login_required
def api_delete_lesson_r2(lesson_id):
    """Delete lesson and its R2 object."""
    try:
        r2_key = delete_lesson_r2(lesson_id)
        if r2_key is None:
            return jsonify({'error': 'Lesson not found'}), 404

        # Try to delete R2 object (don't fail if it errors)
        if r2_key:
            try:
                bucket = os.environ.get('R2_BUCKET_NAME', 'fencing-lessons')
                get_r2_client().delete_object(Bucket=bucket, Key=r2_key)
            except Exception:
                pass  # Log but don't fail

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons/<int:lesson_id>/tags', methods=['POST'])
@login_required
def api_add_tags(lesson_id):
    """Add tags to a lesson."""
    data = request.get_json()
    tags = data.get('tags', [])
    if not tags:
        return jsonify({'error': 'No tags provided'}), 400
    try:
        added = add_tags_to_lesson(lesson_id, tags)
        return jsonify({'success': True, 'added': added})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons/<int:lesson_id>/tags/remove', methods=['POST'])
@login_required
def api_remove_tag(lesson_id):
    """Remove a tag from a lesson."""
    data = request.get_json()
    tag = data.get('tag', '')
    if not tag:
        return jsonify({'error': 'No tag provided'}), 400
    try:
        success = remove_tag_from_lesson(lesson_id, tag)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Tag not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tags')
@login_required
def api_get_all_tags():
    """Get all unique tags."""
    return jsonify(get_all_tags())


@app.route('/api/edit-tip', methods=['POST'])
@login_required
def edit_tip():
    """Edit a specific tip."""
    data_json = request.get_json()
    category = data_json.get('category')
    old_text = data_json.get('old_text')
    new_text = data_json.get('new_text')

    if not all([category, old_text, new_text]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        success = update_tip_in_db(category, old_text, new_text)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Tip not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-tip', methods=['POST'])
@login_required
def delete_tip():
    """Delete a specific tip."""
    data_json = request.get_json()
    category = data_json.get('category')
    text = data_json.get('text')

    if not all([category, text]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        success = delete_tip_from_db(category, text)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Tip not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def extract_pool_results_from_photo(image_path):
    """Extract pool results from a photo using Claude Vision API."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = image_path.suffix.lower()
    if ext == '.jpg' or ext == '.jpeg':
        media_type = "image/jpeg"
    elif ext == '.png':
        media_type = "image/png"
    elif ext == '.webp':
        media_type = "image/webp"
    else:
        raise ValueError(f"Unsupported image format: {ext}")

    message = get_claude_client().messages.create(
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
                    "text": """This is a photo of a fencing pool results sheet (grid format).

The fencer to track is SALIM Ethan (or the first fencer listed). Extract results from HIS ROW ONLY.

IMPORTANT: The pool sheet may be in one of three states:
1. EMPTY — names are listed but NO bouts have been fenced yet (all cells empty). Extract opponent names only.
2. PARTIAL — some bouts have scores, others are still empty. Extract what's available, use null for unfenced bouts.
3. COMPLETE — all bouts have scores and summary stats are filled in.

HOW TO READ THE POOL GRID:
- Each row is one fencer. The columns (numbered 1-6) correspond to each fencer's number.
- The cell where a fencer's row meets an opponent's column shows the result of THAT bout.
- D4 in a cell means the ROW fencer LOST and scored 4 touches. The opponent scored 5 (pool bouts go to 5).
- V5 in a cell means the ROW fencer WON and scored 5 touches. To find the opponent's score, look at the opponent's row in the column for our fencer.
- Black/diagonal cells are where a fencer's row meets their own column (no bout against yourself).
- EMPTY cells mean that bout has NOT been fenced yet.

EXAMPLE: If SALIM (row 1) has "D4" in column 2, that means:
  - SALIM lost to fencer #2
  - SALIM scored 4 touches (score_for = 4)
  - Fencer #2 scored 5 touches (score_against = 5)

If SALIM (row 1) has "V5" in column 4, that means:
  - SALIM beat fencer #4
  - SALIM scored 5 touches (score_for = 5)
  - To find fencer #4's score, look at row 4, column 1 (e.g., "D3" means they scored 3, so score_against = 3)

The right side of the grid shows summary stats (only present when pool is complete):
  - V = total victories
  - V/M = win rate (victories / matches)
  - TS = total touches scored
  - TR = total touches received
  - Ind = indicator (TS - TR)

Extract the following in JSON format:

{
  "pool_number": <number from "POOL #X">,
  "strip_number": <number from "ON STRIP X" or null>,
  "pool_status": "empty" | "partial" | "complete",
  "fencer_name": "<SALIM Ethan or first fencer's full name>",
  "fencer_club": "<club abbreviation / region>",
  "position_in_pool": <their ranking in the pool based on V column, 1=best, or null if not yet determined>,
  "victories": <V value from right side, or null if pool not complete>,
  "defeats": <number of bouts minus victories, or null>,
  "victory_rate": <V/M value, or null>,
  "touches_scored": <TS value, or null>,
  "touches_received": <TR value, or null>,
  "indicator": <Ind value, or null>,
  "bouts": [
    {
      "bout_order": <sequence 1, 2, 3...>,
      "opponent_name": "<opponent's full name from their row label>",
      "opponent_club": "<club / region from their row label>",
      "score_for": <our fencer's touches in this bout, or null if not yet fenced>,
      "score_against": <opponent's touches in this bout, or null if not yet fenced>,
      "result": "won" | "lost" | null
    }
  ]
}

CRITICAL RULES:
- score_for is ALWAYS our fencer's touches (the number after D or V in OUR row)
- score_against is the opponent's touches (5 for defeats, or cross-reference for victories)
- For D4: score_for=4, score_against=5, result="lost"
- For V5 against opponent who has D3 in our column: score_for=5, score_against=3, result="won"
- bout_order should match the column order (column 2=bout 1, column 3=bout 2, etc., skipping our own column)
- For bouts NOT YET FENCED (empty cells): set score_for=null, score_against=null, result=null — but STILL include the bout entry with the opponent's name
- ALWAYS include ALL opponents in the bouts array, even if no scores exist yet
- Return null for any field that's unclear or unreadable"""
                }
            ],
        }],
    )

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


# --- Tournament routes ---

@app.route('/tournaments')
@login_required
def tournaments_page():
    """Tournaments list page."""
    return render_template('tournaments.html', tournaments=get_tournaments())


@app.route('/tournaments/<int:tournament_id>')
@login_required
def tournament_detail_page(tournament_id):
    """Single tournament detail page."""
    tournament = get_tournament(tournament_id)
    if not tournament:
        return redirect(url_for('tournaments_page'))
    pool_data = get_pool_results(tournament_id)
    de_tips = get_de_prep_tips(tournament_id)
    de_results = get_de_results(tournament_id)
    de_summary = get_de_summary(tournament_id)
    return render_template('tournament_detail.html', tournament=tournament, pool_data=pool_data, de_tips=de_tips, de_results=de_results, de_summary=de_summary)


@app.route('/api/tournaments', methods=['POST'])
@login_required
def api_create_tournament():
    """Create a new tournament."""
    data = request.get_json()
    if not data.get('name') or not data.get('date'):
        return jsonify({'error': 'Name and date are required'}), 400
    try:
        tournament = create_tournament(data)
        return jsonify({'success': True, 'tournament': tournament})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tournaments', methods=['GET'])
@login_required
def api_list_tournaments():
    """List all tournaments."""
    return jsonify(get_tournaments())


@app.route('/api/tournaments/<int:tournament_id>', methods=['GET'])
@login_required
def api_get_tournament(tournament_id):
    """Get a single tournament."""
    tournament = get_tournament(tournament_id)
    if not tournament:
        return jsonify({'error': 'Tournament not found'}), 404
    return jsonify(tournament)


@app.route('/api/tournaments/<int:tournament_id>', methods=['POST'])
@login_required
def api_update_tournament(tournament_id):
    """Update a tournament."""
    data = request.get_json()
    try:
        tournament = update_tournament(tournament_id, data)
        if not tournament:
            return jsonify({'error': 'Tournament not found'}), 404
        return jsonify({'success': True, 'tournament': tournament})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tournaments/<int:tournament_id>/delete', methods=['POST'])
@login_required
def api_delete_tournament(tournament_id):
    """Delete a tournament."""
    try:
        success = delete_tournament(tournament_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Tournament not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-pool-photo', methods=['POST'])
@login_required
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

    filename = secure_filename(file.filename)
    filepath = app.config['UPLOAD_FOLDER'] / filename
    file.save(filepath)

    try:
        pool_data = extract_pool_results_from_photo(filepath)
        opponent_intel = _build_preview_opponent_intel(pool_data.get('bouts') or [])
        return jsonify({
            'success': True,
            'extracted_data': pool_data,
            'opponent_intel': opponent_intel,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if filepath.exists():
            filepath.unlink()


@app.route('/api/confirm-pool-results', methods=['POST'])
@login_required
def confirm_pool_results():
    """Save confirmed pool results to database."""
    data = request.get_json()
    tournament_id = data.get('tournament_id')
    pool_data = data.get('pool_data')

    if not all([tournament_id, pool_data]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        result = save_pool_results_to_db(tournament_id, pool_data)
        return jsonify({
            'success': True,
            'pool_round_id': result.get('pool_round_id'),
            'opponent_intel': result.get('opponent_intel') or [],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_de_prep_tips(tournament, pool_data):
    """Generate 5 quick DE prep tips from pool results using Claude."""
    # Build bout details string
    bout_lines = []
    for bout in pool_data.get('bouts', []):
        result_str = 'WIN' if bout['result'] == 'won' else 'LOSS'
        club_str = f" ({bout['opponent_club']})" if bout.get('opponent_club') else ''
        bout_lines.append(
            f"vs {bout['opponent_name']}{club_str}: "
            f"{bout['score_for']}-{bout['score_against']} {result_str}"
        )

    prompt = f"""You are Coach Ziad's assistant analyzing pool results for Ethan, a Y-12 epee fencer, right before his Direct Elimination (DE) rounds.

Tournament: {tournament['name']}
Date: {tournament['date']}

Pool Results:
Record: {pool_data['victories']}V-{pool_data['defeats']}D | Indicator: {pool_data['indicator']} | TS: {pool_data['touches_scored']} | TR: {pool_data['touches_received']}

Individual Bouts:
{chr(10).join(bout_lines)}

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
  {{"priority": 1, "category": "<category>", "tip": "<specific actionable tip>"}},
  {{"priority": 2, "category": "<category>", "tip": "<specific actionable tip>"}},
  {{"priority": 3, "category": "<category>", "tip": "<specific actionable tip>"}},
  {{"priority": 4, "category": "<category>", "tip": "<specific actionable tip>"}},
  {{"priority": 5, "category": "<category>", "tip": "<specific actionable tip>"}}
]"""

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        return json.loads(message.content[0].text)
    except json.JSONDecodeError:
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())


@app.route('/api/tournaments/<int:tournament_id>/de-prep-tips', methods=['POST'])
@login_required
def api_generate_de_prep_tips(tournament_id):
    """Generate DE prep tips from pool data."""
    tournament = get_tournament(tournament_id)
    if not tournament:
        return jsonify({'error': 'Tournament not found'}), 404

    pool_data = get_pool_results(tournament_id)
    if not pool_data:
        return jsonify({'error': 'No pool results found. Upload pool results first.'}), 400

    try:
        tips = generate_de_prep_tips(tournament, pool_data)
        saved = save_de_prep_tips(tournament_id, tips)
        return jsonify({'success': True, 'tips': saved})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tournaments/<int:tournament_id>/de-prep-tips', methods=['GET'])
@login_required
def api_get_de_prep_tips(tournament_id):
    """Retrieve saved DE prep tips."""
    tips = get_de_prep_tips(tournament_id)
    if not tips:
        return jsonify({'error': 'No tips found'}), 404
    return jsonify(tips)


def generate_de_summary(tournament, de_results):
    """Generate DE performance summary from elimination results using Claude."""
    our_fencer = de_results.get('our_fencer', {})
    seed = our_fencer.get('seed', 'Unknown')
    final_placement = our_fencer.get('final_placement_range', 'Unknown')

    bout_lines = []
    for bout in de_results.get('bouts', []):
        club_str = f" ({bout['opponent_club']})" if bout.get('opponent_club') else ''
        seed_str = f", seed #{bout['opponent_seed']}" if bout.get('opponent_seed') else ''
        bout_lines.append(
            f"Round: {bout['round_name']} | vs {bout['opponent_name']}{club_str}{seed_str} | "
            f"Score: {bout['score_for']}-{bout['score_against']} | {bout['result']}"
        )

    prompt = f"""You are an experienced epee fencing analyst reviewing a Y-12 fencer's Direct Elimination performance. The fencer is Ethan (coached by Ziad).

Tournament: {tournament['name']}
Date: {tournament['date']}

Ethan's Seed: {seed}
Final Placement: {final_placement}

DE Bouts:
{chr(10).join(bout_lines)}

Provide a performance analysis in JSON format:
{{
  "overall_assessment": "<2-3 sentence big-picture summary of the DE performance>",
  "bout_analyses": [
    {{
      "round_name": "<round>",
      "opponent": "<name>",
      "result": "won/lost",
      "analysis": "<1-2 sentences: what the score tells us about this bout>"
    }}
  ],
  "seed_performance": "<Did Ethan outperform his seed? Any upset wins? Compare seed to final placement>",
  "strengths": ["<specific strength shown in DEs>"],
  "areas_to_improve": ["<specific area based on the data>"],
  "ethan_takeaway": "<1-2 sentences written directly to Ethan, age-appropriate, encouraging but honest>",
  "coach_summary": "<2-3 sentences for Coach Ziad — what to focus on in lessons based on DE performance>"
}}

Rules:
- Reference SPECIFIC bout scores and opponent names/seeds
- Use epee-specific terminology (no right-of-way in epee)
- Analyze score margins (15-7 = dominant, 15-12 = close/competitive, 15-14 = could go either way)
- Note upset wins (beating a higher seed) as significant achievements
- Be honest but constructive — this is an 11-12 year old fencer
- The ethan_takeaway should be motivating, not deflating"""

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1536,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        return json.loads(message.content[0].text)
    except json.JSONDecodeError:
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())


@app.route('/api/tournaments/<int:tournament_id>/de-summary', methods=['POST'])
@login_required
def api_generate_de_summary(tournament_id):
    """Generate DE performance summary from saved DE results."""
    tournament = get_tournament(tournament_id)
    if not tournament:
        return jsonify({'error': 'Tournament not found'}), 404

    de_results = get_de_results(tournament_id)
    if not de_results or not de_results.get('bouts'):
        return jsonify({'error': 'No DE results found. Upload DE bracket first.'}), 400

    try:
        summary = generate_de_summary(tournament, de_results)
        saved = save_de_summary(tournament_id, summary)
        return jsonify({'success': True, 'summary': saved})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tournaments/<int:tournament_id>/de-summary', methods=['GET'])
@login_required
def api_get_de_summary(tournament_id):
    """Retrieve saved DE performance summary."""
    summary = get_de_summary(tournament_id)
    if not summary:
        return jsonify({'error': 'No summary found'}), 404
    return jsonify(summary)


@app.route('/api/upload-de-bracket', methods=['POST'])
@login_required
def upload_de_bracket():
    """Handle DE bracket photo upload and extraction."""
    if 'photos' not in request.files:
        return jsonify({'error': 'No photos uploaded'}), 400

    tournament_id = request.form.get('tournament_id')
    if not tournament_id:
        return jsonify({'error': 'Tournament ID required'}), 400

    our_fencer_name = request.form.get('fencer_name', 'SALIM Ethan')

    files = request.files.getlist('photos')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    if len(files) > 8:
        return jsonify({'error': 'Maximum 8 photos allowed'}), 400

    saved_paths = []
    try:
        for file in files:
            filename = secure_filename(file.filename)
            filepath = app.config['UPLOAD_FOLDER'] / f"de_{uuid.uuid4().hex[:8]}_{filename}"
            file.save(filepath)
            saved_paths.append(filepath)

        bracket_data = extract_full_de_bracket(
            saved_paths, our_fencer_name, tournament_id
        )

        our_fencer = (bracket_data or {}).get('our_fencer') or {}
        path_bouts = [
            b for b in (our_fencer.get('path') or [])
            if (b.get('opponent_name') or '').upper() != 'BYE'
        ]
        opponent_intel = _build_preview_opponent_intel(path_bouts)

        return jsonify({
            'success': True,
            'extracted_data': bracket_data,
            'images_processed': len(saved_paths),
            'opponent_intel': opponent_intel,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for path in saved_paths:
            if path.exists():
                path.unlink()


@app.route('/api/confirm-de-results', methods=['POST'])
@login_required
def confirm_de_results():
    """Save confirmed DE results to database."""
    data = request.get_json()
    tournament_id = data.get('tournament_id')
    bracket_data = data.get('bracket_data')

    if not all([tournament_id, bracket_data]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        result = save_de_results_to_db(tournament_id, bracket_data) or {}
        return jsonify({
            'success': True,
            'opponent_intel': result.get('opponent_intel') or [],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tournaments/<int:tournament_id>/de-results', methods=['GET'])
@login_required
def api_get_de_results(tournament_id):
    """Get saved DE results for a tournament."""
    results = get_de_results(tournament_id)
    if not results:
        return jsonify({'error': 'No DE results found'}), 404
    return jsonify(results)


# --- Phase 5: Final Results photo extraction + tournament summary ---

def _generate_tournament_narrative(tournament_id):
    """Generate a Claude-written narrative summary of the tournament.

    Pulls pool results, DE results, and the just-saved final rank / podium
    and asks Claude Sonnet for a 2-4 sentence summary. Stores the result
    (narrative + podium + final_rank + total_fencers + event_name) via
    `save_tournament_summary` and returns the serialized dict.

    Raises on Claude failure — caller should handle the error response.
    """
    tournament = get_tournament(tournament_id)
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")

    pool = get_pool_results(tournament_id)
    de = get_de_results(tournament_id)
    summary_row = get_tournament_summary(tournament_id)
    existing = (summary_row or {}).get('data') or {}

    final_rank = tournament.get('final_rank') or existing.get('final_rank')
    total_fencers = tournament.get('total_fencers') or existing.get('total_fencers')
    event_name = tournament.get('event_name') or existing.get('event_name')
    podium = existing.get('podium') or []

    # Build pool summary lines (only if pool data exists).
    pool_block = 'Pool: (not recorded)'
    if pool:
        pool_block_parts = [
            f"Record: {pool.get('victories', 0)}V-{pool.get('defeats', 0)}D",
            f"Indicator: {pool.get('indicator')}",
            f"TS/TR: {pool.get('touches_scored')}/{pool.get('touches_received')}",
        ]
        pool_block = "Pool: " + " | ".join(str(p) for p in pool_block_parts if p is not None)

    # Build DE summary.
    de_block = 'DE: (not recorded)'
    if de and de.get('bouts'):
        de_lines = []
        for bout in de['bouts']:
            score = ''
            if bout.get('score_for') is not None and bout.get('score_against') is not None:
                score = f" {bout['score_for']}-{bout['score_against']}"
            de_lines.append(
                f"{bout.get('round_name', '?')}: "
                f"{(bout.get('result') or '?').upper()} vs {bout.get('opponent_name', '?')}{score}"
            )
        de_block = "DE:\n  " + "\n  ".join(de_lines)

    # Podium block.
    if podium:
        podium_lines = []
        for row in podium:
            place = row.get('place') or '?'
            name = row.get('name') or '?'
            club = row.get('club') or ''
            podium_lines.append(f"{place}. {name} ({club})" if club else f"{place}. {name}")
        podium_block = "Podium:\n  " + "\n  ".join(podium_lines)
    else:
        podium_block = "Podium: (not recorded)"

    rank_line = ''
    if final_rank and total_fencers:
        rank_line = f"Ethan's final placement: {final_rank} of {total_fencers}"
    elif final_rank:
        rank_line = f"Ethan's final placement: {final_rank}"

    event_line = f"Event: {event_name}" if event_name else ""

    prompt = f"""You are an experienced epee fencing coach summarizing a Y-12 fencer's full tournament in 2-4 short sentences. The fencer is Ethan, coached by Ziad.

Tournament: {tournament['name']}
Date: {tournament['date']}
{event_line}
{rank_line}

{pool_block}

{de_block}

{podium_block}

Write a natural-language summary (2-4 sentences, no bullet points) covering:
1. Pool performance (record + what the indicator/scores suggest)
2. DE performance (how he did in elimination, any upset wins or tough losses)
3. Final placement relative to the field
4. ONE concrete tactical takeaway for the next tournament

Tone: honest but encouraging, age-appropriate for an 11-12 year old, no right-of-way (this is epee). Reference specific scores/opponents where useful. Do NOT wrap the output in JSON or markdown — just return the prose."""

    message = get_claude_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    narrative = (message.content[0].text or '').strip()

    payload = {
        'narrative': narrative,
        'podium': podium,
        'final_rank': final_rank,
        'total_fencers': total_fencers,
        'event_name': event_name,
        'warnings': existing.get('warnings') or [],
    }
    return save_tournament_summary(tournament_id, payload)


@app.route('/api/upload-final-results', methods=['POST'])
@login_required
def upload_final_results():
    """Handle Final Results screenshot upload + Vision extraction.

    Multi-image; mirrors `/api/upload-de-bracket`. Saves each file to
    UPLOAD_FOLDER, runs Claude Vision via `extract_final_results`, then
    deletes the temp files in `finally`.
    """
    if 'images' not in request.files:
        return jsonify({'error': 'No images uploaded'}), 400

    tournament_id = request.form.get('tournament_id')
    if not tournament_id:
        return jsonify({'error': 'Tournament ID required'}), 400

    files = request.files.getlist('images')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    if len(files) > 8:
        return jsonify({'error': 'Maximum 8 photos allowed'}), 400

    our_fencer_name = (
        request.form.get('fencer_name')
        or os.environ.get('DEFAULT_FENCER_NAME')
        or 'SALIM Ethan'
    )

    saved_paths = []
    try:
        for file in files:
            filename = secure_filename(file.filename)
            filepath = app.config['UPLOAD_FOLDER'] / f"final_{uuid.uuid4().hex[:8]}_{filename}"
            file.save(filepath)
            saved_paths.append(filepath)

        extracted = extract_final_results(
            saved_paths, our_fencer_name, tournament_id
        )

        return jsonify({
            'success': True,
            'extracted_data': extracted,
            'images_processed': len(saved_paths),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for path in saved_paths:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass


def _normalize_final_results_payload(raw):
    """Map extractor output (ethan_rank) to storage fields (final_rank).

    Accepts either key — the Vision extractor returns ``ethan_rank`` but the
    storage helper and Tournament column are named ``final_rank``. We also
    strip any fields the helper doesn't know about.
    """
    raw = raw or {}
    normalized = {}
    # ethan_rank is the extractor's name; final_rank is the column name.
    if 'final_rank' in raw:
        normalized['final_rank'] = raw.get('final_rank')
    elif 'ethan_rank' in raw:
        normalized['final_rank'] = raw.get('ethan_rank')
    if 'total_fencers' in raw:
        normalized['total_fencers'] = raw.get('total_fencers')
    if 'event_name' in raw:
        normalized['event_name'] = raw.get('event_name')
    if 'podium' in raw:
        normalized['podium'] = raw.get('podium') or []
    if 'warnings' in raw:
        normalized['warnings'] = raw.get('warnings') or []
    return normalized


@app.route('/api/confirm-final-results', methods=['POST'])
@login_required
def confirm_final_results():
    """Persist extracted final-results data + kick off narrative generation."""
    data = request.get_json(silent=True) or {}
    tournament_id = data.get('tournament_id')
    final_results = _normalize_final_results_payload(data.get('final_results'))

    if not tournament_id:
        return jsonify({'error': 'Missing tournament_id'}), 400

    try:
        tournament_id = int(tournament_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid tournament_id'}), 400

    # 404 when the tournament doesn't exist.
    if not get_tournament(tournament_id):
        return jsonify({'error': 'Tournament not found'}), 404

    try:
        # Persist rank/total/event/podium. Even an all-None payload is OK —
        # caller may just want to wipe and regenerate later.
        update_tournament_final_results(tournament_id, final_results)
    except Exception as e:
        return jsonify({'error': f'Failed to save final results: {e}'}), 500

    # Now generate the narrative. This hits Claude — let errors bubble
    # through with a clear message rather than silently swallowing them.
    try:
        summary = _generate_tournament_narrative(tournament_id)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Final results saved but narrative generation failed: {e}',
        }), 500

    return jsonify({'success': True, 'summary': summary})


@app.route('/api/tournaments/<int:tournament_id>/regenerate-summary', methods=['POST'])
@login_required
def api_regenerate_tournament_summary(tournament_id):
    """Regenerate the Claude narrative on demand."""
    if not get_tournament(tournament_id):
        return jsonify({'error': 'Tournament not found'}), 404

    try:
        summary = _generate_tournament_narrative(tournament_id)
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tournaments/<int:tournament_id>/summary', methods=['GET'])
@login_required
def api_get_tournament_summary(tournament_id):
    """Read the stored tournament summary."""
    summary = get_tournament_summary(tournament_id)
    if not summary:
        return jsonify({'error': 'No summary found'}), 404
    return jsonify(summary)


# --- Bout video routes (multiple videos per bout, pool and elim) ---

BOUT_VIDEO_MIME_MAP = {
    '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.avi': 'video/x-msvideo',
    '.mkv': 'video/x-matroska', '.m4v': 'video/x-m4v'
}


def _upload_bout_video(bout_kind, bout_id):
    if 'video' not in request.files:
        return jsonify({'error': 'No video file uploaded'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not bout_exists(bout_kind, bout_id):
        return jsonify({'error': 'Bout not found'}), 404

    original_filename = secure_filename(file.filename)
    file_ext = Path(original_filename).suffix.lower() or '.mp4'
    temp_filename = f"bout_{uuid.uuid4()}{file_ext}"
    filepath = app.config['UPLOAD_FOLDER'] / temp_filename
    file.save(filepath)

    try:
        r2_key = f"bout-videos/{bout_kind}_{bout_id}_{uuid.uuid4()}{file_ext}"
        bucket = os.environ.get('R2_BUCKET_NAME', 'fencing-lessons')
        content_type = BOUT_VIDEO_MIME_MAP.get(file_ext, 'video/mp4')
        get_r2_client().upload_file(
            str(filepath), bucket, r2_key,
            ExtraArgs={'ContentType': content_type}
        )

        video_id = add_bout_video(bout_kind, bout_id, r2_key)
        return jsonify({'success': True, 'video_id': video_id})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if filepath.exists():
            filepath.unlink()


@app.route('/api/pool-bouts/<int:bout_id>/videos', methods=['POST'])
@login_required
def api_upload_pool_bout_video(bout_id):
    return _upload_bout_video('pool', bout_id)


@app.route('/api/elimination-rounds/<int:bout_id>/videos', methods=['POST'])
@login_required
def api_upload_elim_bout_video(bout_id):
    return _upload_bout_video('elim', bout_id)


@app.route('/api/bout-videos/<int:video_id>', methods=['GET'])
@login_required
def api_get_bout_video_playback(video_id):
    v = get_bout_video(video_id)
    if not v:
        return jsonify({'error': 'Video not found'}), 404
    try:
        url = get_r2_client().generate_presigned_url(
            'get_object',
            Params={
                'Bucket': os.environ.get('R2_BUCKET_NAME', 'fencing-lessons'),
                'Key': v['r2_key']
            },
            ExpiresIn=3600
        )
        return jsonify({'url': url, 'expires_in': 3600})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bout-videos/<int:video_id>/delete', methods=['POST'])
@login_required
def api_delete_bout_video(video_id):
    r2_key = delete_bout_video(video_id)
    if r2_key is None:
        return jsonify({'error': 'Video not found'}), 404
    try:
        bucket = os.environ.get('R2_BUCKET_NAME', 'fencing-lessons')
        get_r2_client().delete_object(Bucket=bucket, Key=r2_key)
    except Exception:
        pass  # DB row already gone; stale R2 object is acceptable
    return jsonify({'success': True})


# --- Opponent preview helpers (used by pool/DE upload endpoints) ---

def _build_preview_opponent_intel(bouts):
    """Build an opponent_intel preview list (lookup-only — no stubs created).

    Each entry is aligned to the input bouts order with shape:
        {opponent_name, opponent_club, action, tier, opponent_id, known,
         name_score, club_score}

    ``action`` is 'auto_link' when the lookup returns Tier 1 or 2; otherwise
    'skipped' (we leave stub creation to the confirm/save step so the user
    can correct misread names before we persist anything).
    """
    if not bouts:
        return []
    names = []
    for b in bouts:
        names.append({'name': b.get('opponent_name') or '', 'club': b.get('opponent_club') or ''})
    try:
        matches = lookup_opponents_by_names(names) or []
    except Exception as e:
        print(f"[opponent-sync] preview lookup failed: {e}")
        matches = [{'query_name': n['name'], 'match': None} for n in names]

    intel = []
    for bout, entry in zip(bouts, matches):
        match = (entry or {}).get('match') or {}
        tier = match.get('tier')
        opp = match.get('opponent') or {}
        opponent_name = bout.get('opponent_name')
        opponent_club = bout.get('opponent_club')
        if not opponent_name or not str(opponent_name).strip():
            intel.append({
                'opponent_name': opponent_name,
                'opponent_club': opponent_club,
                'action': 'skipped',
                'tier': None,
                'opponent_id': None,
                'known': False,
                'name_score': 0,
                'club_score': 0,
            })
            continue
        if tier in (1, 2) and opp.get('id'):
            intel.append({
                'opponent_name': opponent_name,
                'opponent_club': opponent_club,
                'action': 'auto_link',
                'tier': tier,
                'opponent_id': opp.get('id'),
                'known': True,
                'name_score': int(match.get('name_score') or 0),
                'club_score': int(match.get('club_score') or 0),
            })
        else:
            intel.append({
                'opponent_name': opponent_name,
                'opponent_club': opponent_club,
                'action': 'skipped',
                'tier': tier,
                'opponent_id': opp.get('id'),
                'known': False,
                'name_score': int(match.get('name_score') or 0),
                'club_score': int(match.get('club_score') or 0),
            })
    return intel


# --- Opponent Intelligence routes ---

@app.route('/opponents')
@login_required
def opponents_page():
    """Opponent list page."""
    return render_template('opponents.html', opponents=get_all_opponents())


@app.route('/opponents/<int:opponent_id>')
@login_required
def opponent_profile_page(opponent_id):
    """Single opponent profile page."""
    opponent = get_opponent(opponent_id)
    if not opponent:
        return 'Opponent not found', 404
    head_to_head = get_head_to_head(opponent_id)
    return render_template(
        'opponent_profile.html',
        opponent=opponent,
        head_to_head=head_to_head,
    )


@app.route('/api/opponents', methods=['POST'])
@login_required
def api_create_opponent():
    """Create a new opponent."""
    data = request.get_json() or {}
    if not (data.get('canonical_name') or data.get('last_name') or data.get('first_name')):
        return jsonify({'error': 'Name is required (canonical_name or first_name/last_name)'}), 400
    try:
        opponent = create_opponent(data)
        return jsonify({'success': True, 'opponent': opponent})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opponents', methods=['GET'])
@login_required
def api_list_opponents():
    """List all opponents."""
    return jsonify({'opponents': get_all_opponents()})


@app.route('/api/opponents/<int:opponent_id>', methods=['GET'])
@login_required
def api_get_opponent(opponent_id):
    """Get a single opponent with head-to-head."""
    opponent = get_opponent(opponent_id)
    if not opponent:
        return jsonify({'error': 'Opponent not found'}), 404
    return jsonify({
        'opponent': opponent,
        'head_to_head': get_head_to_head(opponent_id),
    })


@app.route('/api/opponents/<int:opponent_id>', methods=['POST'])
@login_required
def api_update_opponent(opponent_id):
    """Update an opponent."""
    data = request.get_json() or {}
    try:
        opponent = update_opponent(opponent_id, data)
        if not opponent:
            return jsonify({'error': 'Opponent not found'}), 404
        return jsonify({'success': True, 'opponent': opponent})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opponents/<int:opponent_id>/delete', methods=['POST'])
@login_required
def api_delete_opponent(opponent_id):
    """Delete an opponent (cascades to notes and bout records)."""
    try:
        success = delete_opponent(opponent_id)
        if not success:
            return jsonify({'error': 'Opponent not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Tactical notes

@app.route('/api/opponents/<int:opponent_id>/notes', methods=['POST'])
@login_required
def api_add_tactical_note(opponent_id):
    """Add a tactical note for an opponent."""
    if not get_opponent(opponent_id):
        return jsonify({'error': 'Opponent not found'}), 404
    data = request.get_json() or {}
    if not data.get('observation'):
        return jsonify({'error': 'observation is required'}), 400
    try:
        note = add_tactical_note(opponent_id, data)
        return jsonify({'success': True, 'note': note})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opponents/<int:opponent_id>/notes/<int:note_id>', methods=['POST'])
@login_required
def api_update_tactical_note(opponent_id, note_id):
    """Update a tactical note."""
    data = request.get_json() or {}
    try:
        note = update_tactical_note(note_id, data)
        if not note:
            return jsonify({'error': 'Note not found'}), 404
        return jsonify({'success': True, 'note': note})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opponents/<int:opponent_id>/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def api_delete_tactical_note(opponent_id, note_id):
    """Delete a tactical note."""
    try:
        success = delete_tactical_note(note_id)
        if not success:
            return jsonify({'error': 'Note not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opponents/<int:opponent_id>/notes/<int:note_id>/validate', methods=['POST'])
@login_required
def api_validate_tactical_note(opponent_id, note_id):
    """Increment times_validated on a tactical note."""
    try:
        note = increment_note_validated(note_id)
        if not note:
            return jsonify({'error': 'Note not found'}), 404
        return jsonify({'success': True, 'note': note})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opponents/<int:opponent_id>/notes/<int:note_id>/invalidate', methods=['POST'])
@login_required
def api_invalidate_tactical_note(opponent_id, note_id):
    """Increment times_invalidated on a tactical note."""
    try:
        note = increment_note_invalidated(note_id)
        if not note:
            return jsonify({'error': 'Note not found'}), 404
        return jsonify({'success': True, 'note': note})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Search / filter

@app.route('/api/opponents/search', methods=['GET'])
@login_required
def api_search_opponents():
    """Fuzzy name search for opponents."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'matches': []})
    results = search_opponents_by_name(query)
    return jsonify({
        'matches': [{'opponent': opp, 'score': score} for opp, score in results]
    })


@app.route('/api/opponents/filter', methods=['GET'])
@login_required
def api_filter_opponents():
    """Filter opponents by trait fields (handedness, height_category, build, etc.)."""
    trait_fields = (
        'handedness', 'height_category', 'build', 'speed_rating',
        'primary_style', 'secondary_style', 'division',
    )
    filters = {}
    for field in trait_fields:
        value = request.args.get(field, '').strip()
        if value:
            filters[field] = value
    return jsonify({'opponents': search_opponents_by_traits(filters)})


@app.route('/api/opponents/lookup', methods=['POST'])
@login_required
def api_lookup_opponents():
    """Batch fuzzy lookup: POST {"names": ["JI Dylan", {"name":"...","club":"..."}, ...]}.

    Returns {matches: [...]} — one entry per input, in order, with the full match
    dict shape from ``lookup_opponents_by_names``.
    """
    data = request.get_json(silent=True) or {}
    names = data.get('names')
    if not isinstance(names, list):
        return jsonify({'error': '`names` must be a list'}), 400
    try:
        matches = lookup_opponents_by_names(names)
        return jsonify({'matches': matches})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Manual bout entry

@app.route('/api/opponents/<int:opponent_id>/bouts', methods=['POST'])
@login_required
def api_add_bout_record(opponent_id):
    """Add a historical bout record for an opponent."""
    if not get_opponent(opponent_id):
        return jsonify({'error': 'Opponent not found'}), 404
    data = request.get_json() or {}
    try:
        bout = add_bout_record(opponent_id, data)
        return jsonify({'success': True, 'bout': bout})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Pre-bout Intel (Phase 4) ---

def _format_trait_phrase(field, value):
    """Format a single opponent trait field+value into a human phrase.

    Only used by _build_opponent_intel when constructing ``physical_summary``.
    Returns None for empty / unknown values.
    """
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Snake-case → spaces, then title-case first letter.
    human = v.replace('_', ' ')
    if field == 'handedness':
        # "Left-handed" / "Right-handed"
        return f"{human.capitalize()}-handed"
    if field == 'height_category':
        # "Tall" / "Very tall" / "Short"
        return human.capitalize()
    if field == 'primary_style':
        # "aggressive style" / "counter-attacker style" etc. "style" flows
        # naturally after every allowed value.
        return f"{human.lower()} style"
    if field == 'speed_rating':
        # "fast" / "very fast" / "slow" — no extra word needed.
        return human.lower()
    return human.capitalize()


def _build_physical_summary(opponent):
    """Compose the one-line physical summary string, or None if no traits set."""
    if not opponent:
        return None
    parts = []
    for field in ('handedness', 'height_category', 'primary_style', 'speed_rating'):
        phrase = _format_trait_phrase(field, opponent.get(field))
        if phrase:
            parts.append(phrase)
    if not parts:
        return None
    return ', '.join(parts)


def _sort_notes_by_confidence(notes):
    """Sort notes by confidence DESC then created_at DESC; None-confidence last."""
    def key(n):
        conf = n.get('confidence')
        created = n.get('created_at') or ''
        # True sorts after False, so `conf is None` puts unset last.
        # Use negative confidence via inversion: rely on (1 - conf) so higher
        # confidences come first within the populated group.
        return (conf is None, -(conf or 0.0), )
    # Two-stage sort so created_at ties are broken newest-first.
    sorted_by_created = sorted(notes, key=lambda n: n.get('created_at') or '', reverse=True)
    return sorted(sorted_by_created, key=key)


def _build_opponent_intel(opponent_id):
    """Return the consolidated pre-bout intel dict for an opponent, or None.

    Shape matches the spec in PLAN_OPPONENT_INTELLIGENCE.md §2:
      { opponent, head_to_head, notes_by_section, physical_summary,
        last_encounter }
    """
    opponent = get_opponent(opponent_id)
    if not opponent:
        return None

    head_to_head = get_head_to_head(opponent_id) or {
        'wins': 0, 'losses': 0, 'touches_for': 0, 'touches_against': 0, 'bouts': []
    }
    all_notes = get_tactical_notes(opponent_id) or []

    what_works = [n for n in all_notes if (n.get('category') or '') == 'what_worked']
    watch_out_for = [
        n for n in all_notes
        if (n.get('category') or '') in ('favorite_action', 'tell')
    ]
    weaknesses = [n for n in all_notes if (n.get('category') or '') == 'weakness']

    notes_by_section = {
        'what_works': _sort_notes_by_confidence(what_works),
        'watch_out_for': _sort_notes_by_confidence(watch_out_for),
        'weaknesses': _sort_notes_by_confidence(weaknesses),
    }

    physical_summary = _build_physical_summary(opponent)

    last_encounter = None
    bouts = head_to_head.get('bouts') or []
    if bouts:
        # get_head_to_head returns bouts sorted newest-first already.
        top = bouts[0]
        last_encounter = {
            'tournament_name': top.get('tournament_name'),
            'tournament_date': top.get('tournament_date'),
            'result': (top.get('result') or None),
            'score_for': top.get('score_for'),
            'score_against': top.get('score_against'),
        }

    return {
        'opponent': opponent,
        'head_to_head': head_to_head,
        'notes_by_section': notes_by_section,
        'physical_summary': physical_summary,
        'last_encounter': last_encounter,
    }


@app.route('/opponents/<int:opponent_id>/intel')
@login_required
def opponent_intel_page(opponent_id):
    """Pre-bout intel page — the phone-glance briefing view."""
    intel = _build_opponent_intel(opponent_id)
    if not intel:
        return 'Opponent not found', 404
    return render_template('opponent_intel.html', **intel)


@app.route('/api/opponents/<int:opponent_id>/intel', methods=['GET'])
@login_required
def api_opponent_intel(opponent_id):
    """JSON payload used by the pre-bout intel page."""
    intel = _build_opponent_intel(opponent_id)
    if not intel:
        return jsonify({'error': 'Opponent not found'}), 404
    return jsonify(intel)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
