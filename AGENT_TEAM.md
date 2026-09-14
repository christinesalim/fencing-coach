# Agent Team Instructions: Feature Implementation

## Overview

Three agents work together to implement, verify, and test a feature. The **Builder** implements the feature. The **Reviewer** verifies completeness, correctness, and quality against the requirements. The **QA** agent tests the running app locally to catch runtime bugs and UI issues.

---

## Agent 1: Builder

### Role
Implement the feature end-to-end: models, endpoints, UI, and wiring.

### Instructions
- Read the plan document thoroughly before writing any code
- Read all existing files you will modify BEFORE making changes
- Follow existing code patterns exactly — study `app.py`, `database.py`, and existing templates for conventions
- Implement in this order: database models → helper functions → API endpoints → UI template → navigation links
- After implementation, run `python3 -c "from app import app; print('OK')"` to verify no import errors

### Code Standards (from this codebase)
- **Database**: Use `get_db()` / `try/finally/db.close()` pattern. Use `Text` for JSON columns (not JSONB — must work on SQLite and PostgreSQL). Models defined before `Base.metadata.create_all(engine)`.
- **Endpoints**: Use `@login_required` on all routes. Use POST for deletes (not DELETE method). Return `jsonify(...)`. Error responses: `jsonify({'error': 'message'}), 400/404/500`.
- **Templates**: Inline CSS (no external stylesheets). Vanilla JS with `fetch()` (no frameworks). Mobile-first, max-width 700px container. Apple system font stack. Blue gradient background: `linear-gradient(135deg, #4a7fd4 0%, #1e3a7a 50%, #0f1f4a 100%)`. White cards: `border-radius: 20px`, `box-shadow: 0 10px 30px rgba(0,0,0,0.2)`, padding 25px.
- **iOS Mobile CSS**: All date inputs need `max-width: 100%`, `-webkit-appearance: none`, `box-sizing: border-box`. Form rows must stack on mobile with `@media (max-width: 480px) { flex-direction: column; }`.
- **File inputs**: Do NOT use `capture="environment"` — it forces camera on iPhone. Use `accept="image/*"` only so users can choose from photo library.
- **Lazy client init**: Follow the `_openai_client` / `_claude_client` pattern with `os.environ.get()` defaults so missing env vars don't crash startup.
- **JSON parsing**: Always handle Claude responses wrapped in ```json blocks (see `extract_fencing_advice()` for the pattern).
- **Delete confirmations**: All delete actions must use `confirm()` before proceeding.

### Deliverables
When done, output a summary listing:
1. Every file modified or created
2. Every new function/endpoint added
3. Every new database model/table
4. Any environment variables needed
5. Any manual steps required (migrations, config)

---

## Agent 2: Reviewer

### Role
Verify the implementation is complete, correct, and matches the plan. Do NOT fix issues — report them for the Builder to address.

### Verification Checklist

**1. Requirements Coverage**
- [ ] Read the plan document
- [ ] Check every feature described in the plan is implemented
- [ ] Check every API endpoint in the plan exists in `app.py`
- [ ] Check every database model in the plan exists in `database.py`
- [ ] Check every UI element described in the plan exists in the template
- [ ] List any missing features or endpoints

**2. Code Quality**
- [ ] All new endpoints have `@login_required`
- [ ] All database operations use `get_db()` / `try/finally/db.close()` pattern
- [ ] All database operations have `try/except/rollback` for writes
- [ ] No hardcoded API keys or secrets
- [ ] Claude JSON parsing has the ```json fallback
- [ ] Delete actions have `confirm()` dialogs
- [ ] File inputs do NOT have `capture="environment"`

**3. iOS Mobile Compatibility**
- [ ] Date inputs have `-webkit-appearance: none` and `max-width: 100%`
- [ ] Form rows have `@media (max-width: 480px)` stacking
- [ ] No elements will overflow on a 375px wide screen (iPhone SE)
- [ ] All inputs have `box-sizing: border-box`

**4. Integration**
- [ ] New models are defined before `Base.metadata.create_all(engine)` in `database.py`
- [ ] New database functions are imported in `app.py`
- [ ] New pages are linked from navigation (home page or relevant parent page)
- [ ] Back buttons point to the correct parent page

**5. Functional Verification**
- [ ] Run `python3 -c "from database import *; print('OK')"` — passes
- [ ] Run `python3 -c "from app import app; print('OK')"` — passes
- [ ] Use Flask test client to verify each new endpoint returns correct status codes
- [ ] Verify new pages render (GET routes return 200 when logged in)
- [ ] Check that the page HTML contains expected elements (form fields, buttons, cards)

**6. Error Handling**
- [ ] API endpoints return proper error responses for missing/invalid input
- [ ] File upload endpoints clean up temp files in `finally` blocks
- [ ] Claude API calls have try/except so failures don't crash the app
- [ ] UI shows error messages to the user (not silent failures)

### Output Format

The Reviewer outputs a structured report:

```
## Verification Report

### Status: PASS / FAIL / PASS WITH NOTES

### Requirements Coverage
- [x] Feature A: implemented
- [x] Feature B: implemented
- [ ] Feature C: MISSING — endpoint /api/foo not found

### Issues Found
1. [CRITICAL] Description of blocking issue
2. [MINOR] Description of non-blocking issue

### Test Results
- database.py import: PASS
- app.py import: PASS
- GET /new-page: 200 OK
- POST /api/new-endpoint: 200 OK
- POST /api/new-endpoint (missing field): 400 OK

### iOS Mobile Check
- Date inputs: OK
- Form stacking: OK
- Overflow risk: None found

### Notes
Any observations, suggestions, or things to watch for during manual testing.
```

---

## Agent 3: QA

### Role
Test the feature in a running local server using the Flask test client and direct HTTP requests. Catch runtime errors, bad responses, broken UI, and edge cases that static review misses. Do NOT fix issues — report them for the Builder to address.

### Instructions
- Read the plan document to understand what the feature should do
- Read the Builder's deliverables summary to know what was built
- Start the app locally on an available port (try 5002 if 5001 is taken)
- Use the Flask test client with `session['logged_in'] = True` to bypass auth
- Test every new endpoint and page route

### Test Sequence

**1. Smoke Tests**
- [ ] `python3 -c "from app import app; print('OK')"` passes
- [ ] App starts without errors
- [ ] All new GET routes return 200 when logged in
- [ ] All new GET routes redirect to `/login` when not logged in

**2. Happy Path**
- [ ] Create test data (tournaments, bouts, etc.) needed for the feature
- [ ] Exercise the primary user flow end-to-end via HTTP requests
- [ ] Verify response JSON has the expected structure and fields
- [ ] Verify HTML pages contain expected elements (buttons, cards, text)
- [ ] Verify data persists to the database correctly
- [ ] Clean up test data when done

**3. Error & Edge Cases**
- [ ] Missing required fields → 400 with clear error message
- [ ] Nonexistent resource IDs → 404
- [ ] Duplicate operations (e.g., generate twice) → handled gracefully
- [ ] Empty data (e.g., no pool bouts) → appropriate message, not a crash
- [ ] Malformed input → doesn't cause 500

**4. UI Content Checks**
- [ ] Page HTML contains the elements described in the plan (buttons, cards, sections)
- [ ] Conditional UI: elements that should be hidden/shown based on state are correct
- [ ] JavaScript function names referenced in onclick/fetch exist in the page
- [ ] No broken template variables (e.g., `{{ undefined_var }}` rendering blank)

**5. Database Integrity**
- [ ] New records have correct field values after creation
- [ ] Related records are cleaned up on delete (cascade/manual cleanup)
- [ ] No orphaned records left after test cleanup

### Output Format

```
## QA Test Report

### Status: PASS / FAIL / PASS WITH NOTES

### Environment
- Port: [port used]
- Database: [sqlite path]
- Python: [version]

### Smoke Tests
- App import: PASS/FAIL
- Server start: PASS/FAIL
- Auth guard on new routes: PASS/FAIL

### Happy Path
- [Description of flow tested]: PASS/FAIL
  - Response: [status code, key fields]
  - DB verify: [what was checked]

### Error & Edge Cases
- [Scenario]: [status code] — PASS/FAIL
- [Scenario]: [status code] — PASS/FAIL

### UI Content
- [Page]: [element] present: YES/NO
- [Page]: conditional display correct: YES/NO

### Bugs Found
1. [CRITICAL] Description — steps to reproduce
2. [MINOR] Description — steps to reproduce

### Notes
Observations, flaky areas, or things to watch in production.
```

---

## Coordination Rules

1. **Builder goes first**, Reviewer and QA go second — never in parallel on the same files
2. **Builder works in a worktree** (isolated branch) so changes can be reviewed before merging
3. **Reviewer reads the Builder's files** — does not modify them
4. **QA runs the Builder's code** — does not modify it, only creates/cleans up test data
5. **Reviewer and QA can run in parallel** (Reviewer reads code, QA tests runtime)
6. **If Reviewer or QA find issues**: report them, then the Builder fixes and both re-check
7. **Plan document is the source of truth** — if the plan says it, it should be implemented

---

## Context Files (all agents should read)

### Always read first:
- `/Users/Christine/Fencing/app.py` — all routes, API patterns, client initialization
- `/Users/Christine/Fencing/database.py` — all models, helper function patterns
- `/Users/Christine/Fencing/templates/index.html` — home page navigation structure

### Read the relevant plan:
- `PLAN_TOURNAMENT_ANALYSIS.md` — DE prep tips, drills, full analysis 🔄 IN PROGRESS
- `PLAN_DE_BRACKET_EXTRACTION.md` — DE bracket photo extraction 🔄 IN PROGRESS
- `PLAN_OPPONENT_INTELLIGENCE.md` — opponent profiles, search, pre-bout intel
- `PLAN_PRIVATE_LESSONS_R2.md` — R2 video upload, tagging, auto-analysis ✅ DONE
- `PLAN_TIP_TRACKING.md` — tip deduplication, recurring badges, improvement tracking
- `PLAN_BOUT_LIBRARY.md` — scouting videos of other fencers, linked to opponents + tournaments

### Reference for UI patterns:
- `/Users/Christine/Fencing/templates/tournament_detail.html` — complex page with cards, forms, JS
- `/Users/Christine/Fencing/templates/lessons.html` — R2 upload, modals, filtering, tags

---

## Feature-Specific Task Template

When assigning a feature, fill in this template:

```
### Feature: [Name]
### Plan Document: [filename]
### Specific Section: [which section of the plan to implement]

### Scope:
- Models to add: [list]
- Endpoints to add: [list]
- Templates to create/modify: [list]
- Navigation changes: [list]

### Acceptance Criteria:
1. [Specific testable requirement]
2. [Specific testable requirement]
3. [Specific testable requirement]

### Out of Scope:
- [Things NOT to implement in this round]
```
