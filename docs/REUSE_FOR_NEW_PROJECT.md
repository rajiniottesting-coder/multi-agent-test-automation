# Reusing this framework for a different project

## Package layout

    agents/         the agents with Python code (0, 1, 2, 3, 5 - Agent 4
                    is the runner workflow) - the pipeline itself
    core/           shared infrastructure (LLM client, schemas, config,
                    usage ledger, board status, Agent 0's impact modules)
    integrations/   tool adapters + the Protocols they satisfy
                    (tracker/jira_client, repo_host/github_client)
    validators/     static checks on LLM-generated code

Porting to a new tool means adding ONE file under `integrations/` and changing
one line in `config/config.yaml`. Nothing in `agents/` changes.

> **Verification status (Oct 2026, main `e89fd4a`):** the full unit suite
> passes (~2,900 offline tests). Deployed: v17/v18 prompt hardening, orphan
> cleanup (`ai-update` AND `ai-regenerate`), dynamic sprint scoping
> (`sprint: "auto"` via JIRA_BOARD_ID), end-to-end LLM token & cost
> instrumentation, module-wise app context (`prompts/app_context/`), inventory
> JSON minification, duplicate step-definition guard, per-story ledger reset
> marker, light-model routing (`LLM_MODEL_LIGHT` for Agents 1 and 5), the
> 29-check validator gate, board automation, and **Agent 0** (impact analysis,
> Impact Review, hand-over, context update, reconcile). Framework code, agent
> prompts and unit-test logic carry no application-specific references.

This guide explains exactly what to change to point this framework at a different application (e.g., banking app, CMS, internal portal, anything with a web UI testable by Playwright + pytest-bdd).

The framework's design principle is: **agent code never changes between projects. Only config, prompts/app_context, app inventory, and reference files change.**

---

## What stays the same (NEVER touch when reusing)

These files contain zero project-specific knowledge. Reuse as-is:

### Agents (the orchestration brains)
- `agents/agent0_impact.py` — change story → affected tests, Impact Review (Agent 0)
- `agents/agent1_analyst.py` — Jira → Test Cases; `agents/agent1_impact.py` — revise approved tests
- `agents/agent2_coder.py` — Test Cases → Playwright code + PR; `agents/agent2_impact.py` — change-story splice
- `agents/agent3_reviewer.py` — PR review
- `agents/agent5_reporter.py` — results and cost to Jira; scores Agent 0
- `core/impact_*.py`, `core/context_update.py`, `core/json_block.py` — Agent 0's graph, analysis, review, hand-over, reconcile, context update
- `core/board_status.py`, `core/test_case_rules.py`, `core/failure_diagnosis.py`, `core/allure_*.py`
- `validators/orphan_cleanup.py` — dead-code detection (purely AST + Gherkin)
- `core/app_context.py` — loads app_under_test from config
- `integrations/tracker.py`, `integrations/repo_host.py` — the Protocols
- `integrations/github_client.py` — GitHub adapter
- `integrations/jira_client.py`, `integrations/jira_markup.py` — Jira adapter
- `core/llm_client.py` — provider-agnostic LLM wrapper (OpenAI-compatible) + token/cost tracking
- `core/usage_ledger.py` — per-story LLM cost ledger (Jira comments) — fully app-agnostic
- `validators/gherkin_analyzer.py` — Gherkin / step-def matching primitives (renamed from test_inventory.py)
- `validators/import_validator.py`, `validators/method_resolution_validator.py`, `validators/page_object_contract.py` — generic validators
- `core/schemas.py` — Pydantic models

### Agent prompts (templated, read app info from config at runtime)
- `prompts/agent0_seeds.md`, `prompts/agent0_adjudicate.md`, `prompts/agent0_wording.md`, `prompts/agent0_context_notes.md`
- `prompts/agent1_analyst.md`, `prompts/agent1_impact_aware.md`
- `prompts/agent2_coder_plan.md`
- `prompts/agent2_coder_generate.md` — all generation rules + BasePage helpers section
- `prompts/agent3_reviewer.md`
- `prompts/agent5_reporter.md`

### Universal page-object helpers
- `pages/base_page.py` — 85 generic Playwright-native helpers. Universal across projects.

### Unit tests (the test suite is project-agnostic)
- everything under `tests/unit/` (~2,900 offline tests) — synthetic fixtures (banking, CMS, a fake tracker and repo host), for example:
- `tests/unit/test_orphan_cleanup.py` — uses banking + CMS fixtures
- `tests/unit/test_pipeline_tool_agnostic.py` — the pipeline against an in-memory tracker
- `tests/unit/test_validators.py` — a fixture uses "Admin" as a generic role placeholder, not tied to any app

### Infrastructure
- `.github/workflows/*.yml` — all nine workflows
- `requirements.txt`
- `pytest.ini`
- `config/__init__.py`, `config/paths.py`

---

## What you MUST change (project-specific touch points)

There are **6 changes** for a new project, plus an optional seventh (Agent 0). They are ranked by criticality.

### Change 1 — `config/config.yaml` (MANDATORY)

Edit the `app_under_test` block. Example for a banking app:

```yaml
app_under_test:
  name: "AcmeBank"
  base_url: "https://bank.acme.example.com"
  inventory_file: "app_inventory/acmebank.json"

  reference_files:
    feature: "features/login.feature"
    step_def: "tests/step_defs/test_login.py"
    page_object: "pages/login_page.py"

  reserved_paths:
    - "features/login.feature"
    - "tests/step_defs/test_login.py"
    - "pages/login_page.py"

  extendable_paths:
    - "pages/account_page.py"
    - "pages/base_page.py"        # NEVER remove — universal helpers
```

ALSO update the legacy top-level `base_url:` alias:

```yaml
base_url: https://bank.acme.example.com   # was: the previous app's base URL
```

ALSO update or REMOVE the `test_users:` block - it holds the previous app's roles.

> **⚠️ Credentials — read before onboarding a REAL application.**
>
> A public demo app's credentials are often safe to commit - they are

> printed on the app's own login page and guard nothing. **Real application credentials are not.** Putting them in
> `config.yaml` or any file under `prompts/app_context/` means they are:
>
> 1. **Committed to Git permanently** — deleting the line later does not remove it
>    from history; that needs a history rewrite.
> 2. **Sent to the LLM on every Agent 1 call** — the `app_context/` modules are
>    injected into the prompt. Most client security policies prohibit exactly this.
>
> **The correct pattern — keep the knowledge, move the secret:**
>
> ```yaml
> # config.yaml — usernames and ROLE BEHAVIOUR are fine; passwords are not
> test_users:
>   admin:  { username: "admin_user",  password_env: "TEST_ADMIN_PASSWORD" }
>   viewer: { username: "viewer_user", password_env: "TEST_VIEWER_PASSWORD" }
>   locked: { username: "locked_user", password_env: "TEST_LOCKED_PASSWORD" }
> ```
>
> ```markdown
> <!-- prompts/app_context/login.md — behavioural knowledge, no secrets -->
> | Username | Password | Notes |
> |---|---|---|
> | `admin_user`  | *(env: TEST_ADMIN_PASSWORD)*  | Full permissions; can approve |
> | `locked_user` | *(env: TEST_LOCKED_PASSWORD)* | Receives lockout error on login |
> ```
>
> Step definitions read the real value at runtime: `os.getenv("TEST_ADMIN_PASSWORD")`.
> Passwords live in GitHub Secrets (CI) and `.env` (local, gitignored).
>
> Agent 1 still learns everything it needs — *that* a locked user exists and *what*
> happens when it logs in — which is what drives good test-case design. It never
> needs to know the password.
>
> **The same rule applies to any other secret** that might drift into these files:
> API keys, DB connection strings, tokens. Behavioural knowledge in the prompt;
> secrets in the environment.

The `agents:` section (label selection rules, completion labels) **stays exactly the same**. The Jira label workflow is universal. Two exceptions: set `agents.agent0_impact.enabled: false` until Change 7, and check the column names under `status_workflow` match your board.

### Change 2 — `app_inventory/<your_app>.json` (MANDATORY)

Delete the previous app's inventory. Create a new JSON file describing your app's pages, selectors, and methods. See `the "App inventory JSON schema" section below` for the schema.

This file is what Agent 2's planner uses to understand what page objects exist and what methods they expose. Get it right or Agent 2 will hallucinate methods.

**Bootstrap it, don't start from scratch.** The `scripts/generate_inventory.py` tool crawls your live app and emits a first-draft inventory with selectors already ranked and page objects guessed:

```bash
# Crawl the app configured in config.yaml, logging in via env credentials:
INVENTORY_USER="$APP_USER" INVENTORY_PASS="$APP_PASS" \
  python -m scripts.generate_inventory --crawl --max-pages 20 \
  --output app_inventory/<your_app>.draft.json
```

The tool is **fully app-agnostic**. Two knobs matter for a new app:

- `--test-attrs` — the test-id attributes it prefers/tracks. Defaults cover the common conventions (`data-test, data-testid, data-test-id, data-qa, data-cy, data-automation-id, data-tid`). If your app uses something else, pass it: `--test-attrs data-cy,data-qa`.
- Login — fields are auto-detected by input type. If the form is unusual (SSO, multi-step), override with `--login-url`, `--username-selector`, `--password-selector`, `--submit-selector`, or skip with `--no-login` for public pages.

The draft fills only what a machine can know (url, ranked selectors, page-object guess) and leaves `elements_notes`, `key_methods`, page-level `errors`, and `components` as **visible stubs** — a crawler can't infer behaviour, intended API, or exact error strings, so **always hand-review before committing**.

**Complex locators are handled.** The generator captures native controls *and* custom widgets that carry an interactive ARIA role, `tabindex`, or `contenteditable` (React-Select, MUI, toggles, etc.), giving them a churn-proof `role=combobox[name='…']` locator; it walks **iframes** (emitting `iframe#x >>> [selector]`, which means `page.frame_locator('iframe#x').locator(...)`); and it pierces **open shadow DOM**. Anything it can only reach via a fragile css fallback is listed under a page's `_unstable_selectors` so you know to add a `data-test`. What stays manual: un-accessible custom controls (a plain `<div onClick>` with no role/test-id), per-row list/table item locators (capture the container + a parametrized locator), and elements the app gives no stable hook for.

### Change 3 — `prompts/app_context/` module folder (MANDATORY)

These files ARE NOT templates — they're injected verbatim into Agent 1's prompt.
As of Phase 2 (backlog 2.1), app context is split into a **module folder** so a
large app only injects the modules relevant to the story being processed:

```
prompts/app_context/
  core.md          # ALWAYS injected — app name, base URL, global conventions
  login.md         # injected when the story's Jira Component == "Login"
  <component>.md   # one file per Jira Component (e.g. cart.md, checkout.md)
```

**How selection works** (`agents/agent1_analyst.py :: load_app_context_block`):

- `core.md` is injected on every run.
- For each Jira Component on the story, the matching `<component>.md` is added.
  Matching is case/space/hyphen-insensitive: a `"User Management"` component maps
  to `user_management.md`.
- A story with **no** components — or a component with **no** matching file —
  injects **ALL** modules. This is a safe default that never silently drops
  context. (A Login-tagged story injects ~49% fewer app-context tokens than the
  old single file.)
- **Backward compatible:** if the `prompts/app_context/` folder does not exist,
  the loader falls back to a single `prompts/app_context.md` file. You can start
  with one file and split into modules later.

Fill each module with your app's:

- Known test users / accounts and what each does
- Known error messages (exact wording, used in expected results)
- Page flow / URL structure
- Domain-specific notes the LLM needs

Name each module file to match a Jira Component on your project so selection
works. Put anything global (app name, base URL, cross-cutting rules) in `core.md`.

### Change 4 — Author ONE reference test (MANDATORY)

The framework's quality depends on one excellent hand-written reference test. Agent 2 mimics its style; Agent 3 compares new code against it. The reference is THREE files:

- `features/<reference>.feature` — Gherkin example
- `tests/step_defs/test_<reference>.py` — step definitions example
- `pages/<reference>_page.py` — page object example

Make this test:
- A typical user flow for your app (not an edge case)
- Self-contained (no shared state with other tests)
- Clean Gherkin (Given/When/Then with no awkward phrasing)
- Step defs that show `parsers.re` usage for quoted values (see Change 5 — **not** `parsers.parse`)
- At least ONE step defined locally in the paired module, so the reference
  demonstrates how to write a step — not just how to bind scenarios

This is the only file the LLM "studies" before generating code. Quality matters here more than anywhere else.

### Change 5 — `tests/step_defs/conftest.py` (MANDATORY)

**This file is required for every application.** Without it, the SECOND feature
file Agent 2 generates will fail at collection with
`pytest_bdd.exceptions.StepDefinitionNotFoundError`.

#### Why it is mandatory

pytest-bdd implements step definitions as **pytest fixtures**, and fixtures are
**module-scoped**. A step defined in `tests/step_defs/test_login.py` is visible
only inside that module — it is NOT available to `test_checkout.py` or to any
generated step-def file. The only supported cross-module sharing mechanism is
`conftest.py`, whose fixtures are shared with every test module in that
directory and below.

So any step or page-object fixture that **more than one feature needs** must
live in `tests/step_defs/conftest.py`. Steps specific to a single feature stay
in that feature's paired module.

> Proven empirically: a step defined in a sibling step-def module raises
> `StepDefinitionNotFoundError`; the same step moved to `conftest.py` passes.

#### Why it must be in `tests/step_defs/`, not `tests/`

Both validators discover on-disk step definitions with
`tests/step_defs/*.py`. Shared steps placed in `tests/conftest.py` would work at
runtime but be **invisible to the step-coverage validator**, so Agent 2 would
report phantom "missing decorator" errors. `tests/step_defs/conftest.py` is the
one location that satisfies both pytest and the validators.

#### The two conftest files — division of labour

The project has two `conftest.py` files, split along the same engine/app
boundary as the rest of the framework:

| | `tests/conftest.py` | `tests/step_defs/conftest.py` |
|---|---|---|
| **Contains** | `browser`, `page`, `base_url`, `config`, screenshot-on-failure hook | Page-object fixtures + shared step definitions |
| **Concern** | Playwright lifecycle & CI plumbing | Your application's step vocabulary |
| **New project** | **Reuse unchanged** — app-agnostic | **Rewrite** — app-specific |
| **Scope** | everything under `tests/` (incl. `tests/unit/`) | `tests/step_defs/` and below |

pytest merges conftest files hierarchically, so the step-def conftest
automatically inherits `page` and `base_url` from the parent — it never
redefines them.

Both belong in `reserved_paths`: they are human-owned foundations.

#### What to put in it

```python
"""Shared page-object fixtures and shared step definitions."""
import pytest
from pytest_bdd import given, when, then, parsers

from pages.login_page import LoginPage


@pytest.fixture
def login_page(page):          # `page` comes from tests/conftest.py
    return LoginPage(page)


@given("I am on the <your app> login page")
def open_login_page(login_page, base_url):
    login_page.open(base_url)


# One single-quoted line. parsers.re + [^"]* so empty values still match.
@when(parsers.re(r'I log in with username "(?P<username>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_credentials(login_page, username, password):
    login_page.login_as(username, password)
```

#### Two rules the file must follow

1. **`parsers.re`, not `parsers.parse`, for quoted values.** Validation
   scenarios pass empty values (`When I log in with username "" and password ""`).
   The `parse` library's default placeholder requires at least one character, so
   `parsers.parse` fails at runtime with `StepDefinitionNotFoundError` even
   though the decorator looks correct. `parsers.re(r'... "(?P<u>[^"]*)" ...')`
   matches both `"alice"` and `""`; named groups bind to arguments identically.

2. **Keep each decorator pattern on ONE single-quoted line.** The step-coverage
   validator extracts decorators with a regex that reads from the first quote to
   the last quote. Splitting a pattern across lines with implicit string
   concatenation corrupts the captured pattern, and **every** step using it
   silently stops matching.

#### Rule of thumb

> Needed by more than one feature → `conftest.py`.
> Specific to one feature → that feature's paired step-def module.

### Change 6 - Clean up the previous app's leftovers (RECOMMENDED)



Delete:

- the previous reference trio: `features/<old>.feature`,

  `tests/step_defs/test_<old>.py`, `pages/<old>_page.py`

- every other `pages/*_page.py` belonging to the old app

- `app_inventory/<old-app>.json` (after creating yours)

- every module under `prompts/app_context/` except your own - they

  describe the OLD app's behaviour and will mislead Agent 1 if left.

### Change 7 - Turn on Agent 0 (OPTIONAL)

Agent 0 needs two things from the new application before it can trace a change
to tests: `components` on every inventory page, and a `# JIRA:` marker above every
scenario (`python -m scripts.backfill_markers` adds missing ones). Then:

1. `python -m scripts.onboarding_check` — readiness: layout, inventory, markers, adapters
2. `enabled: true`, `shadow_mode: true` — reports only, scored by Agent 5
3. `shadow_mode: false` once the shadow reports are trusted — Impact Reviews go live

Details: [AGENT0_ONBOARDING.md](./AGENT0_ONBOARDING.md).

---

## Changing the test stack (e.g. Playwright + Python to Playwright + JS)

This is a DIFFERENT and larger job than changing the app. Changing the app
touches configuration; changing the language the generated tests are WRITTEN in
touches the layer that reads and checks that code.

### What does not change

Most of the repository, which is the claim "agent code never changes between
projects" tested against something harder than an app swap.

| Layer | Why it survives |
|---|---|
| All six agents' orchestration | They read a tracker, call an LLM, write text files, open a PR. None of them knows what language the text is in. |
| `core/llm_client.py`, `core/schemas.py` | Schema-in-prompt and Pydantic validation; provider- and language-agnostic. |
| `integrations/` — Tracker (23 ops), RepoHost (16 ops) | Nothing to do with the test stack. |
| **`app_inventory/*.json`** | `role=`, `text=` and `label=` are PLAYWRIGHT concepts, not Python ones. `page.getByRole('button', {name:'Save'})` in JS resolves the identical locator, so **the whole inventory carries over unchanged**. |
| `inventory_tools/` — crawler, ranking, staleness | Produces selectors, not code. |
| CI workflow structure, the label state machine, the sweeper | Unchanged. |

### What does change, in order

**1 · The reference trio — highest leverage.** `features/*.feature` stays as it
is: Gherkin is language-neutral. Rewrite the step-definition module and the
reference page object in JS, using Cucumber-JS's `Given/When/Then`. Everything
Agent 2 generates copies this style, so it shapes every later file.

**2 · `pages/base_page.py` → `base_page.js`.** 75 helpers. Keep every method
NAME: the inventory's `key_methods` and the validators both reference them.
Mechanical, but not small.

**3 · The runner.** `pytest.ini` becomes `cucumber.js`; Agent 4's workflow runs
`npx cucumber-js` instead of `pytest tests/step_defs/`. It must still emit
**junit.xml**, or Agent 5 has nothing to parse.

**4 · Five validators need a JavaScript parser — the real work.**
`agents/agent2_coder.py`, `validators/method_resolution_validator.py`,
`gherkin_analyzer.py`, `import_validator.py` and `orphan_cleanup.py` all use
Python's `ast` module, which cannot read JS. Swap for `@babel/parser` or
`ts-morph`. **The RULES survive; the tree-walking code is rewritten.** This also
covers the AST extraction that injects BasePage's method signatures into the
generation prompt.

**5 · Three prompts.** `agent2_coder_generate.md`, `agent2_coder_plan.md` and
`agent3_reviewer.md` carry Python syntax in every code example and convention.

**6 · Framework unit tests.** Around nine files assert pytest-bdd behaviour —
for instance that step definitions are MODULE-SCOPED. Cucumber-JS resolves steps
GLOBALLY, so those assertions must be re-derived against the new runner's actual
behaviour, not translated.

### Sizing, honestly

Steps 1–3 and 5 are a focused week. **Step 4 is the risk**: it is the
enforcement layer that stops the model shipping unusable code, and until it
works Agent 2 has no guardrails at all. Keep the Python stack running until
step 4 passes rather than switching wholesale.

### And if the target were Selenium instead

Substantially larger again, for two specific reasons rather than because Java or
C# is harder:

- **No `role=` / `text=` / `label=` engines.** The entire selector-ranking
  function has nothing to rank toward, so it needs re-deriving rather than
  translating — and you fall back to CSS/XPath more often, which is the
  brittleness this framework exists to avoid.
- **No strict mode.** Playwright THROWS when a locator matches several elements;
  that is the mechanism `multi_match` enforcement leans on. Selenium's
  `findElement()` silently returns the first match, so a 68-match locator
  becomes a silent wrong click instead of a loud failure. You would have to
  build that safety net yourself.

Also: no auto-waiting, so every BasePage helper needs explicit waits written by
hand.

---

## App inventory JSON schema

The inventory is the **only** application knowledge Agents 2 and 3 receive —
`prompts/app_context/*.md` goes to Agent 1 alone. Anything the code generator
must know belongs in `elements_notes` here.

Build it with the tooling rather than by hand; the full sequence, with commands,
is in [GUIDE.md](./GUIDE.md#inventory-tooling--the-full-sequence):

```
generate_inventory  ->  promote_draft  ->  verify_locators  ->  CURATE  ->  check_inventory_staleness
```

Steps one to three are mechanical. **Curation is the step that matters and
cannot be automated** — a crawler records what a page contains, never what it
means.

### Fields, and what to do with each

| Field | What it is | Action |
|---|---|---|
| `url` | page path | keep |
| `url_sample` | a real address for a templated `url` (`/records/{id}`) | add if the page is a template |
| `components` | Jira Components mapping to this page — crawler leaves EMPTY | **fill in**, or Agent 2 gets the whole inventory |
| `page_object_file` / `page_object_class` | where the page object lives | keep |
| `always` | `true` for shared chrome (navigation) | set on the nav page |
| `elements` | key → selector | trim to what tests need |
| `elements_notes` | per-key traps — crawler leaves EMPTY | **write this.** Highest-value field |
| `key_methods` | methods the page object should expose — EMPTY | **write this** |
| `multi_match` | keys matching several elements; enforced at generation time | verify |
| `conditional` | elements that exist only after an interaction | verify |
| `async_family` | a family the app fills asynchronously; an index pin is never valid | add where relevant |
| `errors` | validation message text | fill if the page has any |
| `implementation_status`, `title_seen` | draft markers | **delete** |
| `_selector_strategies`, `_ambiguous_selectors`, `_unstable_selectors`, `_fragile_selectors` | crawl-time review notes | **delete the blocks**, keep the elements |
| `_third_party_elements` | ad and widget embeds | **delete block and elements** |
| `_selectors_to_improve` | real elements on weak selectors | keep as a TODO, or fix |
| `_unresolved_selectors` | measured ZERO at crawl time | fix each — the element exists, the locator does not |

### `_` means two different things

| Where | Meaning | Sent to Agents 2 and 3? |
|---|---|---|
| Page level (`_selectors_to_improve`, `_third_party_elements`, ...) | review artefact — act on it, then delete | ❌ stripped |
| Top level (`_inventory_conventions`) | note to a human | ❌ stripped |
| **Inside `elements_notes`** (`_url`, `_naming`, `_shared`) | a note about the PAGE, not one element | ✅ **sent — keep them** |

Inside `elements_notes` every other key is an element NAME, so the prefix only
distinguishes a page-wide note from a per-element one. Deleting those on the
"anything with an underscore goes" rule throws away the guidance that stops the
generator inventing a record id or asserting on shared data.

`implementation_status` and `title_seen` carry no prefix and must be removed by
name.

### Selector ranking

test-id → `getByRole` → `getByLabel` → aria-label → placeholder → alt → title →
css `#id`/`[name=]` → text → css path. Anchors prefer their `href`, which is
exact and immune to markup inside the link. XPath is never emitted.

Two traps that each produced locators matching nothing:

- **An icon-only control has no accessible name**, so `role=button[name=…]`
  cannot match it — use its id.
- **An icon INSIDE a control poisons the name.** A CSS `::before` glyph joins
  the accessible name but is invisible to `textContent`. Elements with an icon
  descendant are located by attribute instead.