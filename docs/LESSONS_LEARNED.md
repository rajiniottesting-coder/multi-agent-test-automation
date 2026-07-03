# Lessons Learned — LLM Failure Catalog

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

## Why not runtime learning (RAG over past failures, fine-tuning, etc.)?

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
