#!/usr/bin/env python3
"""Transcribe voice memos and summarize them using OpenAI Whisper + Claude."""

import os
import glob
from pathlib import Path
import openai
import anthropic
from dotenv import load_dotenv

load_dotenv()

AUDIO_DIR = Path(__file__).parent
OUTPUT_FILE = AUDIO_DIR / "transcripts_and_summaries.md"
NOTEBOOK_FILE = AUDIO_DIR / "fencing_notebook.md"
TIPS_FILE = AUDIO_DIR / "fencing_tips_printable.md"


def transcribe(file_path: Path, openai_client: openai.OpenAI) -> str:
    print(f"  Transcribing {file_path.name}...")
    with open(file_path, "rb") as f:
        result = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return result


def summarize(transcript: str, filename: str, claude_client: anthropic.Anthropic) -> str:
    print(f"  Summarizing {filename}...")
    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"The following is a transcript of a voice memo called '{filename}'.\n\n"
                    f"{transcript}\n\n"
                    "Please provide a concise summary (3-5 sentences) capturing the key points."
                ),
            }
        ],
    )
    return message.content[0].text


def extract_fencing_advice(transcript: str, filename: str, claude_client: anthropic.Anthropic) -> dict:
    print(f"  Extracting fencing advice from {filename}...")
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
    import json
    try:
        return json.loads(message.content[0].text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())


def main():
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not openai_key:
        raise SystemExit("Error: OPENAI_API_KEY environment variable not set.")
    if not anthropic_key:
        raise SystemExit("Error: ANTHROPIC_API_KEY environment variable not set.")

    openai_client = openai.OpenAI(api_key=openai_key)
    claude_client = anthropic.Anthropic(api_key=anthropic_key)

    audio_files = sorted(AUDIO_DIR.glob("*.m4a"))
    if not audio_files:
        raise SystemExit("No .m4a files found in the current directory.")

    results = []
    all_advice = {
        "patience_and_control": [],
        "distance_management": [],
        "reading_opponent": [],
        "when_ahead": [],
        "attack_execution": [],
        "defense_and_retreat": []
    }

    for audio_file in audio_files:
        print(f"\nProcessing: {audio_file.name}")
        transcript = transcribe(audio_file, openai_client)
        summary = summarize(transcript, audio_file.name, claude_client)
        advice = extract_fencing_advice(transcript, audio_file.name, claude_client)
        results.append((audio_file.name, transcript, summary, advice))

        # Merge advice into all_advice
        for category, points in advice.items():
            if category in all_advice:
                all_advice[category].extend(points)

    # Write transcripts and summaries
    with open(OUTPUT_FILE, "w") as out:
        out.write("# Voice Memo Transcripts and Summaries\n\n")
        for filename, transcript, summary, _ in results:
            out.write(f"## {filename}\n\n")
            out.write(f"### Summary\n\n{summary}\n\n")
            out.write(f"### Full Transcript\n\n{transcript}\n\n")
            out.write("---\n\n")

    # Load existing notebook advice if it exists
    from datetime import datetime
    import json

    existing_sessions = []
    if NOTEBOOK_FILE.exists():
        with open(NOTEBOOK_FILE, "r") as f:
            content = f.read()
            # Try to extract previous sessions from JSON comment
            if "<!-- SESSIONS_DATA" in content:
                try:
                    json_data = content.split("<!-- SESSIONS_DATA\n")[1].split("\n-->")[0]
                    existing_sessions = json.loads(json_data)
                except (IndexError, json.JSONDecodeError):
                    pass

    # Add current session
    current_session = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "files": [f for f, _, _, _ in results],
        "advice": all_advice
    }
    existing_sessions.append(current_session)

    # Write fencing notebook
    with open(NOTEBOOK_FILE, "w") as out:
        out.write("# Fencing Competition Notebook\n\n")
        out.write("*Review these key points before competitions*\n\n")
        out.write("---\n\n")

        # Combine all advice across all sessions
        combined_advice = {
            "patience_and_control": [],
            "distance_management": [],
            "reading_opponent": [],
            "when_ahead": [],
            "attack_execution": [],
            "defense_and_retreat": []
        }

        for session in existing_sessions:
            for category, points in session["advice"].items():
                if category in combined_advice:
                    combined_advice[category].extend(points)

        # Remove duplicates while preserving order
        for category in combined_advice:
            seen = set()
            unique_points = []
            for point in combined_advice[category]:
                if point.lower() not in seen:
                    seen.add(point.lower())
                    unique_points.append(point)
            combined_advice[category] = unique_points

        # Write organized advice
        category_titles = {
            "patience_and_control": "🎯 Patience and Control",
            "when_ahead": "📊 When You're Ahead",
            "distance_management": "📏 Distance Management",
            "defense_and_retreat": "🛡️ Defense and Retreat",
            "reading_opponent": "👁️ Reading Your Opponent",
            "attack_execution": "⚔️ Attack Execution"
        }

        for category, title in category_titles.items():
            if combined_advice[category]:
                out.write(f"## {title}\n\n")
                for point in combined_advice[category]:
                    out.write(f"- {point}\n")
                out.write("\n")

        # Add session history
        out.write("---\n\n")
        out.write("## Training Session History\n\n")
        for i, session in enumerate(reversed(existing_sessions), 1):
            out.write(f"### Session {len(existing_sessions) - i + 1} - {session['date']}\n")
            out.write(f"Files reviewed: {', '.join(session['files'])}\n\n")

        # Store sessions data as JSON comment for next run
        out.write("\n<!-- SESSIONS_DATA\n")
        out.write(json.dumps(existing_sessions, indent=2))
        out.write("\n-->\n")

    # Write printable tips file (clean version without history)
    with open(TIPS_FILE, "w") as out:
        out.write("# Fencing Competition Tips\n\n")
        out.write("---\n\n")

        for category, title in category_titles.items():
            if combined_advice[category]:
                out.write(f"## {title}\n\n")
                for point in combined_advice[category]:
                    out.write(f"- {point}\n")
                out.write("\n")

    print(f"\nDone! Results saved to:")
    print(f"  - {OUTPUT_FILE}")
    print(f"  - {NOTEBOOK_FILE}")
    print(f"  - {TIPS_FILE} (printable version)")


if __name__ == "__main__":
    main()
