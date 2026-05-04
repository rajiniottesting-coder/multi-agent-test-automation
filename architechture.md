# 🏛️ Architecture Deep Dive

This document explains the role, inputs, outputs, and design rationale of each component in the multi-agent test automation system.

---

## The 5 Agents

The system is organized around **5 specialized agents**, each modeled after a role on a real QA/Dev team. They are numbered by their position in the pipeline.

---

### 🤖 Agent 1: Analyst (`agents/agent1_analyst.py`) ✅ Implemented

**Role analogy:** Business Analyst / QA Lead reading requirements.

**What it does:**
- Reads a user story from Jira (description + acceptance criteria).
- Calls Gemini with a structured prompt to derive test cases.
- Validates the LLM output against a Pydantic schema (`TestCaseList`).
- Creates each test case as a "Test Case" issue in Jira, linked to the story.
- Marks the story with `ai-processed` label for idempotency.

**Inputs:**
- Manual mode: a Jira story key (e.g., `SCRUM-3`)
- Scan mode: stories matching JQL filter (status + labels)

**Outputs:**
- 5–8 Jira "Test Case" issues per story, each containing:
  - Title prefixed with `[Positive]` / `[Negative]` / `[Edge]`
  - Description, priority, preconditions
  - Numbered steps with expected results
  - Test data (concrete usernames, payloads, etc.)
- Idempotency label on the parent story

**Human gate:**
- You review the generated Test Cases in Jira.
- Edit / delete bad ones, approve good ones (status change or label).

**Why this design:**
- **Pydantic-validated output** — LLM hallucinations / malformed JSON fail loudly, not silently.
- **Dry-run mode** — preview before writing to Jira (avoid spamming on prompt iteration).
- **Config-driven selection** — change behavior via YAML, no code changes.

---

### 🤖 Agent 2: Coder (`agents/agent2_coder.py`) 🚧 Day 4

**Role analogy:** SDET / Test Automation Engineer.

**What it will do:**
- Reads approved Test Cases from Jira (filtered by `ready-for-automation` label).
- Sends them to Gemini along with a **few-shot example** (the Day 2 reference test).
- Receives back: a `.feature` file, step definitions, and any new page object classes.
- Creates a feature branch (`auto/SCRUM-N-test-cases`), commits the files.
- Opens a Pull Request on GitHub with a descriptive title and body linking to the Jira story.

**Inputs:**
- Approved Test Cases (Jira issues with specific label)
- Existing reference test (`tests/step_defs/test_login.py`) as exemplar

**Outputs:**
- New files in the repo: `features/<feature>.feature`, `tests/step_defs/test_<feature>.py`, optionally new `pages/<page>.py`
- A GitHub Pull Request

**Human gate:**
- You review the PR on GitHub.
- Comment, request changes, or approve & merge.

**Why this design:**
- **Few-shot prompting** — the LLM mimics the style of your existing test, ensuring consistency (locator strategy, naming conventions, POM structure).
- **PR-based review** — uses GitHub's built-in collaboration tools rather than reinventing.
- **Branch isolation** — bad agent output never lands on `main` directly.

---

### 🤖 Agent 3: Reviewer (`agents/agent3_reviewer.py`) ⏳ Day 5

**Role analogy:** Senior Engineer doing code review.

**What it will do:**
- Triggered when a PR is opened by Agent 2 (Coder).
- Fetches the PR diff via GitHub API.
- Sends the diff to Gemini with a code-review prompt.
- Reviews for:
  - POM compliance (no selectors leaking into test files)
  - Hardcoded waits (`time.sleep`) instead of Playwright auto-waits
  - Missing assertions
  - Test data leakage
  - Naming conventions
- Posts review comments on the PR.
- Optionally runs `flake8` / `pylint` and includes findings.

**Inputs:**
- PR number / branch from Agent 2
- Project's code style guide (in `prompts/agent3_reviewer.md`)

**Outputs:**
- Review comments on PR
- Verdict: `approve` / `request_changes` / `comment`

**Human gate:**
- You read the AI review + your own assessment, then merge or reject.

**Why this design:**
- **Catches the boring stuff** — hardcoded waits, missing asserts. Saves senior engineers' time.
- **Two-pass review** — AI catches mechanics, human catches intent. Defense in depth.

---

### 🤖 Agent 4: Runner (`agents/agent4_runner.py`) ⏳ Day 5

**Role analogy:** Build/Release Engineer or test scheduler.

**What it will do:**
- Triggered by GitHub Actions on `push to main`, schedule, or manual dispatch.
- Decides what tests to run based on conditions:
  - Commit touches `pages/base_page.py` or config → full regression
  - Commit touches one feature file → smoke (just that feature + sanity)
  - Nightly schedule → full regression
  - Manual dispatch with tag → user-specified subset
- Executes the chosen pytest selection.
- Captures Allure results, Playwright traces, screenshots.

**Inputs:**
- Git diff (commit SHA, changed files)
- Optional: pytest markers / tags from user

**Outputs:**
- Test execution artifacts: `reports/allure-results/`, traces, screenshots
- Pass/fail summary as a state object for Agent 5 (Reporter)

**Human gate:**
- None for the default flow (CI is autonomous).
- For ad-hoc runs: humans pick markers via workflow dispatch UI.

**Why this design:**
- **Smart selection saves time** — full regression on every commit is wasteful and slow.
- **Conditions are config-driven** — no hardcoded "if filename contains X" in agent code.

---

### 🤖 Agent 5: Reporter (`agents/agent5_reporter.py`) ⏳ Day 5/6

**Role analogy:** QA Lead summarizing the test run.

**What it will do:**
- Reads test results from Allure / pytest output.
- Sends failures + logs to Gemini for summarization.
- LLM produces a human-readable summary: *"3 tests failed, all timeout-related on inventory page — likely environmental, not regression."*
- Posts summary as a comment on the original Jira story.
- Sends Slack/email notification (optional).
- Publishes Allure HTML report to GitHub Pages.

**Inputs:**
- `reports/allure-results/` (raw test results)
- Playwright traces / screenshots
- Original story key (for the Jira comment)

**Outputs:**
- Jira comment with summary + link to Allure report
- Slack/email notification
- Public Allure dashboard URL

**Human gate:**
- None — this is the final notification stage.

**Why this design:**
- **Failures need triage, not noise** — a 100-line stack trace is useless; a 2-sentence summary with a link is gold.
- **Closes the loop in Jira** — story → test cases → automation → results, all in one ticket.

---

## Cross-Cutting Components

These aren't agents — they're **shared infrastructure** every agent uses.

### `agents/jira_client.py`
- **Adapter pattern** wrapping the `jira` Python library.
- All Jira interactions go through this class — agents never call the library directly.
- Provides: `get_story`, `find_stories_to_process`, `create_test_case`, `add_label`, `_link_to_story`.
- Saved us during the Atlassian API v3 migration (only one file changed).

### `agents/llm_client.py`
- Wraps Gemini with:
  - **Tenacity retries** on rate-limit errors (Gemini free-tier is 10 RPM)
  - **Structured output** via `with_structured_output(Pydantic)` — no JSON parsing
  - Configurable temperature for creativity vs. determinism

### `agents/schemas.py`
- Pydantic models defining the **data contracts** between agents.
- Right now: `TestStep`, `TestCase`, `TestCaseList`.
- Future: `ReviewComment`, `RunResult`, `FailureSummary`.

### `config/paths.py`
- Centralized file/directory paths derived from `__file__`.
- Eliminates `Path(__file__).parent.parent...` repetition across files.
- One change here = consistent across the whole codebase.

### `config/config.yaml`
- Non-secret configuration: browser settings, test data, per-agent selection rules.
- Editable without redeploying code.

### `prompts/`
- Agent prompt templates as `.md` files.
- **Treated as code** — versioned in git, edited like code, with commit messages explaining changes.
- Each agent loads its prompt at runtime (`load_prompt()`).

---

## Why This Is "Multi-Agent" and Not Just Scripts

A reasonable question: *aren't these just Python scripts that call Gemini?*

The distinction is real and has 3 parts:

### 1. Specialization
Each agent has a focused role with its own prompt, schema, and tools. They aren't general-purpose — they're experts. Agent 1 doesn't know how to write Playwright code; Agent 2 doesn't know how to read Jira stories from scratch. **Each is good at one thing.**

### 2. Composability
Agents communicate through structured state (Pydantic models in/out). The orchestrator (Day 5) wires them: Agent 1's output (`test_case_keys`) becomes Agent 2's input. **No agent knows about another agent's internals.**

### 3. Human-in-the-loop
Each agent stops at a checkpoint. A human reviews and approves (or rejects) before the next agent picks up. This **isn't full autonomy** — it's collaborative AI, which is the right level for production QA work in 2026.

In contrast, a "monolithic" version would be one giant prompt: *"Read this Jira story, write tests, review them, run them, and report."* It would be brittle, hallucinatory, and impossible to insert human review into.

**Specialization + composability + checkpoints = real multi-agent architecture.**

---

## Design Principles Applied

| Principle | Where it shows up |
|---|---|
| **DRY** (Don't Repeat Yourself) | `config/paths.py`, shared `JiraClient`, `LLMClient` |
| **Single Responsibility** | One agent per role; one method per logical action |
| **Adapter Pattern** | `JiraClient` isolates the Atlassian SDK |
| **Configuration over Code** | `config.yaml` for selection rules; YAML > if/else |
| **Idempotency** | `ai-processed` label prevents re-running on the same story |
| **Defense in Depth** | 3-layer filter: status + required labels + excluded labels |
| **Fail Loud, Recover Gracefully** | Pydantic validation crashes on bad LLM output; per-story try/except in scan mode |
| **Audit Trail** | Logs at every step + Jira labels = "what did the AI touch when?" |

---

## Future Extensions (post-Day-7)

Things this design would support cleanly:

- **Multi-app support** — change `BASE_URL` and `prompts/agent1_analyst.md` to test a different app
- **Different LLM providers** — swap `langchain-google-genai` for `langchain-anthropic`; agents don't change
- **Webhooks instead of polling** — replace cron-based scan mode with Jira webhooks → no agent changes
- **More agents** — adding a "PerformanceTester" or "AccessibilityChecker" agent is a new file in `agents/` plus an entry in `config.yaml`
- **Multi-environment runs** — Agent 4 (Runner) could pick `dev` vs `staging` vs `prod` based on PR target branch