"""The Allure report is the application tests' (13 Nov 2026).

Every Agent 4 run wrote its ~4,400 unit tests into reports/allure-results
beside the application tests: the published Allure report listed them all,
and Allure's history file - which keeps every test it ever saw - reached
11 MB on the results store branch. Now a unit-test session writes no Allure
results, and the history keeps only the tests the run reported.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.allure_meta import prune_history
from core.local_outputs import keep_unit_tests_out_of_allure, unit_only

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("args,expected", [
    (["tests/unit"], True),
    (["tests/unit/test_x.py::test_a", "tests/unit/sub"], True),
    (["tests/step_defs"], False),
    (["tests/unit", "tests/step_defs/test_y.py"], False),
    (["tests"], False),
    ([], False),                                  # the whole suite: app tests included
])
def test_unit_only(tmp_path, args, expected):
    assert unit_only(args, tmp_path) is expected


def test_relative_paths_are_read_from_where_pytest_started(tmp_path):
    assert unit_only(["unit"], tmp_path, base=tmp_path / "tests") is True
    assert unit_only(["step_defs"], tmp_path, base=tmp_path / "tests") is False


def _config(args, alluredir="reports/allure-results"):
    return SimpleNamespace(args=args, option=SimpleNamespace(allure_report_dir=alluredir),
                           invocation_params=SimpleNamespace(dir=ROOT))


def test_a_unit_session_writes_no_allure_results():
    config = _config(["tests/unit/"])
    assert keep_unit_tests_out_of_allure(config, ROOT) is True
    assert config.option.allure_report_dir is None


@pytest.mark.parametrize("args", [["tests/step_defs/"], []])
def test_an_app_session_keeps_allure(args):
    config = _config(args)
    assert keep_unit_tests_out_of_allure(config, ROOT) is False
    assert config.option.allure_report_dir == "reports/allure-results"


def test_it_runs_before_the_allure_plugin():
    src = (ROOT / "tests/conftest.py").read_text()
    i = src.index("def pytest_configure(config):")
    assert "@pytest.hookimpl(tryfirst=True)" in src[i - 60:i]
    assert "keep_unit_tests_out_of_allure(" in src[i:i + 3000]


def _results(tmp_path, history: dict, run_ids):
    res = tmp_path / "allure-results"
    (res / "history").mkdir(parents=True)
    (res / "history" / "history.json").write_text(json.dumps(history))
    (res / "history" / "history-trend.json").write_text("[1, 2]")
    for i, hid in enumerate(run_ids):
        (res / f"r{i}-result.json").write_text(json.dumps({"historyId": hid}))
    return res


def test_history_keeps_only_the_tests_this_run_reported(tmp_path):
    res = _results(tmp_path, {"app1": {"items": [1]}, "app2": {"items": [2]},
                              "unit1": {"items": [3]}, "gone": {"items": [4]}},
                   ["app1", "app2", "new"])
    assert prune_history(res) == (2, 2)
    assert set(json.loads((res / "history" / "history.json").read_text())) == {"app1", "app2"}
    assert (res / "history" / "history-trend.json").read_text() == "[1, 2]"   # left alone


def test_no_results_never_empty_the_history(tmp_path):
    res = _results(tmp_path, {"a": {}}, [])
    assert prune_history(res) == (0, 0)
    assert json.loads((res / "history" / "history.json").read_text()) == {"a": {}}
    assert prune_history(tmp_path / "missing") == (0, 0)


def test_agent4_prunes_before_generating():
    wf = (ROOT / ".github/workflows/agent4_runner.yml").read_text()
    step = wf[wf.index("- name: Generate the Allure report"):wf.index("- name: Upload test report")]
    assert step.index("prune_allure_history reports/allure-results") < step.index("allure\" generate")


def test_the_cli_prints_what_it_kept(tmp_path, capsys):
    from scripts.prune_allure_history import main
    res = _results(tmp_path, {"a": {}, "b": {}}, ["a"])
    assert main([str(res)]) == 0
    assert "1 test(s) kept, 1 no longer reported dropped" in capsys.readouterr().out
    assert main([]) == 0
