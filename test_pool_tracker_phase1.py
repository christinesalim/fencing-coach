#!/usr/bin/env python3
"""Pool Tracker Phase 1 — Vision extraction + upload endpoint.

Mocks the Claude client so no real API call happens. Verifies:
  - Vision function parses a JSON response + JSON-in-codeblock response
  - Vision function matches Ethan on both first AND last name
  - /api/upload-pool-order-photo endpoint wires the function up correctly
    (auth, file handling, error path, success path, tmp-file cleanup)

Exits 0 only if every scenario PASSes.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import app as app_module
from app import app, extract_pool_bout_order_from_photo


UPLOAD_FOLDER = Path(__file__).parent / "uploads"
results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def authed_client():
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    return c


SAMPLE_RESPONSE = {
    "pool_number": 5,
    "strip": 6,
    "roster": [
        {"pool_num": 1, "last_name": "BOROVIKOV", "first_name": "Alexander", "club": "AFM", "region": "Central California"},
        {"pool_num": 2, "last_name": "ZHU",       "first_name": "Alexander", "club": "AFM", "region": "Central California"},
        {"pool_num": 3, "last_name": "SALIM",     "first_name": "Ethan",     "club": "AFM", "region": "Central California"},
        {"pool_num": 4, "last_name": "HOLBROOK",  "first_name": "Kieran",    "club": "EBFG", "region": "Northern California"},
        {"pool_num": 5, "last_name": "XIAO",      "first_name": "Yijian",    "club": "BAYFC", "region": "Central California"},
        {"pool_num": 6, "last_name": "POLIAKOV",  "first_name": "Timur",     "club": "CAP", "region": "Central California"},
    ],
    "bouts": [
        {"order": 1, "right_num": 1, "left_num": 2},
        {"order": 2, "right_num": 4, "left_num": 5},
        {"order": 3, "right_num": 2, "left_num": 3},
    ],
    "ethan_pool_num": 3,
}


def install_claude_mock(response_text):
    """Replace app.get_claude_client so no real Anthropic call happens.

    Sets the Vision call to return a Message whose first content block has
    the provided text (which Vision parses as JSON).
    """
    content_block = MagicMock()
    content_block.text = response_text
    message = MagicMock()
    message.content = [content_block]
    claude = MagicMock()
    claude.messages.create = MagicMock(return_value=message)
    app_module.get_claude_client = lambda: claude
    return claude


def write_fake_png():
    """Write a tiny PNG header so suffix detection works. Content doesn't
    matter — Claude is mocked."""
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    p = UPLOAD_FOLDER / "pool_order_phase1_test.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
    return p


def main():
    print("Pool Tracker Phase 1 — Vision + upload endpoint")
    print("=" * 55)

    # 1. Happy path: raw JSON response ---------------------------------
    install_claude_mock(json.dumps(SAMPLE_RESPONSE))
    p = write_fake_png()
    try:
        got = extract_pool_bout_order_from_photo(p)
        record(
            "vision: raw JSON response parsed to dict",
            got.get("pool_number") == 5
            and got.get("ethan_pool_num") == 3
            and len(got.get("roster") or []) == 6
            and len(got.get("bouts") or []) == 3,
            f"keys={sorted((got or {}).keys())}",
        )
    finally:
        if p.exists():
            p.unlink()

    # 2. Vision wraps JSON in a ```json block --------------------------
    wrapped = "Here's what I see:\n```json\n" + json.dumps(SAMPLE_RESPONSE) + "\n```\nHope this helps."
    install_claude_mock(wrapped)
    p = write_fake_png()
    try:
        got = extract_pool_bout_order_from_photo(p)
        record(
            "vision: JSON-in-codeblock response parsed",
            got.get("ethan_pool_num") == 3,
            f"ethan_pool_num={got.get('ethan_pool_num')}",
        )
    finally:
        if p.exists():
            p.unlink()

    # 3. Unsupported file extension raises -----------------------------
    install_claude_mock(json.dumps(SAMPLE_RESPONSE))
    p = UPLOAD_FOLDER / "pool_order_phase1_test.gif"
    p.write_bytes(b"GIF89a")
    try:
        extract_pool_bout_order_from_photo(p)
        record("vision: unsupported ext raises ValueError", False, "no exception")
    except ValueError as e:
        record("vision: unsupported ext raises ValueError", "Unsupported" in str(e), str(e))
    except Exception as e:
        record("vision: unsupported ext raises ValueError", False, f"wrong exc: {type(e).__name__}")
    finally:
        if p.exists():
            p.unlink()

    # 4. Endpoint: unauth → 302 /login ---------------------------------
    r = app.test_client().post("/api/upload-pool-order-photo")
    record(
        "endpoint: unauth redirect to /login",
        r.status_code == 302 and "/login" in (r.headers.get("Location") or ""),
        f"status={r.status_code} loc={r.headers.get('Location')}",
    )

    # 5. Endpoint: missing photo → 400 ---------------------------------
    c = authed_client()
    r = c.post("/api/upload-pool-order-photo",
               data={}, content_type="multipart/form-data")
    body = r.get_json() or {}
    record(
        "endpoint: missing photo returns 400",
        r.status_code == 400 and "error" in body,
        f"status={r.status_code} body={body}",
    )

    # 6. Endpoint: empty filename → 400 --------------------------------
    r = c.post(
        "/api/upload-pool-order-photo",
        data={"photo": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )
    body = r.get_json() or {}
    record(
        "endpoint: empty filename returns 400",
        r.status_code == 400 and "error" in body,
        f"status={r.status_code} body={body}",
    )

    # 7. Endpoint: happy path returns extracted_data -------------------
    install_claude_mock(json.dumps(SAMPLE_RESPONSE))
    r = c.post(
        "/api/upload-pool-order-photo",
        data={"photo": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 64), "ftl_pool_5.png")},
        content_type="multipart/form-data",
    )
    body = r.get_json() or {}
    extracted = body.get("extracted_data") or {}
    record(
        "endpoint: happy path returns extracted_data w/ roster+bouts+ethan_pool_num",
        r.status_code == 200
        and body.get("success") is True
        and extracted.get("pool_number") == 5
        and extracted.get("ethan_pool_num") == 3
        and len(extracted.get("roster") or []) == 6
        and len(extracted.get("bouts") or []) == 3,
        f"status={r.status_code} success={body.get('success')} pn={extracted.get('pool_number')}",
    )

    # 8. Endpoint: Vision error surfaces as 500 JSON -------------------
    broken = MagicMock()
    broken.messages.create = MagicMock(side_effect=RuntimeError("mock vision failure"))
    app_module.get_claude_client = lambda: broken
    r = c.post(
        "/api/upload-pool-order-photo",
        data={"photo": (io.BytesIO(b"\x89PNG\r\n\x1a\n"), "x.png")},
        content_type="multipart/form-data",
    )
    body = r.get_json() or {}
    record(
        "endpoint: Vision exception → 500 w/ error json",
        r.status_code == 500 and "mock vision failure" in (body.get("error") or ""),
        f"status={r.status_code} body={body}",
    )

    # 9. Endpoint cleans up its temp file -------------------------------
    # The uploads/ folder should not have any pool_order_*.png left over
    # from the successful run above.
    leftover = list(UPLOAD_FOLDER.glob("pool_order_*.png")) if UPLOAD_FOLDER.exists() else []
    record(
        "endpoint: temp upload file deleted after request",
        not leftover,
        f"leftover={leftover}",
    )

    # 10. Ethan-matching semantics --------------------------------------
    # The matching is instructed via the prompt, so we can't execute it
    # locally — but we can confirm the prompt actually says "both must match".
    prompt_text = None
    install_claude_mock(json.dumps(SAMPLE_RESPONSE))
    p = write_fake_png()
    try:
        extract_pool_bout_order_from_photo(p)
        call = app_module.get_claude_client().messages.create.call_args
        content_blocks = call.kwargs["messages"][0]["content"]
        prompt_text = next(b["text"] for b in content_blocks if b.get("type") == "text")
    finally:
        if p.exists():
            p.unlink()
    record(
        "vision prompt: requires BOTH first_name=Ethan AND last_name=SALIM",
        prompt_text is not None
        and 'first_name is "Ethan"' in prompt_text
        and 'last_name is "SALIM"' in prompt_text
        and "both must match" in prompt_text,
        f"prompt_has_both_match={'both must match' in (prompt_text or '')}",
    )

    print()
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("All tests passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
