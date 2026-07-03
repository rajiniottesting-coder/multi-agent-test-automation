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
| 14 catalogued failures → prompt rules | **Prompt engineering as institutional memory** | docs/LESSONS_LEARNED.md, prompts v12–v18 |
| Human must approve before code gen and before merge | **Human-in-the-loop (HITL)** | `human-approved` label + PR review |
| SHA-256 hash markers to detect changed inputs | **Content-addressable change detection** (not ML, but ask-worthy) | `# JIRA: KEY (hash: xxx)` markers |

## 3. Concepts NOT used — and the honest reason

| Concept | Why not here |
|---|---|
| **LangChain / LangGraph / CrewAI** | Raw API + custom orchestration gives full control and no framework churn; our "graph" is the Jira label machine, which is externally observable and survives process death — an in-memory graph doesn't. |
| **Vector DB / embeddings / semantic RAG** | Dedup is exact-title matching on ~dozens of scenarios; page-object retrieval is AST-based and exact. Embeddings would add infra and fuzziness where we need precision. |
| **Fine-tuning** | Failure modes were fixable with prompt rules (see LESSONS_LEARNED.md); fine-tuning freezes behavior into an uninspectable artifact. |
| **Runtime memory / learning loop** | Lessons are curated into prompts at development time — zero marginal token cost. See LESSONS_LEARNED.md §"Why not runtime learning". |
| **Multi-model routing** | One model keeps behavior predictable; the LLM client is a single swap point if we ever route (e.g., cheap model for Agent 5 summaries). |
| **Evals / benchmark harness** | Partially covered: 96 unit tests pin validator behavior; the real "eval" is Agent 4 running the generated tests. A dedicated prompt-regression eval set is a fair future item. |

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
A: Two mechanisms. Within a run: the repair loop (validator errors → retry). Across runs: a curated failure catalog (docs/LESSONS_LEARNED.md, 14 entries) distilled into prompt rules and validators — permanent, token-free, version-controlled. Deliberately not a runtime memory store; see the catalog for the trade-off analysis.

**Q: What does a run cost and how is cost bounded?**
A: ~$0.10–0.30 of LLM per Agent 2 story. `max_stories_per_run: 2` caps blast radius per cron tick; the human-approval gate stops accidental mass processing.

**Q: How would this scale to 50 stories a sprint?**
A: Raise the per-run cap, or parallelize — each story is independent (own branch, own PR, no shared state). The bottleneck becomes human review of PRs, which is by design.

**Q: What's the weakest part of the system?**
A: Honest answers impress: (1) `ai-update` can't add new page-object methods (documented limitation — use `ai-regenerate`), (2) dedup is title-based, so a reworded duplicate slips through, (3) no dedicated prompt-regression eval suite yet.
