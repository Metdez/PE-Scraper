from __future__ import annotations

import json

from pescraper.models import FirmRecord


def test_evaluate_cases_reports_field_and_page_selection_accuracy() -> None:
    from pescraper.benchmark import BenchmarkCase, evaluate_cases

    cases = [
        BenchmarkCase(
            name="acme",
            expected=FirmRecord(
                firm_name="Acme Capital",
                website="https://acme.example",
                ebitda_min_musd=5,
                deal_types="Buyout",
            ),
            actual=FirmRecord(
                firm_name="Acme Capital",
                website="https://acme.example",
                ebitda_min_musd=5.0,
                deal_types="Growth",
            ),
            expected_pages=["https://acme.example/criteria"],
            selected_pages=["https://acme.example/criteria", "https://acme.example/about"],
        )
    ]

    report = evaluate_cases(cases)

    assert report.field_scores["ebitda_min_musd"].matches == 1
    assert report.field_scores["deal_types"].matches == 0
    assert report.extraction_accuracy == 0.5
    assert report.page_selection_accuracy == 1.0


def test_load_cases_reads_jsonl_fixture(tmp_path) -> None:
    from pescraper.benchmark import load_cases

    fixture = tmp_path / "benchmark.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "name": "blocked-firm",
                "category": "blocked",
                "expected": {"firm_name": "Blocked Capital", "website": "https://blocked.example"},
                "actual": {"firm_name": "Blocked Capital", "website": "https://blocked.example"},
                "expected_pages": [],
                "selected_pages": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(fixture)

    assert len(cases) == 1
    assert cases[0].category == "blocked"
    assert cases[0].expected.firm_name == "Blocked Capital"
