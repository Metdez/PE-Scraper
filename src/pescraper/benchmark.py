"""Accuracy benchmark harness — Phase 3's v1 acceptance gate.

Runs real qwen3:4b extraction (no mocking — this measures actual model
accuracy) against a hand-verified golden set and reports per-field match rate.
Numeric fields match within a small tolerance; string fields match
case-insensitively. Re-running after any prompt/model change shows whether
accuracy moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pescraper import extract

NUMERIC_TOLERANCE = 0.5


@dataclass
class FieldResult:
    firm_name: str
    field_name: str
    expected: object
    actual: object
    correct: bool


@dataclass
class BenchmarkReport:
    results: list[FieldResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def match_rate(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def per_field_match_rate(self) -> dict[str, float]:
        by_field: dict[str, list[FieldResult]] = {}
        for r in self.results:
            by_field.setdefault(r.field_name, []).append(r)
        return {
            f: sum(1 for r in rs if r.correct) / len(rs) for f, rs in by_field.items()
        }

    def mismatches(self) -> list[FieldResult]:
        return [r for r in self.results if not r.correct]


def _values_match(expected: object, actual: object) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= NUMERIC_TOLERANCE
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() in actual.strip().lower() or actual.strip().lower() in expected.strip().lower()
    return expected == actual


def run_benchmark(golden_set: list[dict]) -> BenchmarkReport:
    """Run extraction against each golden entry's frozen pages, score fields."""
    report = BenchmarkReport()

    for entry in golden_set:
        firm_name = entry["firm_name"]
        pages = entry["pages"]
        expected_fields = entry["expected"]

        financial, categorical = extract.extract(pages, firm_name)
        actual = {**financial.model_dump(), **categorical.model_dump()}

        for field_name, expected_value in expected_fields.items():
            actual_value = actual.get(field_name)
            report.results.append(
                FieldResult(
                    firm_name=firm_name,
                    field_name=field_name,
                    expected=expected_value,
                    actual=actual_value,
                    correct=_values_match(expected_value, actual_value),
                )
            )

    return report


async def check_page_selection(golden_set: list[dict]) -> dict[str, bool]:
    """Live check: does crawl.select_pages(website) surface the golden page?

    Separate from field-accuracy scoring (ROADMAP success criterion 2 — page-
    selection accuracy reported separately from extraction accuracy). Touches
    real network/crawl4ai; not part of the fast offline field-accuracy loop.
    """
    from pescraper import crawl

    results: dict[str, bool] = {}
    for entry in golden_set:
        pages = await crawl.select_pages(entry["website"])
        results[entry["firm_name"]] = entry["golden_page_url"] in pages
    return results


def format_report(report: BenchmarkReport) -> str:
    lines = [f"Overall match rate: {report.correct}/{report.total} ({report.match_rate:.0%})", ""]
    lines.append("Per-field:")
    for f, rate in sorted(report.per_field_match_rate().items()):
        lines.append(f"  {f}: {rate:.0%}")
    mismatches = report.mismatches()
    if mismatches:
        lines.append("")
        lines.append("Mismatches:")
        for m in mismatches:
            lines.append(f"  {m.firm_name}.{m.field_name}: expected={m.expected!r} actual={m.actual!r}")
    return "\n".join(lines)


__all__ = [
    "NUMERIC_TOLERANCE",
    "FieldResult",
    "BenchmarkReport",
    "run_benchmark",
    "check_page_selection",
    "format_report",
]
