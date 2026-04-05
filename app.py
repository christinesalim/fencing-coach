#!/usr/bin/env python3
"""Flask web app for fencing tips - upload voice memos and get tips."""

import os
from pathlib import Path
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
import openai
import anthropic
from dotenv import load_dotenv
from database import (
    load_data_from_db,
    save_session_to_db,
    update_tip_in_db,
    delete_tip_from_db
)

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size (for videos)
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

ALLOWED_AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.aac', '.ogg', '.flac'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}

# Initialize API clients
openai_client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def extract_audio_from_video(video_path):
    """Extract audio from video file and save as temporary audio file."""
    from moviepy.editor import VideoFileClip

    audio_path = video_path.with_suffix('.mp3')

    try:
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
            result = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        return result
    finally:
        # Clean up extracted audio file
        if extracted_audio and audio_path.exists():
            audio_path.unlink()


def extract_fencing_advice(transcript, filename):
    """Extract actionable fencing advice from transcript."""
    message = claude_client.messages.create(
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


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/tips')
def tips():
    """View all tips."""
    data = load_data_from_db()
    return render_template('tips.html', data=data)


@app.route('/upload', methods=['POST'])
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
def get_data():
    """Get all data as JSON."""
    return jsonify(load_data_from_db())


@app.route('/api/edit-tip', methods=['POST'])
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
