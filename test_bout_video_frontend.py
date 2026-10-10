#!/usr/bin/env python3
"""Phase 3 smoke test: tournament_detail.html uses presign/PUT/register.

JS can't execute without a browser, so this verifies at the structure level:
  - Jinja template still parses
  - `uploadBoutVideo` function exists
  - New three-step flow is present (presign → XHR PUT → register)
  - Old `fetch(.../videos, FormData)` upload call is gone
  - Both pool and elim base URLs are built correctly
  - Progress hook + 30-min client timeout wired up
  - The clip-chip + wake-lock + counter plumbing was preserved

Exits 0 only if every check passes.
"""

import re
import sys
from pathlib import Path

import jinja2

TEMPLATE_PATH = Path(__file__).parent / "templates" / "tournament_detail.html"

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print("Phase 3 smoke test — tournament_detail.html upload swap")
    print("=" * 55)

    # 1. Template still parses as Jinja -------------------------------
    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_PATH.parent))
        )
        env.get_template(TEMPLATE_PATH.name)
        record("template: parses as valid Jinja", True)
    except Exception as e:
        record("template: parses as valid Jinja", False, str(e))
        print("Cannot continue without a parseable template.")
        sys.exit(1)

    src = TEMPLATE_PATH.read_text()

    # 2. uploadBoutVideo signature preserved (callers in HTML use it) --
    record(
        "signature: async function uploadBoutVideo(kind, boutId, input) still exists",
        "async function uploadBoutVideo(kind, boutId, input)" in src,
    )

    # 3. New three-step flow is present -------------------------------
    checks = [
        ("presign fetch URL",       "base + '/presign'" in src),
        ("register fetch URL",      "base + '/register'" in src),
        ("filename sent in presign",'JSON.stringify({filename: file.name})' in src),
        ("r2_key sent in register", "JSON.stringify({r2_key: presign.r2_key})" in src),
        ("XMLHttpRequest for PUT",  "new XMLHttpRequest()" in src and "xhr.open('PUT'" in src),
        ("Content-Type set on PUT", "setRequestHeader('Content-Type'" in src),
        ("upload progress hook",    "xhr.upload.onprogress" in src),
        ("30-minute timeout",       "30 * 60 * 1000" in src),
        ("timeout handler surfaces","Upload timed out" in src),
        ("progress % in status",    "pct + '%'" in src),
    ]
    for name, ok in checks:
        record(f"flow: {name}", ok)

    # 4. Old multipart POST to /videos is gone -------------------------
    # This is the pre-presign call — the exact pattern that hung on long uploads.
    # Permit the string "/videos" to still appear elsewhere, but reject
    # a fetch(... /videos, { method: 'POST', body: formData })-style call.
    old_pattern = re.search(
        r"fetch\(\s*uploadUrl\s*,\s*\{\s*method\s*:\s*'POST'\s*,\s*body\s*:\s*formData",
        src,
    )
    record(
        "no leftover multipart POST to /videos",
        old_pattern is None,
    )
    record(
        "no leftover formData.append('video', ...) in uploader",
        "formData.append('video'" not in src,
    )

    # 5. Base URL built correctly for both pool and elim ---------------
    record(
        "URL builder: pool prefix + /videos",
        "'/api/pool-bouts/'" in src and "'/videos'" in src,
    )
    record(
        "URL builder: elim prefix + /videos",
        "'/api/elimination-rounds/'" in src,
    )

    # 6. Preserved bookkeeping (we didn't accidentally delete these) ---
    for name, needle in [
        ("wake lock acquire",   "acquireBoutUploadWakeLock()"),
        ("wake lock release",   "releaseBoutUploadWakeLock()"),
        ("counter increment",   "totalBoutUploadsInFlight += files.length"),
        ("counter decrement",   "totalBoutUploadsInFlight--"),
        ("per-bout count map",  "boutUploadCounts[key]"),
        ("addClipChip on success", "addClipChip(container, registered.video_id)"),
        ("error status display",   "setBoutStatus(kind, boutId, 'Error uploading"),
    ]:
        record(f"preserved: {name}", needle in src)

    print()
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
