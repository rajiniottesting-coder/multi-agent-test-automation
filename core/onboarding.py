"""Onboarding readiness for an application outside this repository (design E2).

Agent 0 can be attached to a running suite once five things hold. Each is a
check here, and each miss says what to do about it:

  1. tracker adapter    the configured tracker is registered and complete
  2. repo-host adapter  the configured repository host is registered and complete
  3. graph builder      a layer 1 builder exists for the suite's language
  4. layout + inventory the directories the builder reads exist; the inventory
                        loads; pages carry Components (layer 2 pre-filter)
  5. markers            scenarios carry `# JIRA:` markers; unmarked ones need
                        the backfill (B1) before Agent 0 can revise them

A FAIL means Agent 0 cannot run that layer; a WARN means it runs but loses
accuracy. Read-only: nothing is written, and no tracker or host write is made.
Adapters are constructed to inspect their members, which needs their
credentials; without them the check says so instead of guessing.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from core.impact_graph import (
    _load_inventory,
    graph_builder_for,
    registered_languages,
)

OK, WARN, FAIL = "ok", "warn", "fail"

# Directories the layer 1 builder reads. Relative to the project root.
REQUIRED_LAYOUT = ("features", "tests/step_defs", "pages")


@dataclass(frozen=True)
class Check:
    name: str
    status: str                  # OK | WARN | FAIL
    detail: str
    action: str = ""


# ─────────────────────────────────────────────────────────────
# Adapters (1, 2)
# ─────────────────────────────────────────────────────────────

def protocol_members(proto: type) -> set[str]:
    """The public operations a Protocol declares (methods and properties)."""
    return {name for name in vars(proto) if not name.startswith("_")}


def missing_members(proto: type, obj: object) -> list[str]:
    """Protocol operations `obj` does not provide, sorted. Empty when complete."""
    return sorted(name for name in protocol_members(proto) if not hasattr(obj, name))


def adapter_check(kind: str, name: str, proto: type, registered: list[str],
                  construct) -> Check:
    """Check one adapter: registered by name, constructible, and complete.

    `construct` is the registry's get function (get_tracker / get_repo_host).
    Credentials are needed to construct a real adapter; when construction fails
    the check is a WARN with the reason, not a FAIL, because the adapter may be
    fine and this environment simply lacks its secrets.
    """
    if name not in registered:
        return Check(f"{kind} adapter", FAIL,
                     f"no {kind} adapter registered as {name!r} "
                     f"(registered: {', '.join(registered) or 'none'})",
                     f"Write an adapter implementing the {kind} Protocol and "
                     f"register it under {name!r}.")
    try:
        obj = construct(name, fresh=True)
    except Exception as exc:                                  # noqa: BLE001
        return Check(f"{kind} adapter", WARN,
                     f"{name!r} is registered but could not be constructed "
                     f"here ({type(exc).__name__}); its members were not checked",
                     "Run the Protocol conformance test with this suite's "
                     "credentials set.")
    missing = missing_members(proto, obj)
    if missing:
        return Check(f"{kind} adapter", FAIL,
                     f"{name!r} lacks {len(missing)} Protocol operation(s): "
                     f"{', '.join(missing)}",
                     "Implement the missing operations with the Protocol's "
                     "exact signatures.")
    return Check(f"{kind} adapter", OK, f"{name!r} is registered and complete")


# ─────────────────────────────────────────────────────────────
# Graph, layout, inventory, markers (3, 4, 5)
# ─────────────────────────────────────────────────────────────

def layout_checks(root: Path) -> list[Check]:
    out = []
    for rel in REQUIRED_LAYOUT:
        if (root / rel).is_dir():
            out.append(Check(f"layout: {rel}/", OK, "present"))
        else:
            out.append(Check(f"layout: {rel}/", WARN,
                             "missing - the layer 1 builder reads only this layout, "
                             "so anything under a different name is invisible to Agent 0",
                             f"Move the suite's {rel.split('/')[-1]} files into {rel}/, "
                             f"or accept the gap."))
    return out


def inventory_checks(inventory: dict, inventory_file: str | None) -> list[Check]:
    where = inventory_file or "config/config.yaml app_under_test.inventory_file"
    if not inventory:
        return [Check("inventory", FAIL, f"no pages loaded from {where}",
                      "Generate the inventory (scripts/generate_inventory.py) and "
                      "point the config at it.")]
    out = [Check("inventory", OK, f"{len(inventory)} page(s) from {where}")]
    bare = sorted(name for name, spec in inventory.items()
                  if not (spec or {}).get("components"))
    if bare:
        out.append(Check("inventory: components", WARN,
                         f"{len(bare)} page(s) have no Components: {', '.join(bare)}. "
                         f"Layer 2 loses its pre-filter for them and must consider "
                         f"the whole suite",
                         "Add Components to these pages in the inventory."))
    else:
        out.append(Check("inventory: components", OK, "every page carries Components"))
    return out


def graph_checks(root: Path, language: str, inventory_file: str | None
                 ) -> tuple[list[Check], object]:
    """(checks, graph-or-None). The graph is returned so markers can be read from it."""
    builder = graph_builder_for(language)
    if builder is not None and inventory_file is None \
            and not (root / "config" / "config.yaml").is_file():
        return ([Check("graph builder", FAIL,
                       "no inventory named: pass --inventory, or add config/config.yaml "
                       "with app_under_test.inventory_file",
                       "Name the inventory the builder should read for this application.")], None)
    if builder is None:
        return ([Check("graph builder", FAIL,
                       f"no layer 1 builder for {language!r} "
                       f"(registered: {', '.join(registered_languages()) or 'none'}); "
                       f"Agent 0 can run layers 2 and 3 only, and reports layer 1 as absent",
                       "Write a builder with this signature and call "
                       "register_graph_builder(language, builder).")], None)
    try:
        graph = builder(root, inventory_file=inventory_file)
    except Exception as exc:                                  # noqa: BLE001
        return ([Check("graph builder", FAIL,
                       f"the {language!r} builder raised {type(exc).__name__}: {exc}",
                       "Fix the layout or the inventory it reads, then re-run.")], None)
    checks = [Check("graph builder", OK, f"{language!r} builder ran: "
                    f"{len(graph.scenarios)} scenario(s)")]
    if not graph.scenarios:
        checks.append(Check("graph: scenarios", WARN,
                            "no scenarios found under features/",
                            "Check the feature files are where the layout check expects."))
    if graph.gaps:
        kinds = Counter(g.kind for g in graph.gaps)
        summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        checks.append(Check("graph: gaps", WARN,
                            f"{len(graph.gaps)} unresolved link(s): {summary}. Agent 0 "
                            f"reads these as unknown, never as not impacted",
                            "Resolve them; `python -m core.impact_graph` lists each one."))
    return checks, graph


def marker_checks(graph) -> list[Check]:
    if graph is None or not graph.scenarios:
        return []
    unmarked = [s.title for s in graph.scenarios if not s.jira_key]
    if not unmarked:
        return [Check("markers", OK, f"all {len(graph.scenarios)} scenario(s) carry a marker")]
    return [Check("markers", WARN,
                  f"{len(unmarked)} of {len(graph.scenarios)} scenario(s) have no "
                  f"# JIRA: marker, e.g. {unmarked[0]!r}. Agent 0 can find them but "
                  f"cannot revise them or name an owner",
                  "Run `python scripts/backfill_markers.py propose`, review the "
                  "proposals, then `apply`.")]


# ─────────────────────────────────────────────────────────────
# All checks
# ─────────────────────────────────────────────────────────────

def configured_adapters(root: Path | str) -> tuple[str, str]:
    """(tracker type, repo-host type) for the application at `root`.

    The application's own config/config.yaml decides when it has one - an
    application on another tracker must be checked against THAT adapter.
    Without one, the types this deployment is configured for are used.
    """
    import yaml

    from integrations import repo_host as hosts
    from integrations import tracker as trackers

    tracker_type, host_type = trackers.configured_type(), hosts.configured_type()
    cfg_path = Path(root) / "config" / "config.yaml"
    if cfg_path.is_file():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        tracker_type = (data.get("tracker") or {}).get("type") or tracker_type
        host_type = (data.get("repo_host") or {}).get("type") or host_type
    return tracker_type, host_type


def run_checks(root: Path | str, *, language: str = "python-pytest-bdd",
               inventory_file: str | None = None,
               tracker: str | None = None, repo_host: str | None = None) -> list[Check]:
    """Every readiness check for the application at `root`, in build order.

    `tracker` / `repo_host` default to the application's configured types
    (configured_adapters), never to a fixed product name.
    """
    from integrations import repo_host as hosts
    from integrations import tracker as trackers
    from integrations.repo_host import RepoHost
    from integrations.tracker import Tracker

    root = Path(root)
    default_tracker, default_host = configured_adapters(root)
    tracker = tracker or default_tracker
    repo_host = repo_host or default_host
    checks = [
        adapter_check("tracker", tracker.strip().lower(), Tracker,
                      trackers.registered_types(), trackers.get_tracker),
        adapter_check("repo host", repo_host.strip().lower(), RepoHost,
                      hosts.registered_types(), hosts.get_repo_host),
    ]
    checks += layout_checks(root)
    try:
        inventory = _load_inventory(root, inventory_file)
    except OSError:                  # no config/config.yaml and no explicit inventory
        inventory = {}
    checks += inventory_checks(inventory, inventory_file)
    graph_part, graph = graph_checks(root, language, inventory_file)
    checks += graph_part
    checks += marker_checks(graph)
    return checks


def summarise(checks: list[Check]) -> dict[str, int]:
    counts = Counter(c.status for c in checks)
    return {OK: counts.get(OK, 0), WARN: counts.get(WARN, 0), FAIL: counts.get(FAIL, 0)}
