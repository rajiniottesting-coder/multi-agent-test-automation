"""Tests for the Stage-2 prompt cache split.

The saving only exists while the cached span is byte-identical across calls.
These tests protect that invariant, and protect the fallbacks that keep a run
working when it does not hold.
"""
from agents.agent2_coder import (
    _CACHE_MARKER,
    _SUBSTITUTED_PLACEHOLDERS,
    _split_prompt_for_cache,
)
from core.llm_client import _system_message, _prompt_cache_enabled
from config.paths import PROMPTS_DIR


# ── the real prompt file ─────────────────────────────────────────────────

def _template() -> str:
    return (PROMPTS_DIR / "agent2_coder_generate.md").read_text(encoding="utf-8")


def test_real_template_declares_a_cache_marker():
    assert _CACHE_MARKER in _template()


def test_no_substituted_placeholder_below_the_marker():
    """The invariant the whole feature rests on.

    A substituted value below the marker changes the cached prefix on every
    call: each call pays the cache-write premium and no read ever hits, which
    is strictly worse than not caching at all.
    """
    _, static_part = _template().split(_CACHE_MARKER, 1)
    leaked = [p for p in _SUBSTITUTED_PLACEHOLDERS if p in static_part]
    assert not leaked, f"substituted placeholders below the cache marker: {leaked}"


def test_static_part_is_the_bulk_of_the_template():
    """Guards against someone moving the marker down until caching is pointless."""
    variable_part, static_part = _split_prompt_for_cache(_template())
    assert static_part, "marker present but split produced no static part"
    share = len(static_part) / (len(variable_part) + len(static_part))
    assert share > 0.60, f"only {share:.0%} of the template is cacheable"


def test_split_is_lossless():
    """No prompt text may be dropped by the split."""
    template = _template()
    variable_part, static_part = _split_prompt_for_cache(template)
    assert len(variable_part) + len(_CACHE_MARKER) + len(static_part) == len(template)


# ── fallbacks: caching must never break a run ────────────────────────────

def test_missing_marker_degrades_to_uncached():
    template = "no marker here {app_name} at all"
    variable_part, static_part = _split_prompt_for_cache(template)
    assert variable_part == template
    assert static_part == ""


def test_leaked_placeholder_disables_caching():
    """A leak must disable caching, not raise and not cache the wrong thing."""
    bad = f"context\n{_CACHE_MARKER}\nrules mentioning {{file_path}} wrongly"
    variable_part, static_part = _split_prompt_for_cache(bad)
    assert variable_part == bad
    assert static_part == ""


def test_every_substituted_placeholder_is_declared():
    """_SUBSTITUTED_PLACEHOLDERS must cover what the code actually replaces.

    A placeholder added to generate_file_content but not declared here would
    slip past the leak check silently.
    """
    import inspect
    import re
    from agents import agent2_coder
    src = inspect.getsource(agent2_coder.generate_file_content)
    replaced = set(re.findall(r'\.replace\("(\{[a-z_]+\})"', src))
    declared = set(_SUBSTITUTED_PLACEHOLDERS)
    assert replaced <= declared, f"undeclared placeholders: {replaced - declared}"


# ── the message the provider actually receives ───────────────────────────

def test_cache_prefix_off_gives_a_plain_string():
    msg = _system_message("rules", cache_prefix=False)
    assert msg.content == "rules"


def test_cache_prefix_on_gives_a_breakpoint_block():
    msg = _system_message("rules", cache_prefix=True)
    assert isinstance(msg.content, list)
    block = msg.content[0]
    assert block["type"] == "text"
    assert block["text"] == "rules"
    assert block["cache_control"] == {"type": "ephemeral"}


def test_empty_system_prompt_never_gets_a_breakpoint():
    """An empty cached span is meaningless and some providers reject it."""
    assert _system_message("", cache_prefix=True).content == ""
    assert _system_message("   ", cache_prefix=True).content == "   "


def test_env_flag_disables_caching(monkeypatch):
    monkeypatch.setenv("LLM_PROMPT_CACHE", "0")
    assert _prompt_cache_enabled() is False
    assert _system_message("rules", cache_prefix=True).content == "rules"


def test_caching_is_on_by_default(monkeypatch):
    monkeypatch.delenv("LLM_PROMPT_CACHE", raising=False)
    assert _prompt_cache_enabled() is True