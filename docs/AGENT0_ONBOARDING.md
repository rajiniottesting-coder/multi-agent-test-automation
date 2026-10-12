# Attaching Agent 0 to another application

Agent 0 (the impact analyst) can run against an application whose tests are not
in this repository. How Agent 0 works — modes, triggers, review, hand-over,
context update and reconcile — is in [GUIDE.md → Change stories — Agent 0](./GUIDE.md#change-stories--agent-0). This page is the checklist. The readiness check does most of
the verification:

```bash
python -m scripts.onboarding_check --root /path/to/app-repo \
    --inventory qa/inventory.json
```

The tracker and repository-host adapters default to `tracker.type` and
`repo_host.type` in the application's own `config/config.yaml`, falling back to
this deployment's configured types. Pass `--tracker` / `--repo-host` to check a
different adapter.

It reads the project and changes nothing. Exit 1 means a layer cannot run; add
`--strict` to fail on warnings too. Every result carries the action it implies.

## What carries over unchanged

Agent 0's layers 2 (semantic candidates) and 3 (LLM adjudication), its approval
flow, hand-over, reconcile and outcome recording do not depend on the
application. Nothing app-specific lives in framework code; the golden-rule guard
(`tests/unit/test_committed_tree_resolves.py`) fails the build if it does.

## Steps

### 1. Tracker adapter

Agent 0 talks to the tracker through a protocol of operations
(`integrations/tracker.py`, `Tracker`). For a tracker other than Jira, write a
class that provides every operation with the Protocol's exact signatures, then:

```python
from integrations.tracker import register_adapter
register_adapter("xray", XrayTracker)     # the name you pass as --tracker
```

The readiness check reports `FAIL` with the missing operations if the class is
incomplete, and `WARN` if it cannot be constructed without credentials.

### 2. Repository-host adapter

The same pattern for the code host (`integrations/repo_host.py`, `RepoHost`,
register with `register_adapter`). Jira and GitHub are built in.

### 3. Layer 1 graph builder for the suite's language

Layer 1 follows the code: scenario, step definition, page method, element, page
and Component. It is the only part that reads the suite's source, so it is the
only part that differs per language. The builder registered for this repository
is `python-pytest-bdd`.

A builder has the signature `builder(project_root, inventory_file=None) -> ImpactGraph`
and returns the same graph shape (scenarios, step definitions, gaps). Register it:

```python
from core.impact_graph import register_graph_builder
register_graph_builder("java-selenium", build_java_graph)
```

then pass `--language java-selenium`. Without a builder the check fails and
Agent 0 runs layers 2 and 3 only, reporting layer 1 as absent.

Unresolved links are recorded as gaps. Agent 0 treats a gap as *unknown*, never
as *not impacted*, so the gap count is worth reading before trusting a result.

### 4. Layout and inventory

The builder reads three directories, relative to the project root:

- `features/` - the feature files
- `tests/step_defs/` - the step definitions (`conftest.py` applies to all)
- `pages/` - the page objects

A suite that keeps these elsewhere is invisible to layer 1 until they move or
the builder is taught the new layout. The check reports each missing directory.

The inventory is the element catalogue the page objects select from. Name it
with `--inventory` (relative to `--root`), or in `config/config.yaml` under
`app_under_test.inventory_file`. Every page should carry `Components`: layer 2
uses them to pre-filter candidates, and a page without them makes layer 2
consider the whole suite.

Build it with the existing tools when the application has none:
`scripts/generate_inventory.py`, then curate.

### 5. Traceability markers

Each scenario needs a `# JIRA: <key> (hash: <h>)` marker. A scenario without one
can be found by the analysis but has no test case to revise and no owner to
trace. Legacy suites usually have none.

```bash
python scripts/backfill_markers.py propose --story <STORY-KEY>
# review reports/marker_backfill.json: set "apply": true on the rows you accept
python scripts/backfill_markers.py apply reports/marker_backfill.json --open-pr
```

Nothing is written without that confirmation. Use `--story` whenever the project
holds test cases from other applications, since titles alike across apps pair
convincingly and wrongly.

Until markers exist, Agent 0 degrades to report-only for those scenarios.

## Done

The onboarding is done when the readiness check passes with no `FAIL`, the
backfill has run and its proposals are applied, and one full dry run of Agent 0
on a real change story has produced a reviewable list. Shadow mode
(predictions with no hand-over) comes before hand-over is enabled for a team.

## Known limits

- The builder's directory layout is fixed (see step 4). Changing it means
  changing `core/impact_graph.py`; the check reports the gap rather than hiding it.
- Adapter conformance is verified by constructing the adapter. Credentials are
  needed for that, so without them the check reports `WARN` and the Protocol
  conformance test must be run with the suite's secrets set.
- The backfill's `propose` step reads the tracker, so it cannot run offline.
