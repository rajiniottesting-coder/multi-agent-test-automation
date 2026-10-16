"""scripts/cleanup_artifacts.select(): which artifacts go. Pure, no network."""
from datetime import datetime, timedelta, timezone

from scripts.cleanup_artifacts import main, select

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)


def _a(name, days_old, run=1, expired=False, size=10):
    created = (NOW - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return {"id": hash(name) & 0xffff, "name": name, "created_at": created, "expired": expired,
            "size_in_bytes": size, "workflow_run": {"id": run}}


def test_only_artifacts_old_enough_are_chosen():
    arts = [_a("report-1", 5), _a("report-2", 2), _a("report-3", 1.9)]
    assert [a["name"] for a in select(arts, timedelta(days=2), "", set(), NOW)] == ["report-1", "report-2"]


def test_a_running_workflow_keeps_its_artifacts():
    arts = [_a("report-1", 5, run=7), _a("report-2", 5, run=8)]
    assert [a["name"] for a in select(arts, timedelta(days=2), "", {7}, NOW)] == ["report-2"]


def test_expired_artifacts_are_skipped_and_the_prefix_filters():
    arts = [_a("report-1", 5, expired=True), _a("report-2", 5), _a("other-3", 5)]
    assert [a["name"] for a in select(arts, timedelta(days=2), "report-", set(), NOW)] == ["report-2"]


def test_without_credentials_nothing_runs(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    assert main([]) == 2
    assert "must be set" in capsys.readouterr().err
