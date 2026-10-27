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

> **Verification status (22 Oct 2026):** the full unit suite
> passes (~3,000 offline tests). Deployed: v17/v18 prompt hardening, orphan
> cleanup (`ai-update` AND `ai-regenerate`), dynamic sprint scoping
> (`sprint: "auto"` via JIRA_BOARD_ID), end-to-end LLM token & cost
> instrumentation, module-wise app context (`prompts/app_context/`), inventory
> JSON minification, duplicate step-definition guard, per-story ledger reset
> marker, light-model routing (`LLM_MODEL_LIGHT` for Agents 1 and 5), the
> 32-check validator gate, acceptance-criteria coverage (every criterion mapped
> to the test that verifies it), board automation, and **Agent 0** (impact analysis,
> Impact Review, hand-over, context update, reconcile), protection for stories
> in flight at the same time (Agent 2 waits on open PRs; Agent 4's browser runs
> take turns) and a pull-request gate that skips the browser when only prompts,
> docs or Markdown change. Framework code, agent
> prompts and unit-test logic carry no application-specific references.

This guide explains exactly what to change to point this framework at a different application (e.g., banking app, CMS, internal portal, anything with a web UI testable by Playwright + pytest-bdd).

The framework's design principle is: **agent code never changes between projects. Only config, prompts/app_context, app inventory, and reference files change.**

---

## What stays the same (NEVER touch when reusing)

These files contain zero project-specific knowledge. Reuse as-is:

### Agents (the orchestration brains)
- `agents/agent0_impact.py` — change story → affected tests, Impact Review (Agent 0)
- `agents/agent1_analyst.py` — Jira → Test Cases; `agents/agent1_impact.py` — revise approved tests
- `agents/agent2_coder.py` — Test Cases → Playwright code + PR; `agents/agent2_impact.py` — change-story splice; `agents/agent2_coverage.py` — every approved test case covered or named (`ai-incomplete`); `agents/agent2_review_fix.py` — fixes what a PR's reviewer asks for
- `agents/agent3_reviewer.py` — PR review
- `agents/agent5_reporter.py` — results and cost to Jira; scores Agent 0
- `core/impact_*.py`, `core/context_update.py`, `core/json_block.py` — Agent 0's graph, analysis, review, hand-over, reconcile, context update
- `core/inventory_update.py`, `scripts/propose_inventory_update.py` — the nightly inventory-update PR from the drift report (no app names; settings `agents.agent0_impact.inventory_update`)
- `core/inventory_planned.py`, `scripts/plan_inventory.py` — planned inventory entries (an element or a page from the design, before deployment); confirmed by the nightly update once live
- `core/board_status.py`, `core/test_case_rules.py`, `core/failure_diagnosis.py`, `core/allure_*.py`
- `core/in_flight.py` (stories in flight), `core/test_runtime.py` (what a test reads), `scripts/e2e_turn.py` (browser runs take turns)
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
- `tests/conftest.py`, `tests/step_defs/conftest.py` — browser lifecycle, auto-registered page-object fixtures, role-based `credentials` (see Change 5)

### Agent prompts (templated, read app info from config at runtime)
- `prompts/agent0_seeds.md`, `prompts/agent0_adjudicate.md`, `prompts/agent0_wording.md`, `prompts/agent0_context_notes.md`, `prompts/agent0_context_additions.md`
- `prompts/agent1_analyst.md`, `prompts/agent1_impact_aware.md`
- `prompts/agent2_coder_plan.md`
- `prompts/agent2_coder_generate.md` — all generation rules + BasePage helpers section
- `prompts/agent2_review_triage.md` — Agent 2's review fix: fix / decline / no_change per review comment
- `prompts/agent3_reviewer.md`
- `prompts/agent5_reporter.md`

### Universal page-object helpers
- `pages/base_page.py` — 86 generic Playwright-native helpers. Universal across projects.

### Unit tests (the test suite is project-agnostic)
- everything under `tests/unit/` (~3,000 offline tests) — synthetic fixtures (banking, CMS, a fake tracker and repo host), for example:
- `tests/unit/test_orphan_cleanup.py` — uses banking + CMS fixtures
- `tests/unit/test_pipeline_tool_agnostic.py` — the pipeline against an in-memory tracker
- `tests/unit/test_validators.py` — a fixture uses "Admin" as a generic role placeholder, not tied to any app

### Infrastructure
- `.github/workflows/*.yml` — all eleven workflows
- `requirements.txt`
- `pytest.ini`
- `config/__init__.py`, `config/paths.py`

---

## What you MUST change (project-specific touch points)

There are **6 changes** for a new project, plus an optional seventh (Agent 0) and an eighth for operations (health issue, defects, budgets). They are ranked by criticality.

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
    - "pages/base_page.py"        # universal helpers — never edited by an agent

  # Every page object already committed under pages/ is extendable
  # automatically (new methods only, none removed). List a file here only for
  # something the automatic rule cannot see - see GUIDE.md, "extendable_paths".
  extendable_paths: []
  auto_extend_page_objects: true
```

ALSO update the legacy top-level `base_url:` alias:

```yaml
base_url: https://bank.acme.example.com   # was: the previous app's base URL
```

Login roles are NOT in `config.yaml`: rename the `APP_USER_<ROLE>` variables in
`.env` and GitHub Secrets to the new app's roles (Change 5).

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
> **The pattern the framework uses — keep the knowledge, move the secret:**
>
> ```bash
> # .env (gitignored) and GitHub Secrets — one username per ROLE
> APP_USER_ADMIN=admin_user
> APP_USER_LOCKED=locked_user
> APP_PASSWORD=...            # shared, or APP_PASSWORD_<ROLE> per role
> ```
>
> ```markdown
> <!-- prompts/app_context/login.md — behavioural knowledge, no secrets -->
> | Role | Notes |
> |---|---|
> | `admin`  | Full permissions; can approve |
> | `locked` | Receives lockout error on login |
> ```
>
> Features log in by role (`When I log in as "admin"`); the `credentials`
> fixture in `tests/step_defs/conftest.py` reads `APP_USER_ADMIN` and the
> password at runtime. Nothing secret is in a committed file or a prompt.
>
> Agent 1 still learns everything it needs — *that* a locked user exists and *what*
> happens when it logs in — which is what drives good test-case design. It never
> needs to know the password.
>
> **The same rule applies to any other secret** that might drift into these files:
> API keys, DB connection strings, tokens. Behavioural knowledge in the prompt;
> secrets in the environment.

The `agents:` section (label selection rules, completion labels) **stays exactly the same**. The Jira label workflow is universal. Two exceptions: set `agents.agent0_impact.enabled: false` until Change 7, and check the column names under `status_workflow` match your board. The operational blocks (`pipeline_health`, `flaky_tests`, `defects`, `budget`) are Change 8.

### Change 2 — `app_inventory/<your_app>.json` (MANDATORY)

Delete the previous app's inventory. Create a new JSON file describing your app's pages, selectors, and methods. See `the "App inventory JSON schema" section below` for the schema.

Agents 2 and 3 read it for every page and selector; an element missing here is an element Agent 2 cannot use. (The methods a page object exposes are read from the page objects themselves, by AST - not from this file.)

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

**How selection works** (`core/app_context.py :: select_note_modules` - one rule for Agent 1's draft and Agent 0's context update):

- `core.md` is injected on every run.
- For each Jira Component on the story, the matching `<component>.md` is added.
  Matching is case/space/hyphen-insensitive: a `"User Management"` component maps
  to `user_management.md`.
- A story with **no** components — or a component with **no** matching file —
  injects **ALL** modules. This is a safe default that never silently drops
  context. (A Login-tagged story injects ~49% fewer app-context tokens than the
  old single file.)
- **Keep each module small.** Every selected module goes into the prompt;
  `agents.agent0_impact.context_update.module_budget_chars` (8000) is the
  budget the unit suite and the onboarding check enforce. Shared facts belong
  in `core.md` once, not repeated per module.
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

### Change 5 — Login roles and `.env` (MANDATORY if the app has a login)

`tests/step_defs/conftest.py` is **app-agnostic and reused unchanged** — do not
rewrite it. It holds fixtures only:

- **One fixture per page object, registered automatically.** Every `BasePage`
  subclass in `pages/` becomes a fixture named after its class
  (`SearchResultsPage` → `search_results_page`). A new page object needs no
  conftest edit.
- **`credentials`** resolves a login ROLE to a username and password from the
  environment: role `"admin"` → `APP_USER_ADMIN`, and `APP_PASSWORD_ADMIN`,
  else `APP_PASSWORD`. Features log in by role (`When I log in as "admin"`),
  never with a literal credential.
- `run_id` / `unique_username` for data a run creates on a shared application.

So the per-app work is in the environment, not in Python: define one
`APP_USER_<ROLE>` per role (and `APP_PASSWORD` or `APP_PASSWORD_<ROLE>`) in
`.env` locally and in GitHub Secrets for CI, and describe what each role can do
in `prompts/app_context/`.

#### Step definitions are self-contained

pytest-bdd implements step definitions as **pytest fixtures**, which are
**module-scoped**: a step defined in `tests/step_defs/test_login.py` is not
visible to another step-def module. Every generated step-def module therefore
declares **every** step its own feature uses — even when another module already
declares the same text. That duplication is safe (each module resolves its own
copy); the duplicate-step guard flags only the same phrase twice in ONE file,
where the second silently shadows the first. Since #190 a phrase another
feature already defines must also assert no more than that definition does.

The two conftest files split along the engine/app boundary, and both are
reused unchanged:

| | `tests/conftest.py` | `tests/step_defs/conftest.py` |
|---|---|---|
| **Contains** | `browser`, `page`, `base_url`, `config`, failure-evidence capture | auto-registered page-object fixtures, `credentials`, `run_id` |
| **Concern** | Playwright lifecycle & CI plumbing | the page objects and login roles of whatever app is configured |
| **Scope** | everything under `tests/` | `tests/step_defs/` and below |

Two rules still apply to the reference step definitions you write in Change 4:

1. **`parsers.re`, not `parsers.parse`, for quoted values.** Validation
   scenarios pass empty values (`When I log in with username "" and password ""`).
   The `parse` library's default placeholder requires at least one character, so
   `parsers.parse` fails at runtime with `StepDefinitionNotFoundError` even
   though the decorator looks correct. `parsers.re(r'... "(?P<u>[^"]*)" ...')`
   matches both `"alice"` and `""`.
2. **Keep each decorator pattern on ONE single-quoted line.** The step-coverage
   validator reads a decorator from its first quote to its last, so a pattern
   split across lines by implicit string concatenation stops matching.

### Change 6 - Clean up the previous app's leftovers (RECOMMENDED)



Delete:

- the previous reference trio: `features/<old>.feature`,

  `tests/step_defs/test_<old>.py`, `pages/<old>_page.py`

- every other `pages/*_page.py` belonging to the old app

- `app_inventory/<old-app>.json` (after creating yours)

- every module under `prompts/app_context/` except your own - they

  describe the OLD app's behaviour and will mislead Agent 1 if left.

- the previous app's `APP_USER_<ROLE>` variables in `.env` and GitHub Secrets

### Change 7 - Turn on Agent 0 (OPTIONAL)

Agent 0 needs two things from the new application before it can trace a change
to tests: `components` on every inventory page, and a `# JIRA:` marker above every
scenario (`python -m scripts.backfill_markers` adds missing ones). Then:

1. `python -m scripts.onboarding_check` — readiness: layout, inventory, markers, adapters
2. `enabled: true`, `shadow_mode: true` — reports only, scored by Agent 5
3. `shadow_mode: false` once the shadow reports are trusted — Impact Reviews go live

Details: [AGENT0_ONBOARDING.md](./AGENT0_ONBOARDING.md).

### Change 8 - Operations: health issue, defects, budgets (RECOMMENDED)

Nothing here names the application; check that the tracker matches:

1. `pipeline_health.issue_type` (Task) and `defects.issue_type` (Bug) exist in the
   project, and `defects.open_statuses` are its board columns before done.
2. Set the `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M` variables - without
   them no spend budget is enforced. Start `budget.per_story_usd` and
   `per_day_usd` from the costs Agent 5 reports for the first stories; raise them
   as the repository grows.
3. Run *Pipeline health* once by hand, so its issue exists, and have the team
   **watch** it.
4. The nightly run (`agent4_runner.yml`, 03:10 IST) runs the whole suite on
   `main`; move the cron outside the new application's business hours if
   needed.

A tracker adapter other than Jira needs the optional capabilities
(`create_issue`, issue properties, `check_access` - `integrations/tracker.py`)
for these features; without them the features say so once in the log and stay
off, and nothing else changes.

The story's model-cost ledger (F-31) also uses issue properties, plus
`update_comment` (and `properties` to read them in one request): with them a
story shows one cost comment per attempt, edited in place; without them it
keeps the original `[LLM-USAGE]` comment per run and Agent 5's table - nothing
to configure either way. `usage_ledger.store: comments` chooses the original on
purpose. The bot account needs to edit its own comments; switching the edit
notification off needs a (project) administrator, and without it the edit
notifies.

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
| `integrations/` — Tracker (23 ops), RepoHost (20 ops) | Nothing to do with the test stack. |
| **`app_inventory/*.json`** | `role=`, `text=` and `label=` are PLAYWRIGHT concepts, not Python ones. `page.getByRole('button', {name:'Save'})` in JS resolves the identical locator, so **the whole inventory carries over unchanged**. |
| `inventory_tools/` — crawler, ranking, staleness | Produces selectors, not code. |
| CI workflow structure, the label state machine, the sweeper | Unchanged. |

### What does change, in order

**1 · The reference trio — highest leverage.** `features/*.feature` stays as it
is: Gherkin is language-neutral. Rewrite the step-definition module and the
reference page object in JS, using Cucumber-JS's `Given/When/Then`. Everything
Agent 2 generates copies this style, so it shapes every later file.

**2 · `pages/base_page.py` → `base_page.js`.** 86 public helpers. Keep every
method NAME: the generation prompt lists them and the validators reference them.
Mechanical, but not small.

**3 · The runner.** `pytest.ini` becomes `cucumber.js`; Agent 4's workflow runs
`npx cucumber-js` instead of `pytest tests/step_defs/`. It must still emit
**junit.xml**, or Agent 5 has nothing to parse.

**4 · The code readers need a JavaScript parser — the real work.**
`agents/agent2_coder.py`, `validators/method_resolution_validator.py`,
`gherkin_analyzer.py`, `import_validator.py`, `orphan_cleanup.py` and
`page_object_contract.py` all use Python's `ast` module, which cannot read JS.
So does Agent 0's layer-1 graph builder (`core/impact_graph.py`); a new stack
registers its own builder (AGENT0_ONBOARDING.md, step 3). Swap for `@babel/parser` or
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
| `key_methods` | legacy — no agent reads it; Agent 2 reads the real page objects by AST | **leave empty** |
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