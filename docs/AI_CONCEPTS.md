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
| **Input** | Label state machine — LLM only ever sees stories a human explicitly marked `ai-ready` / `human-approved`. No arbitrary input reaches the model. | config.yaml selection blocks + JQL |
| **Output schema** | Structured outputs via Pydantic + function-calling. Malformed JSON is impossible to act on — it raises before any side effect. | `LLMClient.invoke_structured()` + schemas.py |
| **Output content** | Six validators: filename consistency, feature structure, step coverage, path policy, import resolution, method resolution. Invalid code never reaches a commit. | gherkin_analyzer.py, agent2_coder.py, import_validator.py, method_resolution_validator.py |
| **Action / blast radius** | Path policy (reserved files can NEVER be written; extendable files can never be wiped), `max_stories_per_run: 2` cap, human-approval gate before any code gen, PR review before any merge, one-shot label consumption, branch protection on main. | `validate_paths_against_policy()`, config caps, GitHub branch rules |

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
PR review (a human reads every diff before merge).

---

## 2. Concepts actually used (know these cold for a demo)

| Concept | Industry name | Where in this repo |
|---|---|---|
| Multiple specialized agents with durable handoffs | **Multi-agent architecture / agentic pipeline** | 5 agents; Jira labels + GitHub as the shared state |
| Labels controlling triggering, idempotency, one-shot actions | **Agent state machine / orchestration** (what LangGraph models in memory, we model in Jira) | config.yaml selection blocks |
| Plan first, then generate per-file | **Prompt chaining / decomposition** (Plan-and-Execute pattern) | `build_plan()` → `generate_file_content()` loop |
| Pydantic-enforced JSON via function calling | **Structured outputs** | `invoke_structured()`, schemas.py |
| Validators feed errors back to the LLM for retry | **Reflexion / self-correction loop** | `_attempt_step_coverage_repair()`, max 4 retries |
| Already-generated method signatures injected into later prompts | **Context injection (RAG-style, in-run retrieval)** | `_build_sibling_page_object_context()` — AST-extracted, not embeddings |
| One gold-standard example the LLM mimics | **Few-shot prompting / reference-based generation** | reference_files in config.yaml |
| 15 catalogued failures → prompt rules + validators | **Prompt engineering as institutional memory** | the "Lessons learned" section below, prompts v12–v18 |
| Human must approve before code gen and before merge | **Human-in-the-loop (HITL)** | `human-approved` label + PR review |
| SHA-256 hash markers to detect changed inputs | **Content-addressable change detection** (not ML, but ask-worthy) | `# JIRA: KEY (hash: xxx)` markers |

## 3. Concepts NOT used — and the honest reason

| Concept | Why not here |
|---|---|
| **LangChain / LangGraph / CrewAI** | Raw API + custom orchestration gives full control and no framework churn; our "graph" is the Jira label machine, which is externally observable and survives process death — an in-memory graph doesn't. |
| **Vector DB / embeddings / semantic RAG** | Dedup is exact-title matching on ~dozens of scenarios; page-object retrieval is AST-based and exact. Embeddings would add infra and fuzziness where we need precision. |
| **Fine-tuning** | Failure modes were fixable with prompt rules (see the "Lessons learned" section below); fine-tuning freezes behavior into an uninspectable artifact. |
| **Runtime memory / learning loop** | Lessons are curated into prompts at development time — zero marginal token cost. see "Why not runtime learning" in the Lessons learned section below. |
| **Multi-model routing** | One model keeps behavior predictable; the LLM client is a single swap point if we ever route (e.g., cheap model for Agent 5 summaries). |
| **Evals / benchmark harness** | Partially covered: 259 unit tests pin validator behavior; the real "eval" is Agent 4 running the generated tests. A dedicated prompt-regression eval set is a fair future item. |

## 4. Demo Q&A — questions you should expect

**Q: Why five agents instead of one big agent?**
A: Context-window economics, natural human checkpoints (approve test cases before code), and durability — every agent's output is persisted (Jira issue, commit, PR comment) so a crash loses nothing. One mega-agent would lose its place.

**Q: How do agents communicate without a message bus?**
A: They don't talk to each other at all. Each reads state from Jira/GitHub and writes state back. The Jira label set IS the message. This makes the whole pipeline observable from the Jira board and recoverable from any point.

**Q: What stops the LLM from hallucinating code that doesn't run?**
A: Six validators + a repair loop before any commit, then Agent 4 actually executes the tests, then a human reviews the PR. Three independent nets.

**Q: What happens when the LLM output fails validation?**
A: Repairable categories (step coverage) go through the Reflexion loop — the exact validator errors are fed back and only the broken file is regenerated, up to 4 times. Non-repairable failures abort the run with the LLM output logged; no partial commits, no PR.

**Q: How do you prevent the agent from modifying critical files?**
A: Path policy validator. Reserved paths (reference files) can never appear in a plan; extendable paths can be appended to but never recreated. This is checked on the PLAN, before any generation happens.

**Q: How does it handle a Test Case being edited or deleted after code exists?**
A: Hash markers. Every scenario carries `# JIRA: KEY (hash: 8char)` — SHA-256 of the Jira description. Edited → hash mismatch → surgical regeneration of just that scenario (`ai-update`). Deleted → orphan key → scenario removed, dead page-object methods detected via AST and commented out with `# AI-ORPHAN:` banners.

**Q: Prompt injection — what if someone puts instructions in a Jira ticket?**
A: Human-approval gate means a human reads the story and generated test cases before the coder runs; path policy caps what a steered model could touch; PR review catches anything that gets through. We treat ticket text as data, but the real defense is that no output reaches production without two human checkpoints.

**Q: Why no LangChain?**
A: We use the same underlying patterns (chains, structured output, retries) directly against the API. The orchestration state lives in Jira, which beats in-memory graphs for durability and observability. Understanding the internals was also the point of the project.

**Q: How does it learn from mistakes?**
A: Two mechanisms. Within a run: the repair loop (validator errors → retry). Across runs: a curated failure catalog (the "Lessons learned" section below, 15 entries) distilled into prompt rules and validators — permanent, token-free, version-controlled. Deliberately not a runtime memory store; see the catalog for the trade-off analysis.

**Q: What does a run cost and how is cost bounded?**
A: Measured, not estimated — and tokens and cost are tracked separately. Every LLM call records API-reported token usage (`agents/llm_client.py`); each story run ends with two log lines: `LLM TOKEN USAGE` (exact counts) and `LLM COST` (input + output cost from the `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M` repo variables). For the full story cost, every LLM-using agent posts a `[LLM-USAGE]` comment to the story, and Agent 5 aggregates them into an "End-to-end LLM usage & cost" table in its final report (`agents/usage_ledger.py`) — the actual measured cost of Agent 1 + Agent 2 + Agent 3 + Agent 5 for that story in one place. Cost scales with test-case count and repair-loop retries on top of a fixed prompt-overhead floor. Bounding is separate from measurement: `max_stories_per_run: 2` caps blast radius per cron tick; the human-approval gate stops accidental mass processing.

**Q: How would this scale to 50 stories a sprint?**
A: Raise the per-run cap, or parallelize — each story is independent (own branch, own PR, no shared state). The bottleneck becomes human review of PRs, which is by design.

**Q: What's the weakest part of the system?**
A: Honest answers impress: (1) `ai-update` can't add new page-object methods (documented limitation — use `ai-regenerate`), (2) dedup is title-based, so a reworded duplicate slips through, (3) no dedicated prompt-regression eval suite yet.

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
| 5 | v12 | Stage 1 plan JSON parse failures (markdown fences, trailing prose) | Free-text JSON is unreliable | Structured output: Pydantic schema + function-calling mode | `LLMClient.invoke_structured()` |
| 6 | v12e | Code extraction failed when LLM emitted 6-backtick fences | Model occasionally doubles fence characters | Normalize 4+ backticks to 3 before extraction | `extract_code_from_response()` in agent2_coder.py |
| 7 | v15 | Validator rejected valid cross-file step reuse (step defined in another file) | Validator only looked at the paired step-def file | Cross-file awareness: check pre-existing step-def files on disk too | `validate_step_definitions_complete()` |
| 8 | v17 | `[float(p.replace("$",...)) for p in prices]` when method already returned `list[float]` → AttributeError | LLM ignored declared return types | Type-contract awareness prompt rule | prompts/agent2_coder_generate.md §Type contract awareness |
| 9 | v17 | Invented `.active_option` CSS class on native `<select>` → selector never matched | LLM hallucinated framework-specific DOM patterns | Locator discipline prompt rule (`input_value()` / `evaluate()`) | prompts/agent2_coder_generate.md §Locator discipline |
| 10 | v18 | `@then("I should be on the inventory page")` vs feature's "redirected to the inventory page" → StepDefinitionNotFoundError | LLM paraphrased instead of exact-matching | Exact phrase matching rule with examples | prompts/agent2_coder_generate.md §Step 2 |
| 11 | v18 | `parsers.parse('sort by {key}')` captured quotes into the variable → comparisons always failed | Quote-placement subtlety in `parse` templates | parsers.parse quote-handling rule (`"{value}"` vs `{value}`) | prompts/agent2_coder_generate.md §Step 3 |
| 12 | v18 | LLM re-invented dropdown/wait patterns differently every run → inconsistent, sometimes broken | No shared primitives to call | 10 generic BasePage helpers; prompt lists them | pages/base_page.py + prompt §BasePage helpers |
| 13 | May 2026 | Deleted Jira Test Cases left dead page-object methods forever | ai-update preserves page objects by design | Orphan detection: AST analysis, comment-out with `# AI-ORPHAN:` banners | agents/orphan_cleanup.py |
| 14 | May 2026 | Scan picked up stories from old sprints | JQL had no sprint clause | Sprint scoping: `sprint: "auto"` resolves active sprint via JIRA_BOARD_ID | agents/jira_client.py `get_active_sprint_name()` |
| 15 | SCRUM-54 | A new login-adjacent feature re-declared `@given("I am on the SauceDemo login page")`, already defined in the reference `test_login.py` → pytest-bdd registers steps globally across the package, so the duplicate collides at collection time (Agent 3 flagged it) | LLM re-declares common steps (navigation, login) in the new file instead of reusing the reference's existing ones — it doesn't know they're already registered package-wide | (a) prompt rule: reuse existing steps, never re-declare; (b) cross-file duplicate validator — narrowly flags only genuine (keyword, parser_type, phrase) collisions across step-def files incl. the reference | `validate_no_duplicate_step_definitions()` in gherkin_analyzer.py + prompts/agent2_coder_generate.md §rule 13 |

### Why not runtime learning (RAG over past failures, fine-tuning, etc.)?

Considered and deliberately rejected for now:

1. **Injecting a failure log into every prompt** costs tokens on every run for
   failures that may never recur; prompt rules cost those tokens too but are
   curated, deduplicated, and phrased as instructions rather than history.
2. **Fine-tuning** requires training data volume we don't have and freezes
   lessons into a model we can't inspect or diff.
3. **A vector DB of failures** adds infrastructure for what is currently a
   14-row table.

The validator + repair-loop combination gives *runtime* self-correction within
a single run (the LLM sees its own errors and fixes them), while this catalog +
prompt rules give *cross-run* permanence. If failure volume grows to where
manual curation doesn't scale, revisit: the natural next step is auto-appending
repair-loop failures to a structured log and periodically distilling them into
prompt rules.