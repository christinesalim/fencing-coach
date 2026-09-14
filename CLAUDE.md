# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Local development** (runs on port 5001):
```bash
source venv/bin/activate
python app.py
```

**Deploy**: push to `main`; Render auto-deploys via `render.yaml` (2–3 min).

**Install deps**: `pip install -r requirements.txt`

There is no test suite, linter, or build step.

## Architecture

Flask app (`app.py`) + SQLAlchemy data layer (`database.py`) + Jinja templates (`templates/`). Two-service AI pipeline: OpenAI Whisper for transcription, Anthropic Claude (`claude-sonnet-4-6`) for structured tip extraction.

**Upload flow** (`/upload` in `app.py`): save file → if video, `extract_audio_from_video` via moviepy → `transcribe` (Whisper) → `extract_fencing_advice` returns JSON keyed by six fixed categories (`patience_and_control`, `distance_management`, `reading_opponent`, `when_ahead`, `attack_execution`, `defense_and_retreat`) → `save_session_to_db` persists a `Session` row and inserts each bullet as a `Tip` (dedup by unique `text`).

**Category invariant**: the six category keys are hardcoded in three places — Claude prompt in `extract_fencing_advice`, `combined_advice` dict in `load_data_from_db`, and the templates. Adding/renaming a category requires updating all three.

**Dedup**: `Tip.text` has a DB unique constraint, and `save_session_to_db` pre-checks existence. Tips accumulate across sessions; editing a tip via `/api/edit-tip` must not collide with an existing row.

**DB URL resolution** (`get_database_url` in `database.py`): uses `DATABASE_URL` env var in prod (rewrites `postgres://` → `postgresql://` for SQLAlchemy), falls back to local SQLite `fencing_data.db`. `Base.metadata.create_all` runs at import time — new models are auto-created but schema changes on existing tables need manual migration.

**API clients are lazy** (`get_openai_client`/`get_claude_client`): missing `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` must not crash startup (Render needs the app to boot before env vars are set). Preserve this pattern — don't instantiate clients at module scope.

**Auth**: single shared password via `APP_PASSWORD` env var, enforced by `@login_required` decorator. Every route except `/login` should have it.

**File size limit**: 200MB (`MAX_CONTENT_LENGTH`) to accommodate lesson videos. Uploaded files in `uploads/` are deleted after processing (both success and error paths).

## Context

Personal app for one user (Ethan Salim, Y-12 épée fencer). See `APP_SUMMARY.md` for feature inventory and `FUTURE_DATABASE_MODEL.md` for planned tournament/opponent/lesson schemas that haven't been built yet.
