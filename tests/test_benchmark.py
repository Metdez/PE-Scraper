"""Phase 3 accuracy benchmark — runs real qwen3:4b extraction against the
hand-verified golden set (tests/benchmark/golden_set.py). Requires Ollama with
qwen3:4b running; slower than the rest of the suite (real model calls).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from benchmark.golden_set import GOLDEN_SET  # noqa: E402

from pescraper.benchmark import format_report, run_benchmark  # noqa: E402


def test_benchmark_runs_and_reports_reasonable_accuracy() -> None:
    report = run_benchmark(GOLDEN_SET)
    print("\n" + format_report(report))

    assert report.total > 0
    # Loose floor — this is a regression signal, not a strict gate at n=3.
    assert report.match_rate >= 0.5, format_report(report)
