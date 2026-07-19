"""Windows-native runtime smoke test — the three-seam go/no-go health check.

This module is the target of the ``pescraper doctor`` CLI command (lazily imported
from :mod:`pescraper.cli`) and of :mod:`scripts.smoke_test`. It empirically proves
the three runtime seams the whole pipeline depends on, exits non-zero on ANY failed
seam, and never raises out of a check — so it is safe to re-run unattended as a
health probe.

The three seams (Phase 1 success criterion 1, requirement ENVR-01):

1. **runtime** — Python >= 3.11, the asyncio Proactor event-loop policy active on
   win32 (Playwright subprocess support), and UTF-8 stdio.
2. **ollama** — a qwen3:4b *structured-output* round-trip against localhost:11434:
   ``format=<pydantic JSON schema>`` with ``options={"num_ctx": 8192, ...}`` whose
   response validates into a pydantic model. This mirrors the Phase 2 extraction
   contract exactly (research/STACK.md "Extraction call shape"), so the highest-
   variance seam — a 4B model returning schema-valid JSON — is proven now. A bare
   completion is deliberately NOT acceptable here.
3. **crawl4ai** — ``crawl4ai-doctor`` returns 0 AND a real headless Chromium launch
   succeeds via ``AsyncWebCrawler`` over an inline ``raw://`` document (no external
   network), not merely an import.

``HealthPing`` is intentionally a tiny 2-field model, NOT the 24-column FirmRecord,
so this module has zero dependency on ``models.py``/``db.py`` and can run in parallel
with the DB plan. It exists only to exercise the structured-output contract shape.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from pydantic import BaseModel

# Importing the package activates the Windows runtime hardening (Proactor + UTF-8)
# as an import side effect, so every entry point that reaches this module runs under
# the hardened runtime before any check executes.
import pescraper  # noqa: F401
from pescraper.runtime import crawl4ai_browser_kwargs


@dataclass
class CheckResult:
    """Outcome of a single seam check. ``ok`` drives the aggregate exit code."""

    name: str
    ok: bool
    detail: str


class HealthPing(BaseModel):
    """Tiny structured-output contract for the Ollama round-trip.

    Deliberately not the 24-column FirmRecord — this only proves that qwen3:4b can
    return schema-constrained JSON that validates into a pydantic v2 model.
    """

    ok: bool
    model: str


_THINK_BLOCK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


def _strip_think(content: str) -> str:
    """Defensively strip a leading ``<think>...</think>`` block (PITFALLS Pitfall 3).

    qwen3 is a hybrid reasoning model; even with thinking disabled, stray think
    content can leak and break JSON parsing. Strip it before validation regardless.
    """
    return _THINK_BLOCK.sub("", content or "")


def check_runtime() -> CheckResult:
    """Seam 1: Python >= 3.11, win32 Proactor policy active, UTF-8 stdio."""
    try:
        details: list[str] = []
        ok = True

        py = sys.version_info
        details.append(f"python={py.major}.{py.minor}.{py.micro}")
        ok = ok and py >= (3, 11)

        policy = asyncio.get_event_loop_policy()
        details.append(f"loop_policy={type(policy).__name__}")
        if sys.platform == "win32":
            proactor_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
            ok = ok and proactor_cls is not None and isinstance(policy, proactor_cls)

        enc = getattr(sys.stdout, "encoding", None)
        details.append(f"stdout_encoding={enc}")
        norm = (enc or "").replace("-", "").lower()
        ok = ok and norm == "utf8"

        details.append(f"platform={sys.platform}")
        return CheckResult("runtime", ok, "; ".join(details))
    except Exception as exc:  # never raise out of a check
        return CheckResult("runtime", False, f"runtime check errored: {exc!r}")


def check_ollama(model: str = "qwen3:4b") -> CheckResult:
    """Seam 2: qwen3:4b structured-output round-trip validated into ``HealthPing``.

    Sends ``format=HealthPing.model_json_schema()`` with ``num_ctx=8192`` and
    ``temperature=0`` (mirrors the Phase 2 extraction contract), disables qwen3
    thinking, strips any stray think block, and requires the response to validate
    into ``HealthPing``. Wraps every failure as ``ok=False``; never raises.
    """
    try:
        import ollama

        schema = HealthPing.model_json_schema()
        messages = [
            {
                "role": "user",
                "content": (
                    "This is a health check. Reply with ONLY a JSON object matching "
                    'the schema: set "ok" to true and "model" to the string '
                    f'"{model}". No prose, no explanation.'
                ),
            }
        ]
        options = {"num_ctx": 8192, "temperature": 0}

        # Disable qwen3 thinking (PITFALLS Pitfall 3). Older clients lack the
        # ``think`` kwarg — fall back to a call without it.
        try:
            resp = ollama.chat(
                model=model,
                messages=messages,
                format=schema,
                options=options,
                think=False,
            )
        except TypeError:
            resp = ollama.chat(
                model=model,
                messages=messages,
                format=schema,
                options=options,
            )

        content = _strip_think(resp.message.content)
        ping = HealthPing.model_validate_json(content)
        return CheckResult(
            "ollama",
            True,
            f"{model} structured round-trip @localhost:11434 -> "
            f"HealthPing(ok={ping.ok}, model={ping.model!r})",
        )
    except Exception as exc:
        return CheckResult(
            "ollama",
            False,
            f"{model} structured-output round-trip failed "
            f"(is the Ollama app serving {model} on localhost:11434?): {exc!r}",
        )


async def _launch_chromium_once() -> tuple[bool, str]:
    """Launch headless Chromium once over an inline ``raw://`` document."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    html = (
        "<html><head><meta charset='utf-8'><title>pescraper doctor</title></head>"
        "<body><h1>pescraper doctor</h1><p>chromium launch ok</p></body></html>"
    )
    async with AsyncWebCrawler(config=BrowserConfig(**crawl4ai_browser_kwargs())) as crawler:
        result = await crawler.arun(url="raw://" + html)
    return bool(result.success), (result.error_message or "").strip()


def check_crawl4ai() -> CheckResult:
    """Seam 3: ``crawl4ai-doctor`` returns 0 AND a real headless Chromium launch.

    Both must succeed. Uses an inline ``raw://`` document so no external network is
    contacted. Wraps every failure as ``ok=False``; never raises.
    """
    try:
        details: list[str] = []

        # (a) crawl4ai-doctor subprocess — locate the console script installed in
        # this venv, falling back to the Scripts/bin dir next to the interpreter.
        doctor_exe = shutil.which("crawl4ai-doctor")
        if doctor_exe is None:
            bindir = os.path.dirname(sys.executable)
            for cand in ("crawl4ai-doctor.exe", "crawl4ai-doctor"):
                path = os.path.join(bindir, cand)
                if os.path.exists(path):
                    doctor_exe = path
                    break

        if doctor_exe is None:
            return CheckResult(
                "crawl4ai",
                False,
                "crawl4ai-doctor console script not found on PATH or in the venv "
                "Scripts dir (run `uv run crawl4ai-setup`).",
            )

        proc = subprocess.run(
            [doctor_exe],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        doctor_ok = proc.returncode == 0
        details.append(f"crawl4ai-doctor rc={proc.returncode}")

        # (b) real headless Chromium launch over inline raw:// HTML
        launch_ok, launch_err = asyncio.run(_launch_chromium_once())
        details.append(
            f"chromium_launch={'ok' if launch_ok else 'FAILED'}"
            + (f" ({launch_err})" if launch_err else "")
        )

        return CheckResult("crawl4ai", doctor_ok and launch_ok, "; ".join(details))
    except Exception as exc:
        return CheckResult("crawl4ai", False, f"crawl4ai check failed: {exc!r}")


def run_all() -> list[CheckResult]:
    """Run all three seam checks and return their results (order: runtime, ollama, crawl4ai)."""
    return [check_runtime(), check_ollama(), check_crawl4ai()]


def main() -> int:
    """Print one GREEN/RED line per seam and return 0 iff all seams pass, else 1."""
    results = run_all()
    all_ok = True
    for r in results:
        mark = "GREEN" if r.ok else "RED"
        print(f"[{mark}] {r.name}: {r.detail}")
        all_ok = all_ok and r.ok
    print(
        "doctor: all three seams GREEN — runtime ready."
        if all_ok
        else "doctor: RED — at least one seam failed (see above)."
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
