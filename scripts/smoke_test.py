"""One-command Windows-native smoke test (requirement ENVR-01).

Run it with the single documented command:

    uv run python scripts/smoke_test.py

Equivalent to the CLI entry point:

    uv run pescraper doctor

Both validate the three runtime seams and share one exit-code contract:

    exit 0  -> all three seams GREEN (Python 3.11 + Proactor + UTF-8;
               Ollama qwen3:4b structured-output round-trip; Crawl4AI health
               via crawl4ai-doctor + a real headless Chromium launch)
    exit != 0 -> at least one seam FAILED

A non-zero exit means at least one seam is down. The command is side-effect-free
and safe to re-run unattended as a health probe.

Importing this runner imports :mod:`pescraper` (via ``pescraper.doctor``), which
activates the Windows runtime hardening (asyncio Proactor policy + UTF-8 stdio) as
an import side effect *before* any check runs.
"""

from __future__ import annotations

import sys

from pescraper.doctor import main

if __name__ == "__main__":
    sys.exit(main())
