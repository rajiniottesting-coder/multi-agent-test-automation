# AI Concepts in This Project — and Demo Q&A

A map of which AI/LLM engineering concepts this project uses, which it
deliberately doesn't, and the questions peers are likely to ask in a demo.

---

## 1. Guardrails — "why aren't guardrails implemented?"

**They are. This project has extensive guardrails — they're just implemented
as deterministic code, not as a guardrails library.** "Guardrails" as a
concept means: constraints that prevent an LLM from producing or acting on
unsafe/invalid output. This project enforces them at four layers:

| Layer | Guardrail | Where |
|---|---|---|
| **Input** | Label state machine — LLM only ever sees stories a human explicitly marked `ai-ready` / `human-approved` / `impact-check`. No arbitrary input reaches the model. | config.yaml selection blocks + JQL |
| **Output schema** | Structured outputs via Pydantic: the JSON schema goes into the prompt and the reply is parsed back through it (provider-agnostic — no tool-calling needed). One repair attempt, then it raises before any side effect. 21 schemas. | `LLMClient.invoke_structured()` + `core/schemas.py` |
| **Output content** | 28 static checks on generated code (filename consistency, Gherkin structure, step coverage, path policy, imports, method resolution, selector boundaries, waiting predicates, …); test-case rules on Agent 1's drafts; Agent 0's evidence check (a verdict citing no real graph path or verbatim step is dropped, invented element keys are dropped). Invalid output never reaches a commit or a ticket. | `validators/`, `agents/agent2_coder.py`, `core/test_case_rules.py`, `core/impact_analysis.py` |
| **Action / blast radius** | Path policy (reserved files can NEVER be written; extendable files can never be wiped), `max_stories_per_run` caps, human gates before any test-case revision (Impact Review), before code gen and before any merge, one-shot label consumption, Agent 0 shadow mode, Agent 3 blocking only for a named failure, context updates as PRs (never auto-merged). | `validate_paths_against_policy()`, config caps, GitHub branch rules |

What we do NOT have (and why that's fine at current scope):
- **Content-safety filters** (toxicity, PII): the model only generates
  Playwright test code from internal Jira tickets — the input and output
  domains are narrow and non-user-facing.
- **A guardrails framework** (Guardrails-AI, NeMo Guardrails): those shine
  when you need declarative rail specs over many free-form outputs. Our
  outputs are code, and code has a better validator than any rail spec:
  parsers, AST analysis, and test execution.

If asked "what's your riskiest unguarded surface?" the honest answer is:
prompt injection via Jira ticket content — a malicious story description
could try to steer the coder agent. Mitigations in place: human-approval
gate (a human reads every story and test case before Agent 2 runs), path
policy (even a steered LLM cannot touch reserved files or workflows), and
PR review (a human reads every diff before merge). For a change story the
Impact Review adds a gate before any existing test is revised.

---

## 2. Concepts actually used (know these cold for a demo)

| Concept | Industry name | Where in this repo |
|---|---|---|
| Multiple specialized agents with durable handoffs | **Multi-agent architecture / agentic pipeline** | 6 agents (0–5); Jira labels, marker comments + GitHub as the shared state |
| Labels controlling triggering, idempotency, one-shot actions | **Agent state machine / orchestration** (what LangGraph models in memory, we model in Jira) | config.yaml selection blocks |
| Plan first, then generate per-file | **Prompt chaining / decomposition** (Plan-and-Execute pattern) | `build_plan()` → `generate_file_content()` loop |
| Pydantic-enforced JSON, schema in the prompt | **Structured outputs** | `invoke_structured()`, `core/schemas.py` |
| Validators feed errors back to the LLM for retry | **Reflexion / self-correction loop** | `_attempt_step_coverage_repair()`, max 4 attempts; one corrective retry in Agent 1 and in the splice writers |
| Graph finds candidates, the model judges, a formula ranks | **Hybrid retrieval + LLM-as-judge, deterministic scoring** | Agent 0: `core/impact_graph.py` → `ImpactAssessment` → `rank()`; the model's verdict caps the tier |
| A verdict must cite a real path or a verbatim step | **Grounding / citation check** | Agent 0's evidence check in `core/impact_analysis.py` |
| Run beside production, write nothing, measure | **Shadow deployment / online evaluation** | Agent 0 shadow mode; Agent 5 scores each prediction (`record_prediction_outcome()`); `scripts/agent0_backtest.py` for offline evaluation |
| Every model writer gets the facts it must not invent | **Grounded generation** | readable values, real page-object signatures; `tests/unit/test_splice_grounding.py` fails an ungrounded writer |
| Already-generated method signatures injected into later prompts | **Context injection (RAG-style, in-run retrieval)** | `_build_sibling_page_object_context()` — AST-extracted, not embeddings |
| One gold-standard example the LLM mimics | **Few-shot prompting / reference-based generation** | reference_files in config.yaml |
| Catalogued failures → prompt rules + validators | **Prompt engineering as institutional memory** | the "Lessons learned" section below |
| Human must approve before revisions, code gen and merge | **Human-in-the-loop (HITL)** | Impact Review, `human-approved` label, PR review |
| Snapshots let a rejected change be rolled back | **Compensating actions / undo** | Agent 1 snapshots; reconcile restores them when the PR is closed unmerged |
| SHA-256 hash markers to detect changed inputs | **Content-addressable change detection** (not ML, but ask-worthy) | `# JIRA: KEY (hash: xxx)` markers |

## 3. Concepts NOT used — and the honest reason

| Concept | Why not here |
|---|---|
| **LangGraph / CrewAI / agent frameworks** | Our "graph" is the Jira label machine (`ai-ready` -> `ai-processed` -> `human-approved` -> `ai-coded` -> `tests-run`), which is externally observable, survives process death, and costs zero tokens to coordinate — an in-memory graph does none of those. Raw API + custom orchestration also means no framework churn. **LangChain itself IS used**, but only as a provider-agnostic HTTP client (`ChatOpenAI` + message types, two imports in `llm_client.py`) — no chains, agents, tools or memory. Structured output is Pydantic, not LangChain. |
| **Vector DB / embeddings / semantic RAG** | Dedup is exact-title matching on ~dozens of scenarios; page-object retrieval is AST-based and exact; Agent 0's candidates come from a code graph plus lexical relevance within the story's Components. Embeddings would add infra and fuzziness where we need precision. |
| **LangSmith / hosted tracing** | Token and cost tracking is `core/usage_ledger.py`, which posts `[LLM-USAGE]` directly onto the Jira story — the number lands on the work item, and no third party holds our prompts. LangSmith is present in `pip list` only as a transitive dependency of `langchain-core`; nothing imports it. |
| **Fine-tuning** | Failure modes were fixable with prompt rules (see the "Lessons learned" section below); fine-tuning freezes behavior into an uninspectable artifact. |
| **Runtime memory / learning loop** | Lessons are curated into prompts at development time — zero marginal token cost. see "Why not runtime learning" in the Lessons learned section below. |
| **Multi-model routing** | One model keeps behavior predictable; the LLM client is a single swap point if we ever route (e.g., cheap model for Agent 5 summaries). |
| **Evals / benchmark harness** | Partially covered: the unit suite pins validator behaviour; the real "eval" is Agent 4 running the generated tests; Agent 0 has a backtest and per-story prediction scoring. A dedicated prompt-regression eval set for Agents 1–3 is a fair future item. |

## 4. Demo Q&A — questions you should expect

**Q: Why six agents instead of one big agent?**
A: Context-window economics, natural human checkpoints (approve test cases before code), and durability — every agent's output is persisted (Jira issue, commit, PR comment) so a crash loses nothing. One mega-agent would lose its place.

**Q: How do agents communicate without a message bus?**
A: They don't talk to each other at all. Each reads state from Jira/GitHub and writes state back. The Jira label set IS the message. This makes the whole pipeline observable from the Jira board and recoverable from any point.

**Q: What stops the LLM from hallucinating code that doesn't run?**
A: 28 static checks + a repair loop before any commit — the model is also handed the real method signatures, so it has less to invent — then Agent 4 actually executes the tests, then a human reviews the PR. Three independent nets.

**Q: What happens when the LLM output fails validation?**
A: Repairable failures go through the Reflexion loop — the exact validator errors are fed back and only the broken file is regenerated, up to 4 times. Non-repairable failures abort the run with the LLM output logged; no partial commits, no PR.

**Q: How do you prevent the agent from modifying critical files?**
A: Path policy validator. Reserved paths (reference files) can never appear in a plan; extendable paths can be appended to but never recreated. This is checked on the PLAN, before any generation happens.

**Q: How does it handle a Test Case being edited or deleted after code exists?**
A: Hash markers. Every scenario carries `# JIRA: KEY (hash: 8char)` — SHA-256 of the Jira description. Edited → hash mismatch → surgical regeneration of just that scenario (`ai-update`). Deleted → orphan key → scenario removed, dead page-object methods detected via AST and commented out with `# AI-ORPHAN:` banners.

**Q: A story changes behaviour that existing tests check. How do you find them?**
A: Agent 0. One call names the elements the story changes; a code graph (scenario → step → method → selector) finds the scenarios that reach them; a second call judges each with evidence; a weighted score ranks them, capped by the model's verdict. A person then approves, rejects or retires each test in an Impact Review — nothing is revised before that. Agent 5 later scores the prediction against what the PR actually changed and failed.

**Q: And if the change is rejected?**
A: Agent 1 snapshots every test before revising it. If the PR is closed without merging (seen on two scans, so a sweeper close-and-reopen doesn't count), reconcile restores each test's old text, un-retires tests, removes the links, resets the story's labels and moves the card back to To Do.

**Q: Prompt injection — what if someone puts instructions in a Jira ticket?**
A: Human-approval gate means a human reads the story and generated test cases before the coder runs; path policy caps what a steered model could touch; PR review catches anything that gets through. We treat ticket text as data, but the real defense is that no output reaches production without two human checkpoints.

**Q: Why not LangChain / LangGraph for orchestration?**
A: LangChain is used only as the HTTP transport (`ChatOpenAI` + message types). The patterns it offers — chains, structured output, retries — are written directly, and the orchestration state lives in Jira, which beats an in-memory graph for durability and observability: the agents never share a process.

**Q: How does it learn from mistakes?**
A: Two mechanisms. Within a run: the repair loop (validator errors → retry). Across runs: a curated failure catalog (the "Lessons learned" section below) distilled into prompt rules and validators — permanent, token-free, version-controlled. Deliberately not a runtime memory store; see the catalog for the trade-off analysis.

**Q: What does a run cost and how is cost bounded?**
A: Measured, not estimated — and tokens and cost are tracked separately. Every LLM call records API-reported token usage (`core/llm_client.py`); each story run ends with two log lines: `LLM TOKEN USAGE` (exact counts) and `LLM COST` (input + output cost from the `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M` repo variables). For the full story cost, every LLM-using agent posts a `[LLM-USAGE]` comment to the story, and Agent 5 aggregates them into an "End-to-end LLM usage & cost" table in its final report (`core/usage_ledger.py`) — the actual measured cost of Agents 1, 2, 3 and 5 for that story in one place. Agent 0's calls are logged in its own run (`LLM TOKEN USAGE` / `LLM COST`) but not yet posted to the story's ledger. Cost scales with test-case count and repair-loop retries on top of a fixed prompt-overhead floor. Bounding is separate from measurement: `max_stories_per_run` caps blast radius per cron tick; the human-approval gate stops accidental mass processing.

**Q: How would this scale to 50 stories a sprint?**
A: Raise the per-run cap, or parallelize — each story is independent (own branch, own PR, no shared state). The bottleneck becomes human review of PRs, which is by design.

**Q: What's the weakest part of the system?**
A: Honest answers impress: (1) dedup is title-based, so a reworded duplicate slips through, (2) no dedicated prompt-regression eval suite for Agents 1–3 yet, (3) Agent 0 is only as good as the scenario markers and inventory `components` it reads — gaps are reported as unknown, not as unaffected.

---

## Lessons learned — the failure catalog

This file is the project's **failure memory**. Every entry is a real production
failure observed in CI logs, the root cause, and where the permanent fix lives.

**How this project "learns":** lessons are encoded as *prompt rules* and
*validators*, not runtime memory. Once a failure mode is caught here, the fix
is permanent — the LLM cannot repeat it because either (a) the prompt now
forbids it explicitly, or (b) a validator blocks the output before commit and
the repair loop forces a retry with error feedback. This is cheaper and more
reliable than runtime learning: zero extra tokens per run, deterministic
enforcement, and version-controlled history.

**Maintenance rule:** when a NEW failure mode appears in production, add a row
here FIRST, then implement the fix (prompt rule or validator), then link it.
This file is the single place a new team member reads to understand why the
prompts look the way they do.

| # | Version | Failure observed (production) | Root cause | Permanent fix | Enforced by |
|---|---------|------------------------------|------------|---------------|-------------|
| 1 | v9 | Generated step defs missing decorators for some feature steps → collection errors | LLM skipped steps when scenario count was high | Self-correcting repair loop: validator errors fed back to LLM, up to 4 retries per file | `_attempt_step_coverage_repair()` in agent2_coder.py + `validate_step_definitions_complete()` in gherkin_analyzer.py |
| 2 | PR #7 | `features/sort-products.feature` paired with `test_sort_products.py` — kebab vs snake_case mismatch → feature not found at runtime | LLM inconsistent about filename casing across files in one plan | Filename consistency validator with auto-correct | `validate_filename_consistency()` in gherkin_analyzer.py |
| 3 | PR #9 | Validator passed but pytest-bdd failed at runtime on `parsers.parse` with empty quoted values | Our validator was more permissive than pytest-bdd's actual `parse` backend | Validator now uses the SAME `parse` library pytest-bdd uses at runtime | `_phrase_matches()` in gherkin_analyzer.py |
| 4 | PR #14 | Orphan `Given/When/Then` lines outside any Scenario block → cryptic collection error | LLM emitted stray steps after the last scenario | Feature structure validator | `validate_feature_file_structure()` in gherkin_analyzer.py |
| 5 | v12 | Stage 1 plan JSON parse failures (markdown fences, trailing prose) | Free-text JSON is unreliable | Structured output: Pydantic schema in the prompt, reply parsed through it, one repair retry | `LLMClient.invoke_structured()` |
| 6 | v12e | Code extraction failed when LLM emitted 6-backtick fences | Model occasionally doubles fence characters | Normalize 4+ backticks to 3 before extraction | `extract_code_from_response()` in agent2_coder.py |
| 7 | v15 | Validator rejected valid cross-file step reuse (step defined in another file) | Validator only looked at the paired step-def file | Cross-file awareness: check pre-existing step-def files on disk too | `validate_step_definitions_complete()` |
| 8 | v17 | `[float(p.replace("$",...)) for p in prices]` when method already returned `list[float]` → AttributeError | LLM ignored declared return types | Type-contract awareness prompt rule | prompts/agent2_coder_generate.md §Type contract awareness |
| 9 | v17 | Invented `.active_option` CSS class on native `<select>` → selector never matched | LLM hallucinated framework-specific DOM patterns | Locator discipline prompt rule (`input_value()` / `evaluate()`) | prompts/agent2_coder_generate.md §Locator discipline |
| 10 | v18 | `@then("I should be on the inventory page")` vs feature's "redirected to the inventory page" → StepDefinitionNotFoundError | LLM paraphrased instead of exact-matching | Exact phrase matching rule with examples | prompts/agent2_coder_generate.md §Step 2 |
| 11 | v18 | `parsers.parse('sort by {key}')` captured quotes into the variable → comparisons always failed | Quote-placement subtlety in `parse` templates | parsers.parse quote-handling rule (`"{value}"` vs `{value}`) | prompts/agent2_coder_generate.md §Step 3 |
| 12 | v18 | LLM re-invented dropdown/wait patterns differently every run → inconsistent, sometimes broken | No shared primitives to call | Generic BasePage helpers (10 at v18, 85 today); prompt lists them | pages/base_page.py + prompt §BasePage helpers |
| 13 | May 2026 | Deleted Jira Test Cases left dead page-object methods forever | ai-update preserves page objects by design | Orphan detection: AST analysis, comment-out with `# AI-ORPHAN:` banners | validators/orphan_cleanup.py |
| 14 | May 2026 | Scan picked up stories from old sprints | JQL had no sprint clause | Sprint scoping: `sprint: "auto"` resolves active sprint via JIRA_BOARD_ID | integrations/jira_client.py `get_active_sprint_name()` |
| 15 | SCRUM-54 | A new login-adjacent feature re-declared `@given("I am on the OrangeHRM login page")`, already defined in the reference `test_login.py` → pytest-bdd registers steps globally across the package, so the duplicate collides at collection time (Agent 3 flagged it) | LLM re-declares common steps (navigation, login) in the new file instead of reusing the reference's existing ones — it doesn't know they're already registered package-wide | (a) prompt rule: reuse existing steps, never re-declare; (b) cross-file duplicate validator — narrowly flags only genuine (keyword, parser_type, phrase) collisions across step-def files incl. the reference | `validate_no_duplicate_step_definitions()` in gherkin_analyzer.py + prompts/agent2_coder_generate.md §rule 13 |
| 16 | PR #149 / #162 | Agent 3 turned PRs red for failures no test showed, and for lines the PR never changed | A predicted failure was treated as a fact | Blocking needs a named failure scenario; a green Agent 4 run on the same commit refutes it; unchanged lines only advise | `postprocess_review()` in agents/agent3_reviewer.py |
| 17 | PR #151 | Re-running an old check replayed an outdated reviewer copied onto the PR branch | The workflow checked out the PR head | Agent 3 checks out the base branch | `.github/workflows/agent3-reviewer.yml` |
| 18 | PR #164 | An Impact Review table could read as empty | Jira turned test keys into links | Keys read in every link form; an unreadable or empty review refuses to hand over | `core/impact_review.py`, `core/impact_handover.py` |
| 19 | PR #166 | A renamed label left a broken selector and notes teaching the old wording | No agent writes the reference material | Context-update PR at hand-over (wording; since #173 also passages the story makes untrue) | `core/context_update.py` |
| 20 | PR #169 | A change story's spliced step called a page method that does not exist, after the repair loop | The splice writers lacked the grounding the full-file writers had | Grounding for every model writer + one corrected retry; contract test for new writers | `agents/agent2_coder.py`, `tests/unit/test_splice_grounding.py` |
| 21 | PR #171 | The PR said an orphan was commented out, but the file was not in the PR | The cleanup's change was committed only when a step was added | Commit the file whenever the cleanup changed it | `agents/agent2_impact.py` |
| 22 | PR #172 | No outcome was posted for a reviewed change | Jira re-stored an edited JSON code block in another format | One reader for every format Jira writes; unreadable data warns | `core/json_block.py` |
| 23 | PR #173 | A test the model judged "review" ranked must-update on structure alone | The score ignored the model's verdict | The verdict caps the tier | `rank()` in core/impact_analysis.py |
| 24 | PR #173 | A "not shown" assertion passed while the element was still loading | A probe that waits for the element was used to assert absence | New validator | `validate_absence_not_asserted_with_waiting_probe()` |
| 25 | PR #173 | After an undo the story kept `ai-coded`/In Review and its unshipped tests stayed active | The undo restored the other stories but not this one | Retire unshipped tests, reset labels, card to To Do, retry steps | `_settle_story()` in core/impact_reconcile.py |
| 26 | PR #181 | Agent 2 failed a change story: a step function its revisions and retirement left unused | The cleanup only reported orphan step functions, only after retirements, and commented-out code still counted as a definition | Step functions the change left unused are commented out deterministically after every splice; commented-out decorators no longer count | `comment_out_step_defs_unused_by()` in validators/orphan_cleanup.py, `_extract_decorator_phrases()` |
| 27 | PR #181 | The PR said "All checks have passed" while Agent 4 had not run the newest commit | A workflow-level concurrency group hides a queued run: GitHub shows no check for it | The group moved to the test job, so the waiting run is listed as pending | `.github/workflows/agent4_runner.yml` |
| 28 | PR #181 | A hidden confirmation blamed signed-in state, then a blocked font | Nothing recorded whether the action's request was made or answered; the first fix counted static resources | Failures list the page's action requests (XHR, fetch, navigation) and their outcome | `watch_network()` in pages/base_page.py, core/failure_diagnosis.py |
| 29 | PR #182 | Agent 2's repair loop stalled on an `is_<x>_absent()` predicate and the run failed | Two gates disagreed: the predicate rule demanded a presence wait (is_showing) for an absence question, which the absence rule rejects | `BasePage.is_gone()` - the absence wait; predicate rule, absence rule, repair hint and prompt all name it | `pages/base_page.py`, validators/method_resolution_validator.py |
| 30 | A3 retry PR | A retry's context update was skipped silently | The 'already proposed' check trusted comment history; a clean-up deleted the undo comment and kept the closed PR's marker | A marker that opened a PR stands only while that PR is open | `_already_proposed()` in core/context_update.py |
| 31 | A3 retry PR | The change story's own new test failed with 'resolved to 2 elements' | The control was drawn twice inside one card (card + hover overlay); click_in_row clicked the pair | click_in_row clicks the visible copy | `BasePage.click_in_row()` |
| 32 | A3 retry PR | Agent 1 followed the story over the context notes only by luck of wording | No rule said which wins; the notes describe the app before the change | Both Agent 1 prompts: the story is the intended behaviour | `prompts/agent1_*.md` |
| 33 | Agent 0 quality PR | A journey story put 10 existing test cases up for review | The model listed every element the story USES as a change seed, and "review" accepted overlap | Using is not changing: a new_behaviour story seeds nothing (in code); review must name what becomes different | `validate_requirement_seeds()`, `prompts/agent0_seeds.md`, `prompts/agent0_adjudicate.md` |
| 34 | Agent 1 rule PR | Agent 1 rejected a draft twice for following the rule's own advice | The persistent-state rule counted "no row for '<item>'" as a row count, while its remedy asked for exactly that relative absence | Absence of a NAMED entry is relative; bare "no rows" / "no other rows" stay absolute; a test proves the remedy's example passes the rule | `core/test_case_rules.py` |
| 35 | Agent 1 rule, generic | #187 accepted named absence only after listed words (for, of, named ...) | A word list judges phrasing, not meaning: "no row any more for 'X'" was still rejected | "No row(s)" is relative when its clause names an entry the test itself uses (a quoted value or a test-data value), in any wording | `_absence_of_a_named_entry()` in core/test_case_rules.py |
| 36 | Agent 2 step meaning PR | A new story's Then step failed in the browser while every older test passed | A re-defined step phrase asserted an extra, unstated state (the search-results view) that its own empty-search scenario does not have | A phrase already defined elsewhere must assert no more than that definition; a Then step asserts exactly its sentence | `validate_reused_steps_keep_their_meaning()`, prompt rule 5 |
| 37 | Agent 2 markers | Two JIRA lines on every generated scenario | The model's bare `# JIRA: KEY` is not a marker (no hash), so the real one was inserted beside it | Complete the bare line in place | `_bare_key_comment_above()` |

### Gates must agree with each other

Each validator is tested on its own, and that is not enough: in A3 two of them
gave the model opposite instructions for one absence check, so no rewrite
could pass and Agent 2 failed with every individual test green.
`tests/unit/test_gate_remedies_agree.py` runs the real Agent 2 gate on the
canonical shape of each common concern (presence check, absence check) and on
each known wrong shape, and requires every remedy a gate names to pass the
whole gate. **When you add a validator or change a remedy, add its canonical
shape and its wrong-to-right pair there.**

### Why not runtime learning (RAG over past failures, fine-tuning, etc.)?

Considered and deliberately rejected for now:

1. **Injecting a failure log into every prompt** costs tokens on every run for
   failures that may never recur; prompt rules cost those tokens too but are
   curated, deduplicated, and phrased as instructions rather than history.
2. **Fine-tuning** requires training data volume we don't have and freezes
   lessons into a model we can't inspect or diff.
3. **A vector DB of failures** adds infrastructure for what is currently a
   25-row table.

The validator + repair-loop combination gives *runtime* self-correction within
a single run (the LLM sees its own errors and fixes them), while this catalog +
prompt rules give *cross-run* permanence. If failure volume grows to where
manual curation doesn't scale, revisit: the natural next step is auto-appending
repair-loop failures to a structured log and periodically distilling them into
prompt rules.