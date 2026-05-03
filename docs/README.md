# Fencing Coach App — Documentation

A personal coaching app for Ethan Salim (Y-12 epee fencer). Upload lesson recordings, tournament pool sheets, and DE brackets — AI extracts structured tips, results, and opponent intel.

**Stack:** Flask + SQLAlchemy + Jinja2 + vanilla JS | OpenAI Whisper + Anthropic Claude | Cloudflare R2 | Render

---

## Documentation

| Document | What it covers |
|----------|---------------|
| [Architecture](ARCHITECTURE.md) | System overview, tech stack, file structure, key design decisions |
| [Database](DATABASE.md) | All 19 SQLAlchemy models, ER diagram, relationships, constraints |
| [API](API.md) | All ~65 Flask routes grouped by feature, sequence diagrams for complex flows |
| [Features](FEATURES.md) | 8 major features with flowcharts — tips, lessons, tournaments, opponents, bout library |
| [Integrations](INTEGRATIONS.md) | OpenAI Whisper, Claude Vision, Cloudflare R2 — config, usage, error handling |
| [Deployment](DEPLOYMENT.md) | Render setup, env vars, local dev, migrations, maintenance scripts |

## Quick Start

```bash
# Local development
pip install -r requirements.txt
python app.py  # runs on port 5001
```

## Key Entry Points

- `app.py` — all routes and API endpoints (~2400 lines)
- `database.py` — all models and helper functions (~3000 lines)
- `templates/` — Jinja2 pages with inline CSS/JS
- `CLAUDE.md` — instructions for Claude Code when working on this codebase
