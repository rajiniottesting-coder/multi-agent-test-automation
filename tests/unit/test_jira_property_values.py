"""A Jira issue property reads back as the plain JSON that was stored.

4 Nov 2026: Agent 5's second report on PRJ-283 crashed - "'PropertyHolder'
object has no attribute 'get'" - reading its last-report fingerprint. The jira
SDK parses an object value into a PropertyHolder (attributes, no .get()), and
JiraClient.get_property returned that. Every reader that treats the value as
the dict it stored was affected: Agent 5's repeat check crashed, the flaky-test
names and Agent 0's outcome check fell back silently. Now the value is taken
from the response's raw JSON. The real SDK class is used, so an SDK change to
either shape fails here.
"""
from types import SimpleNamespace as NS

import pytest
from jira.resources import IssueProperty

from integrations.jira_client import JiraClient


def _client(prop=None, error=None):
    c = JiraClient.__new__(JiraClient)

    def issue_property(issue, key):
        if error:
            raise error
        return prop
    c._client = NS(issue_property=issue_property)
    return c


@pytest.mark.parametrize("value", [{"fp": "abc", "ref": "https://x/1", "run": "r"},
                                   [1, 2], "text", 3, True, {"nested": {"a": [1]}}])
def test_the_value_is_the_json_that_was_stored(value):
    prop = IssueProperty({"server": "https://jira.example"}, None,
                         raw={"key": "agent5.report", "value": value})
    got = _client(prop).get_property("S-1", "agent5.report")
    assert got == value and type(got) is type(value)
    if isinstance(value, dict):
        assert got.get("fp", "x") == value.get("fp", "x"), "readers call .get()"


def test_the_sdk_still_wraps_an_object_value():
    """Why the raw JSON is read: if this ever fails, the SDK stopped wrapping."""
    prop = IssueProperty({"server": "https://jira.example"}, None,
                         raw={"key": "k", "value": {"fp": "abc"}})
    assert not isinstance(prop.value, dict)


def test_a_missing_property_is_none_and_other_errors_raise():
    assert _client(error=type("E", (Exception,), {"status_code": 404})()).get_property("S-1", "k") is None
    with pytest.raises(RuntimeError):
        _client(error=RuntimeError("401")).get_property("S-1", "k")


def test_agent5_reads_its_last_report_from_a_real_property(monkeypatch):
    from agents import agent5_reporter as a5
    prop = IssueProperty({"server": "https://jira.example"}, None,
                         raw={"key": a5.REPORT_PROPERTY, "value": {"fp": "abc", "ref": "u"}})
    client = _client(prop)
    monkeypatch.setattr("core.usage_ledger.mode", lambda tracker: "properties")
    last = a5._last_report(client, "S-1")
    assert last.get("fp") == "abc"


# ── get_property says it returns plain JSON ───────────────────────────────────

def test_get_property_says_it_returns_plain_json():
    import inspect
    from integrations.jira_client import JiraClient
    ann = inspect.signature(JiraClient.get_property).return_annotation
    assert "dict" in str(ann) and "None" in str(ann)
