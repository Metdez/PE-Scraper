"""Offline contract tests for the three-seam doctor.

Live Ollama/Chromium are not assertable inside an automated gate, so these tests
lock the *harness structure* and the *exit-code contract* via monkeypatching rather
than live services (PITFALLS "Looks Done But Isn't": the smoke test must actually go
RED when a seam is down, not merely pass when everything is up). They run fast and
fully offline.
"""

from __future__ import annotations

from pescraper import doctor
from pescraper.doctor import CheckResult, HealthPing


def _ok(name: str) -> CheckResult:
    return CheckResult(name, True, "stub-ok")


def _fail(name: str) -> CheckResult:
    return CheckResult(name, False, "stub-fail")


def test_public_callables_exist() -> None:
    for attr in ("check_runtime", "check_ollama", "check_crawl4ai", "run_all", "main"):
        assert callable(getattr(doctor, attr)), f"doctor.{attr} must be callable"


def test_run_all_returns_three_results(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "check_runtime", lambda: _ok("runtime"))
    monkeypatch.setattr(doctor, "check_ollama", lambda: _ok("ollama"))
    monkeypatch.setattr(doctor, "check_crawl4ai", lambda: _ok("crawl4ai"))

    results = doctor.run_all()
    assert len(results) == 3
    assert all(isinstance(r, CheckResult) for r in results)
    assert [r.name for r in results] == ["runtime", "ollama", "crawl4ai"]


def test_main_returns_zero_when_all_pass(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "check_runtime", lambda: _ok("runtime"))
    monkeypatch.setattr(doctor, "check_ollama", lambda: _ok("ollama"))
    monkeypatch.setattr(doctor, "check_crawl4ai", lambda: _ok("crawl4ai"))

    assert doctor.main() == 0


def test_main_returns_nonzero_on_any_single_failure(monkeypatch) -> None:
    # Each seam failing in isolation must flip the aggregate to non-zero.
    seams = ("check_runtime", "check_ollama", "check_crawl4ai")
    for failing in seams:
        for name in seams:
            result = _fail(name) if name == failing else _ok(name)
            monkeypatch.setattr(doctor, name, (lambda r: (lambda: r))(result))
        rc = doctor.main()
        assert rc != 0, f"main() must be non-zero when {failing} fails (got {rc})"


def test_check_ollama_wraps_failure_as_not_ok(monkeypatch) -> None:
    # A raising dependency must be surfaced as ok=False, never propagated.
    import ollama

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated ollama outage")

    monkeypatch.setattr(ollama, "chat", _boom)

    result = doctor.check_ollama()  # must NOT raise
    assert isinstance(result, CheckResult)
    assert result.ok is False
    assert result.name == "ollama"


def test_check_crawl4ai_wraps_failure_as_not_ok(monkeypatch) -> None:
    # Force the console-script lookup to fail; the check must degrade to ok=False.
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor.os.path, "exists", lambda _path: False)

    result = doctor.check_crawl4ai()  # must NOT raise
    assert isinstance(result, CheckResult)
    assert result.ok is False
    assert result.name == "crawl4ai"


def test_healthping_round_trip_shape() -> None:
    # The structured-output contract shape: schema out, JSON in, validated model.
    schema = HealthPing.model_json_schema()
    assert schema["properties"].keys() >= {"ok", "model"}
    ping = HealthPing.model_validate_json('{"ok": true, "model": "qwen3:4b"}')
    assert ping.ok is True
    assert ping.model == "qwen3:4b"
