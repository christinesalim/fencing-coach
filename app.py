#!/usr/bin/env python3
"""Flask web app for fencing tips - upload voice memos and get tips."""

import os
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import openai
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

DATA_FILE = Path(__file__).parent / 'fencing_data.json'

# Initialize API clients
openai_client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def load_data():
    """Load existing fencing tips data."""
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "sessions": [],
        "combined_advice": {
            "patience_and_control": [],
            "distance_management": [],
            "reading_opponent": [],
            "when_ahead": [],
            "attack_execution": [],
            "defense_and_retreat": []
        }
    }


def save_data(data):
    """Save fencing tips data."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def transcribe(file_path):
    """Transcribe audio file using Whisper."""
    with open(file_path, "rb") as f:
        result = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return result


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
    data = load_data()
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

        # Load existing data
        data = load_data()

        # Add to combined advice (remove duplicates)
        for category, points in advice.items():
            if category in data['combined_advice']:
                for point in points:
                    if point.lower() not in [p.lower() for p in data['combined_advice'][category]]:
                        data['combined_advice'][category].append(point)

        # Add session
        session = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'filename': filename,
            'transcript': transcript,
            'advice': advice
        }
        data['sessions'].insert(0, session)  # Most recent first

        # Save data
        save_data(data)

        # Clean up uploaded file
        filepath.unlink()

        return jsonify({
            'success': True,
            'session': session,
            'combined_advice': data['combined_advice']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data')
def get_data():
    """Get all data as JSON."""
    return jsonify(load_data())


@app.route('/api/edit-tip', methods=['POST'])
def edit_tip():
    """Edit a specific tip."""
    data_json = request.get_json()
    category = data_json.get('category')
    old_text = data_json.get('old_text')
    new_text = data_json.get('new_text')

    if not all([category, old_text, new_text]):
        return jsonify({'error': 'Missing required fields'}), 400

    data = load_data()

    if category not in data['combined_advice']:
        return jsonify({'error': 'Invalid category'}), 400

    # Find and replace the tip
    tips = data['combined_advice'][category]
    if old_text in tips:
        index = tips.index(old_text)
        tips[index] = new_text
        save_data(data)
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Tip not found'}), 404


@app.route('/api/delete-tip', methods=['POST'])
def delete_tip():
    """Delete a specific tip."""
    data_json = request.get_json()
    category = data_json.get('category')
    text = data_json.get('text')

    if not all([category, text]):
        return jsonify({'error': 'Missing required fields'}), 400

    data = load_data()

    if category not in data['combined_advice']:
        return jsonify({'error': 'Invalid category'}), 400

    # Find and remove the tip
    tips = data['combined_advice'][category]
    if text in tips:
        tips.remove(text)
        save_data(data)
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Tip not found'}), 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
