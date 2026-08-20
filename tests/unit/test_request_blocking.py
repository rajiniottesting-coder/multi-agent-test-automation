"""Third-party hosts listed in config.yaml must be refused at the browser.

WHAT HAPPENED
    An ad network on the site under test served a full-screen interstitial
    that CONSUMED the first navigation after a page load. The click reported
    success, the address gained a fragment, the browser never moved, and the
    next action spent its entire thirty-second timeout waiting for an element
    on a page nobody had reached.

    It appeared on some runs and not others. The same code passed and failed
    with nothing changed, which is the worst property a test suite can have -
    a green run stops meaning anything.

    Three separate framework defences were written against it: a diagnosis
    that names it, a dismissal at the readiness probe, a dismissal at the
    action chokepoint, and a re-issued navigation. Every one of them is a
    recovery AFTER the ad has already done its damage.

    Not loading the ad removes the failure mode rather than handling it.

WHY THE LIST LIVES IN config.yaml
    WHICH hosts to refuse is a property of the site under test, so it belongs
    with the other app configuration. The framework reads a list of suffixes
    and knows nothing else - no network is named anywhere in the code, and
    pointing the suite at a different application changes only the list.
"""
import pytest

from tests.conftest import should_block_request

_BLOCKED = ["adnetwork.example", "tracker.example.net"]


# ─────────────────────────────────────────────────────────────────────────
# Suffix matching, so one entry covers a whole network
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://adnetwork.example/tag.js",
    "https://ads.adnetwork.example/pagead/ads?client=x",
    "https://deep.nested.adnetwork.example/frame.html",
    "http://tracker.example.net/pixel.gif",
])
def test_a_listed_host_and_its_subdomains_are_refused(url):
    assert should_block_request(url, _BLOCKED) is True


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# A blocklist that over-matches would refuse the application itself, and the
# whole suite would fail in a way that looks like the site is down.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://app.example/some/path",
    "https://www.app.example/cdn/main.css",
    "https://api.app.example/v1/resource",
])
def test_the_application_is_never_refused(url):
    assert should_block_request(url, _BLOCKED) is False


def test_a_suffix_cannot_match_a_different_domain():
    """`notadnetwork.example` ends with the listed string but is not it.
    Matching on a bare `endswith` would refuse an unrelated site."""
    assert should_block_request("https://notadnetwork.example/x", _BLOCKED) is False


def test_an_empty_list_blocks_nothing():
    """The escape hatch. Someone debugging a rendering problem needs the real
    page, ads and all."""
    assert should_block_request("https://adnetwork.example/tag.js", []) is False
    assert should_block_request("https://adnetwork.example/tag.js", None) is False


def test_a_malformed_url_is_allowed_through():
    """Blocking is an optimisation, not a security control. It must never be
    able to fail a test by throwing."""
    assert should_block_request("not-a-url", _BLOCKED) is False
    assert should_block_request("", _BLOCKED) is False


def test_matching_ignores_case():
    assert should_block_request("https://ADS.AdNetwork.Example/x", _BLOCKED) is True


# ─────────────────────────────────────────────────────────────────────────
# The list must be wired up, not merely present
#
# A configuration key nothing reads is worse than no key: it looks like the
# problem is handled.
# ─────────────────────────────────────────────────────────────────────────

def test_the_page_fixture_actually_installs_the_route():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "conftest.py").read_text(
        encoding="utf-8")
    body = " ".join(source.split())

    assert 'browser_config.get("block_hosts")' in body, \
        "nothing reads browser.block_hosts from config.yaml"
    assert "context.route(" in body, \
        "the blocklist is read but never installed on the browser context"
    assert "should_block_request(" in body, \
        "the route handler must use the tested predicate, not its own copy"


def test_the_shipped_config_declares_the_key():
    """Not WHICH hosts - that is this application's business and may change -
    only that the key exists, so the mechanism is not silently inert."""
    import yaml
    from config.paths import CONFIG_YAML

    with open(CONFIG_YAML, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    assert "block_hosts" in config["browser"], (
        "config.yaml has no browser.block_hosts key. The framework reads it; "
        "without it every third-party request loads and an interstitial can "
        "consume a navigation again."
    )