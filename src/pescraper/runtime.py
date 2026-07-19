"""Windows-native runtime hardening for the pescraper package.

The two most common Windows failure modes for this stack (per research/PITFALLS.md
Pitfall 8) are baked in here so every entry point that imports ``pescraper`` inherits
the fix:

1. Playwright (under Crawl4AI) needs the Proactor event-loop policy for subprocess
   support; the wrong policy raises ``NotImplementedError`` deep in
   ``_make_subprocess_transport``.
2. Windows' default cp1252/charmap console encoding raises ``UnicodeEncodeError`` on
   crawled Unicode content. Force UTF-8 stdio.

``configure_windows_runtime`` is idempotent and safe to call repeatedly and on
non-win32 platforms (the event-loop step is skipped off win32; UTF-8 is still forced).
"""

from __future__ import annotations

import asyncio
import os
import sys


def configure_windows_runtime() -> dict[str, object]:
    """Harden the process runtime for Windows-native operation.

    Idempotent. Returns a diagnostics dict describing the resulting runtime state.
    Never prints.
    """
    # (a) Event-loop policy: on win32, ensure the Proactor policy is active so that
    # Playwright's subprocess transport works. Only set it if the current policy is
    # not already Proactor, so we never fight another library that already set it.
    if sys.platform == "win32":
        proactor_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if proactor_cls is not None:
            current_policy = asyncio.get_event_loop_policy()
            if not isinstance(current_policy, proactor_cls):
                asyncio.set_event_loop_policy(proactor_cls())

    # (b) Force UTF-8 I/O (belt and suspenders): reconfigure stdio and set the
    # interpreter-level env vars so any child process / re-import also sees UTF-8.
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Non-reconfigurable stream (e.g. already-detached or a plain buffer
                # under pytest capture) — leave it as-is rather than crash.
                pass

    # (c) Diagnostics
    stdout_encoding = getattr(sys.stdout, "encoding", None)
    return {
        "platform": sys.platform,
        "python_version": "%d.%d.%d" % sys.version_info[:3],
        "event_loop_policy": type(asyncio.get_event_loop_policy()).__name__,
        "stdout_encoding": stdout_encoding,
        "pythonutf8": os.environ.get("PYTHONUTF8"),
    }
