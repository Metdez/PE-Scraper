"""Repeatable extraction and page-selection accuracy benchmark."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pescraper.models import FirmRecord


IGNORED_FIELDS = {
    "firm_name",
    "website",
    "confidence",
    "needs_review",
    "last_checked",
    "status",
}


@dataclass(slots=True)
class BenchmarkCase:
    name: str
    expected: FirmRecord
    actual: FirmRecord
    expected_pages: list[str] = field(default_factory=list)
    selected_pages: list[str] = field(default_factory=list)
    category: str = "standard"


@dataclass(slots=True)
class FieldScore:
    matches: int = 0
    compared: int = 0

    @property
    def accuracy(self) -> float:
        return self.matches / self.compared if self.compared else 0.0


@dataclass(slots=True)
class BenchmarkReport:
    field_scores: dict[str, FieldScore]
    page_matches: int
    page_cases: int

    @property
    def extraction_accuracy(self) -> float:
        matches = sum(score.matches for score in self.field_scores.values())
        compared = sum(score.compared for score in self.field_scores.values())
        return matches / compared if compared else 0.0

    @property
    def page_selection_accuracy(self) -> float:
        return self.page_matches / self.page_cases if self.page_cases else 0.0

    def as_dict(self) -> dict:
        return {
            "extraction_accuracy": self.extraction_accuracy,
            "page_selection_accuracy": self.page_selection_accuracy,
            "fields": {
                name: {
                    "matches": score.matches,
                    "compared": score.compared,
                    "accuracy": score.accuracy,
                }
                for name, score in sorted(self.field_scores.items())
            },
        }


def _matches(expected: object, actual: object) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= 1e-6
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().casefold() == actual.strip().casefold()
    return expected == actual


def evaluate_cases(cases: list[BenchmarkCase]) -> BenchmarkReport:
    scores: dict[str, FieldScore] = {}
    page_matches = 0
    page_cases = 0

    for case in cases:
        expected = case.expected.model_dump()
        actual = case.actual.model_dump()
        for name, expected_value in expected.items():
            if name in IGNORED_FIELDS or expected_value is None:
                continue
            score = scores.setdefault(name, FieldScore())
            score.compared += 1
            score.matches += int(_matches(expected_value, actual.get(name)))

        page_cases += 1
        expected_pages = set(case.expected_pages)
        selected_pages = set(case.selected_pages)
        page_matches += int(expected_pages.issubset(selected_pages))

    return BenchmarkReport(scores, page_matches, page_cases)


def load_cases(path: str | Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            cases.append(
                BenchmarkCase(
                    name=raw["name"],
                    category=raw.get("category", "standard"),
                    expected=FirmRecord(**raw["expected"]),
                    actual=FirmRecord(**raw["actual"]),
                    expected_pages=raw.get("expected_pages", []),
                    selected_pages=raw.get("selected_pages", []),
                )
            )
    return cases


__all__ = [
    "BenchmarkCase",
    "BenchmarkReport",
    "FieldScore",
    "evaluate_cases",
    "load_cases",
]
