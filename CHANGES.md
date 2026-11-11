# CHANGES

This document records substantive changes to the framework in reverse-chronological order.

---

## November 2026 — a review fix's new or changed steps pass the step fidelity audit (#443)

**Why:** found in validation Run L (11 Nov, PR #435, review-fix run 43021957053). A `/fix` asked to check that the signup form is shown before it is submitted; the fix added the step and checked it with the page's "loaded" reader, which reads the other form, because the reserved page object has no reader for the signup form. Every rule passed and it was pushed; only Agent 3 noticed.

- `agents/agent2_review_fix._new_stand_ins`: the step fidelity audit (`validators/step_fidelity`) over the steps the fix added or whose code it changed; a step left as it was is not blamed on the fix. A stand-in refuses the batch - nothing is pushed and the summary names the step
- Tests in `test_step_fidelity.py`; TEST_TRACK E158. Not tested live yet: E158

---

## November 2026 — runs that cannot be read judge no workflow; a refused App token names its secret (#438)

**Why:** found in validation window L (11 Nov). With a refused token (health run 43016854504) the GitHub adapter returned no runs for every workflow, and the check read that as "no scheduled run started": five workflow-not-starting alerts opened. The same empty list resolves a real workflow-failing alert as "no longer failing". With a deleted App key (health run 43018090056) the job stopped at Agent identity with only GitHub's "A JSON web token could not be decoded".

- `integrations/repo_host.get_workflow_runs(strict=)`: with `strict` an adapter raises instead of returning `[]`; `GitHubClient` does. `core/health_checks._runs` asks for it, so a workflow whose runs cannot be read is not judged (an adapter without `strict` is read as before)
- `.github/actions/agent-identity`: when the App's token is refused, an error says the job writes nothing, never falls back to `GH_PAT`, and that `GH_APP_PRIVATE_KEY` (or `GH_APP_CLIENT_ID`) is the secret to fix
- Tests in `test_run_c_findings.py`, `test_agent_identity.py`; TEST_TRACK E156, E157. Not tested live yet: E156, E157

---

## November 2026 — a shortened refusal reason never ends inside a code span (#436)

**Why:** found live checking E154 (11 Nov, SCRUM-408 blocked comment 13796): each reason is cut at a fixed length, and a cut inside a code span left an unclosed backtick, shown literally.

- `core/blocked._short` cuts before an unclosed code span
- Test in `test_agent5_scope_and_markup.py`; TEST_TRACK E155. Not tested live yet: E155

---

## November 2026 — a refused story names a reserved page object's missing method; Markdown notices reach Jira rendered (#433)

**Why:** found live in validation Run L (11 Nov, SCRUM-408, Agent 2 run 42984931248). The steps needed `get_signup_error()` on the reserved `LoginPage`; the repair stood the login error in for it, and the blocked comment (13792) named only the stand-in, advising an inventory element the inventory already had. The same comment quoted the step pattern `"(?P<expected_message>[^"]*)"`, and Jira drew a broken image and bold text from it: comments go to REST v2, which reads wiki markup, while most of the agents' notices are Markdown posted as written (the coverage comments on SCRUM-293 showed `*KEY*` and backticks literally).

- `agents/agent2_coder._attempt_step_coverage_repair(reserved_needs=)` records each method a reserved page object lacks (as F49 records missing elements); a refusal carries them first. `core/blocked`: the reserved-page advice comes before the stand-in advice; `reserved_capabilities` is public
- `integrations.tracker.add_markdown_comment`: renders through the tracker's `render_markdown` capability and posts; used by the blocked, waiting, budget-hold, not-selected, coverage, Agent 1 coverage and stopped, and update-stopped notices. Comments written in wiki markup keep `add_comment`
- `integrations/jira_markup`: a code span escapes the characters wiki markup reads as formatting and writes a backslash as `&#92;`
- Tests in `test_run_c_findings.py`, `test_agent5_scope_and_markup.py`; TEST_TRACK E153, E154. Not tested live yet: E153, E154

---

## November 2026 — a file is not repaired on feedback a page-object repair just answered (#428)

**Why:** found re-checking validation item E90 against its runs (Agent 2 run 42825326200, 10 Nov, SCRUM-381): a committed page object joined the batch and its repair added the six methods the steps call - but the step definitions' feedback, computed before that repair, still said the class "does not define" them and offered other names. The repair moved the calls to a reserved page object, the error count rose and the story was refused as "not converging".

- `agents/agent2_coder._attempt_step_coverage_repair` repairs page objects before the files that call them (`_page_objects_first`), and drops a later file's method-resolution items that a page-object repair of the same attempt now answers (`_methods_defined`, `_still_missing`); a file left with none is not repaired - the next attempt validates the code as it is
- Tests in `test_run_c_findings.py` (the loop test fails without the change); TEST_TRACK E152. Not tested live yet: E152

---

## November 2026 — the coverage audit reads a section checked through what it shows (#427)

**Why:** seen live on validation item E103 (11 Nov, SCRUM-293 regenerated, as on 9 Nov): a scenario that checks the feedback email link was audited as not checking "the Feedback for Us section ... showing an email address". The rule that a part checked shows its element named lists only.

- `prompts/agent2_coverage_audit.md`: a link, text or field checked inside a section checks that the section is shown with it, even when the step does not name the section (a generic example)
- Test in `test_run_c_findings.py`; TEST_TRACK E151. Not tested live yet: E151 (a model's reading - the note still asks a person to check the scenario first)

---

## November 2026 — a context update rewrites a note quoted with its location in any shape (#427)

**Why:** found live on validation item E136 (11 Nov, SCRUM-406): the model quoted the inventory note as `pages.home.elements_notes.subscribe_success: <text>` - the notes block's line without its `- ` list marker - and the rewrite was listed under "Not applied: the passage is not in app_inventory/... verbatim". The earlier fix stripped only `- <where>: `.

- `core/context_update._NOTE_LINE` takes the location with or without the list marker or backticks; `_note_locations` - the location is stripped only when it names a note the file really has
- Tests in `test_context_scope.py`; TEST_TRACK E150. Not tested live yet: E150

---

## November 2026 — the step fidelity audit reads every step: each method's code shown once (#427)

**Why:** found live in validation Run K (11 Nov, SCRUM-293 regenerated by key, Agent 2 run 42969704566): the audit logged "Step fidelity: 1 step(s) not read - the prompt is full." Each step carried the code of every page-object method that runs for it, so the shared helpers of the page objects' base class (navigation, waits, locators) were repeated under all eight steps - 61,000 characters, 85% of it the same helpers - and the last step was never judged.

- `validators/step_fidelity.step_bindings` names the methods under each step and returns their code apart; `_prompt` shows each method's code once, after the steps
- Over the limit, methods of a class no step's page fixture names (inherited helpers) are cut to their signature and docstring before any step is left unread; only then are the last steps dropped, with the same warning
- `prompts/agent2_step_fidelity.md` says where the code is; tests in `test_step_fidelity.py`; TEST_TRACK E149. Not tested live yet: E149

---

## November 2026 — a cost row names every kind of run, a completed one included (#421)

**Why:** found live on validation item E147 (11 Nov, SCRUM-403): one failed and one successful Agent 1 run read `Agent 1 (Test Designer): failed | 2` in the cost comment - as if both had failed. A run of no particular kind added nothing to the row's list.

- `core/usage_ledger.by_agent` counts such runs; `_label` lists them as `completed` beside the other kinds when the row's runs differ (`Agent 1 (Test Designer): completed, failed`); a row of one kind still reads as the agent alone
- Tests in `test_usage_ledger.py`; TEST_TRACK E148. Not tested live yet: E148

---

## November 2026 — a failed Agent 1 run is the same attempt: retrying it keeps its cost (#417)

**Why:** observation O3, left open earlier and seen again on 10 Nov (SCRUM-398): Agent 1 ran out of output room and wrote nothing; `ai-ready` added again posted `[LEDGER-RESET] story reprocessed from ai-ready`, and the failed run's cost dropped out of the story's total - a retry of a run that produced nothing is not a new attempt.

- `core/usage_ledger.has_usage(..., same_attempt_if_failed=...)`: failed runs of the named agents do not count as a previous attempt; `TEST_DESIGNER` names Agent 1's ledger entry
- `agents/agent1_analyst.py` passes its own failed runs; a successful draft, or any later agent's run (failed or not), still starts a new attempt; other callers unchanged
- GUIDE updated; tests in `test_a_series_open_items.py`; TEST_TRACK E147. Not tested live yet: E147

---

## November 2026 — every health alert is redacted where it is posted, and quotes a tracker error readably (#415)

**Why:** found live on validation item E31h (11 Nov, window J): the triage's `defects-not-written` alert quoted the tracker client's error whole - `response headers = {'Content-Type': ..., 'S...` - cut at 300 characters just before what could have been a `Set-Cookie` session value. `raise_alert` posted its body as given; only some callers redacted their text.

- `core/pipeline_health.raise_alert` / `resolve_alert`: the body is redacted where it is posted - every alert, whoever raises it
- `core/redaction.redact`: also the value of a credential-carrying HTTP header an error quotes (`Authorization`, `Cookie`, `Set-Cookie`, a `...-Token` header)
- `core/redaction.error_text`: `<Type>: HTTP <status>: <the server's message>` for an error that carries them, else the message without the client's header dump; whitespace collapsed, cut to a length. `core/defects` records refused writes with it
- GUIDE updated; tests in `test_alert_text.py`; TEST_TRACK E146 (and E38). Not tested live yet: E146

---

## November 2026 — Agent 3 logs what its review was shown (#412)

**Why:** validation item E34 (a review of a large change: docs shown as diffs, the changed-files section capped) could not be checked from a run - nothing said which files the reviewer saw in full and which only as a diff, so a review of a large change could not be read against its input.

- `agents/agent3_reviewer.format_changed_files_for_prompt` logs one line: how many changed files were shown in full, how many as their diff only (files not read while the tests run), and which went over the section's cap and were shown as their diff
- Tests in `test_review_prompt_budget.py`; TEST_TRACK E34

---

## November 2026 — a test re-run after a temporary HTTP error is never invisible (#410)

**Why:** found live on validation item E15 (11 Nov, throw-away PR T7): a test refused with HTTP 503 on its first attempt passed on the re-run - and the *Keep only the final attempt* step printed "no re-run tests". `scripts/collapse_junit_reruns.py` assumed the re-run plugin writes every attempt as its own testcase; pytest-rerunfailures 16 writes only the final one and nothing about the earlier attempts, so the re-run reached no reader of the report.

- `core/rerun_record.py` (a pytest plugin, registered by `tests/conftest.py`): counts the attempts pytest reports as `rerun` and puts a `reruns` property on the test's final testcase - whatever shape the plugin's report has
- `scripts/collapse_junit_reruns.py`: lists tests that already carry the property, beside those it collapses; nothing is rewritten when there is nothing to collapse
- GUIDE and TECHNICAL_DEEP_DIVE updated; tests in `test_outage_retry.py` (one runs the installed plugin end to end); TEST_TRACK E145. Not tested live yet: E145

---

## November 2026 — a full Agent 4 run started by hand takes turns and survives a merge, like the nightly one (#407)

**Why:** the owner asked why E30b/E30c had to wait for the nightly run rather than a manual one. Reading the workflow showed why - and a gap: a manual (`workflow_dispatch`) run on `main` shared the concurrency group of a push to `main`, whose `cancel-in-progress` is on, so any merge cancelled a person's full regression run part-way; and it did not take turns with pull requests' browser runs, which log in with the same test accounts (`scripts/e2e_turn.py`), so either could change the other's results.

- `.github/workflows/agent4_runner.yml`: a full run (nightly or by hand) is in group `agent4-full-<ref>`, never the branch's group a push cancels; the turn-taking step runs for `workflow_dispatch` too
- `scripts/e2e_turn.py`: `TURN_EVENTS` includes `workflow_dispatch`
- GUIDE and TECHNICAL_DEEP_DIVE updated; tests in `test_in_flight.py`, `test_defect_triage.py`; TEST_TRACK E144. Not tested live yet: E144

---

## November 2026 — the plan's own Skipped notes decide that nothing is left to code (#404)

**Why:** the live check of #403 (SCRUM-398 by key): the plan left all three test cases out again, but this time planned a feature file with no scenario instead of a note - so "no feature file planned" did not hold, Stage 2 generated it, and the coverage gate refused as before.

- `agents/agent2_coverage.skipped_by_plan`: a test case the plan's notes leave out in the plan's own form (`Skipped: <KEY> -- <reason>`). The story is refused before Stage 2 when every new approved test case is skipped that way, or no feature file is planned
- Tests in `test_step_fidelity.py`; TEST_TRACK E143

---

## November 2026 — a story the plan leaves out entirely costs no generation, and is told to add the elements (#403)

**Why:** found live on Run I: after the step-fidelity fix the plan correctly left out all of SCRUM-398's test cases (the side panel is not in the inventory) - and planned a note file explaining the skips, which Stage 2 then generated and the gate refused (the same happened to SCRUM-394 earlier that evening). The blocked comment then advised editing the test cases ("a test case asks for something this application cannot show"), when the remedy was adding the elements.

- `agents/agent2_coder.py`: when the plan leaves every new approved test case out and plans no feature file, the story is refused before Stage 2 (`Coverage gate failed ... nothing was generated`), with the plan's reasons and the blocked comment, as the coverage gate would after generating
- `core/blocked.py`: reasons that say "not in the app inventory" (the plan's Skipped format) get the add-the-element advice (`scripts.plan_inventory element` / `page`), or retire the test cases
- `prompts/agent2_coder_plan.md`: when every test case is left out, plan no files
- Tests in `test_step_fidelity.py`; TEST_TRACK E143. Not tested live yet: E143

---

## November 2026 — a step whose code checks another element is left out, not shipped (#402)

**Why:** found live on Run I (SCRUM-398's pull request): the story's side-panel list was not in the app inventory. The plan did not skip its test cases; the code read the main list's item names for "the side panel lists ...", opened an item's page by name for "I click ... in the side panel", and checked "the page loaded" for "the side panel is visible". Every gate passed - each step called real page-object methods on real keys - and the coverage audit (which reads the Gherkin, not the code) judged one of the three test cases fully checked.

- `validators/step_fidelity.py`: after the gate, one model call (`prompts/agent2_step_fidelity.md`) reads each step of the story's own step files beside its definition, the page-object methods that run for it and the inventory elements they read (with the inventory's notes), and names each step whose code acts on or checks a different element than the wording names. Setting `agents.agent2_coder.step_fidelity_audit` (on). A failed call changes nothing
- `validators/action_steps.leave_out_stand_ins` takes these errors too (and Then steps, and a step definition's pattern): the scenarios using a named step are left out and their test cases listed as not automated with the reason; a story left with nothing is refused (`Step fidelity gate failed`), and `core/blocked` names the element to add. Only the feature that would be emptied keeps its keys - before, one emptied feature dropped every left-out key of the run
- The plan and generation prompts say a key counts only when its name or note is the thing the test case names
- Found in the same run: a step followed by a data table passed the gate and failed every run with `StepDefinitionNotFoundError` - the pinned pytest-bdd (7.x) reads the lines under a step as part of its text. `validators/step_arguments.py` refuses a data table or doc string under a step (Examples tables are data, not step arguments) while the installed pytest-bdd is below 8; the generation prompt says to put values in the wording or an Examples table
- Tests in `test_step_fidelity.py`, `test_step_arguments.py`; TEST_TRACK E141, E142. Not tested live yet: E141, E142

---

## November 2026 — an unlimited budget is said in words, never "$inf"; Agent 1's output room is a setting (#395)

**Why:** found live: with both budgets set to `.inf` (owner's decision until the validation items are developed), the Pipeline health description read "$71.86 of the $inf daily budget". A project may lift a limit for a while; nothing a person reads should show the raw value.

- `core/spend_budget.unlimited` and `more_after_release`: an `.inf` limit is "no daily budget is set" in the health view, "No daily budget is set now." when a day alert closes, and "spend without a limit" in a hold's release text; the story cost line is left out when there is no story limit to measure against
- `config/config.yaml`: `budget.per_story_usd` and `per_day_usd` are `.inf` for now (restore 8 / 150 when the validation work is complete)
- Agent 1's output room is a setting, `agents.agent1_analyst.max_output_tokens` (12288, as before); a draft that runs out of it names that key - before, the stop said to change the code (`LLMClient(..., cap_setting=...)` names the key for any agent that reads its cap from config)
- Tests in `test_spend_budget.py` and `test_run_b_findings.py` (the cost-comment test in `test_comment_dedup.py` no longer depends on the shipped limit); TEST_TRACK E139, E140. Not tested live yet: E139, E140

---

## November 2026 — a new attempt starts on a fresh budget, without the old hold (#392)

**Why:** found live on Run H (validation window H2, per-story budget lowered): a change story held for an earlier attempt's spend was edited and sent back to Agent 0. Agent 0 records the attempt boundary only after its analysis, so the analysis itself ran on the held budget and was refused - the reset that would have restarted the budget never came. And a reset that did happen (Agent 1 re-processing a story) restarted the budget but left `budget-hold` on the story, so every selection kept skipping it.

- `agents/agent0_impact._restart_budget_for_a_new_attempt`: before analysing a change story that later agents already worked on (a new attempt), its budget starts from zero; the boundary is still recorded after the analysis, as before
- `core/usage_ledger.post_reset_to_story`: the reset also removes the hold label - the hold belonged to the attempt it stopped
- Tests in `test_spend_budget.py`; TEST_TRACK E138 (with E32e). Not tested live yet: E138

---

## November 2026 — an inventory note quoted with its line prefix is still rewritten; a flaky prediction says why it blocks (#389)

**Why:** two fidelity gaps found live on Run H.

- Context update (SCRUM-394's context-update pull request, its "Not applied" list): the model quoted an inventory note as the notes block shows it - `- pages.<page>.elements_notes.<key>: <text>` - and the rewrite was dropped as "not in ... verbatim" although the note was there. `core/context_update._replace_passage` now retries without that line prefix when old and new carry the same one (`_NOTE_LINE`); selectors stay untouchable
- Agent 3 (a throw-away PR whose run was red for another reason): a predicted scenario that passed only on the retry kept blocking - correctly - but only a green run logged why. A red run now logs "passed only on the retry (flaky) - its predicted failure keeps blocking" too
- A run by key printed no "not automated" line, which the scan's summary prints (SCRUM-379's run by key): the by-key summary now lists the test cases left without a scenario
- Tests in `test_context_scope.py`, `test_review_scenario_evidence.py`, `test_blocked_story.py`; TEST_TRACK E136, E137. Not tested live yet: E136, E137

---

## November 2026 — every scan pass skips a story the gate refused on unchanged input (#386)

**Why:** found live on Run H: only the scan's normal pass skipped a story the gate had refused on unchanged input. A refused `ai-regenerate` story keeps its label, so every scan - including the one the hand-off starts after each run - generated it again, refused again, and posted another `[agent2:blocked]` comment: SCRUM-379 reached its $8 budget that way within the hour. `ai-update` never posted the comment at all, so a refused update could repeat the same way.

- `agents/agent2_coder.py`: the scan passes `skip_if_blocked` in every pass; `_refused_before()` is the one check for `run()` and `run_update()`; `run_update()` posts the `[agent2:blocked]` comment on a gate refusal, as `run()` does. A manual run always runs
- GUIDE (troubleshooting), TECHNICAL_DEEP_DIVE; tests in `test_blocked_story.py` (the test that pinned "only the normal pass skips" now pins every pass); TEST_TRACK E135. Not tested live yet: E135

---

## November 2026 — the scenarios that stand in for a missing control are left out, the rest coded (#385)

**Why:** after #384, SCRUM-379 run again (Run H): the plan still automated the test cases that click a control the inventory lacks, the gate refused the step that clicked nothing, and the whole story was refused - its third test case, which needs no missing control, included. The plan's skip is the model's judgement; this is the code's.

- `validators/action_steps.leave_out_stand_ins`, run in Agent 2 before the coverage step: scenarios using a step an `Action step error` names are taken out of the story's own feature, with the step functions only they used; each test case is named `Skipped: <KEY> -- <reason>` in the plan's notes, so the PR lists it under *Approved test cases not automated* with `[agent2:incomplete]` and `ai-incomplete` (E24a). Never a change story's splice into another story's files, never a Background step; a feature that would be left with no scenario is refused as before
- Checked on SCRUM-379's first PR: the two scroll-up scenarios go, the footer scenario stays, and the batch passes every repairable check
- Tests in `test_action_steps.py`; GUIDE; TEST_TRACK E134. Not tested live yet: E134

---

## November 2026 — a test case needing a control the inventory lacks is planned as skipped (#384)

**Why:** after #382, SCRUM-379 run again (Run H): the gate refused the step that clicked nothing, the model kept producing the control's outcome under another name, and the whole story was refused - its test case that needed no missing control included - with the generic "reword a test case" advice. The plan had automated the test case although the inventory has no key for the control it clicks.

- `prompts/agent2_coder_plan.md` decision step 3b: every control a test case clicks, presses or fills and every element it checks must have a key; one that does not makes it `Skipped: <KEY> -- needs <element> on <page>, not in the app inventory` (the PR's "not automated" list, E24a), never stood in for
- `core/blocked.py`: a refusal on an `Action step error` says it is almost always a control the inventory lacks, with the `plan_inventory element` command, or retire the test case so the others are coded
- Test in `test_blocked_story.py`; TEST_TRACK E133. Not tested live yet: E133

---

## November 2026 — a page has one page object (#383)

**Why:** found live on Run H (SCRUM-381): the story needed one more method on the top menu's page object, which is reserved. Instead of the reserved-method refusal (a person adds it), Agent 2 created a second, new page object for the same inventory page - its own names for behaviour the reserved one already has (a second "go to Contact Us"), and the reserved file's protection side-stepped. Only a new page object that resolved none of the page's elements was refused before.

- `validators/method_resolution_validator.validate_page_object_selectors`: a NEW page object whose `INVENTORY_PAGE` a committed page object already implements is a `Selector inventory error` naming that page object; when it is reserved, the error says to call the method on it and that a person adds it there (the step then meets the reserved-method refusal)
- `prompts/agent2_coder_plan.md`: a page has one page object; never plan a new one to get round a reserved one
- Checked against the page objects of the last 13 story PRs: no false positive; it flags SCRUM-381's
- Tests in `test_one_page_object_per_page.py`; GUIDE; TEST_TRACK E132. Not tested live yet: E132

---

## November 2026 — a step that says it clicks, clicks (#382)

**Why:** found live on Run H (SCRUM-379, its first pull request): the inventory had no key for an on-page control, and the generated step `When I click the <control>` called a page-object method that scrolled the window by script - the control's outcome - and clicked nothing. Every gate passed; the scenario would stay green with the control missing or broken. The coverage audit only noted, as the model's reading, that the control's visibility was unchecked.

- `validators/action_steps.validate_click_steps_click` (repair loop and final gate): a Given/When step worded as a click (click, press, tap) whose page-object calls make no click - read through the class's own methods and its base class - is an `Action step error`, routed to the step file; unreadable cases are left alone
- `prompts/agent2_coder_generate.md` rule 15: a missing element is left out with its reason, never stood in for by performing what it would do
- Checked against every click step of the last 13 story PRs (37 steps): no false positive; it flags SCRUM-379's step
- Tests in `test_action_steps.py`; GUIDE (gate list), AI_CONCEPTS #57; TEST_TRACK E131. Not tested live yet: E131
## November 2026 — a workflow younger than the schedule window is not judged (#375)

**Why:** found live right after #372: a throw-away scheduled workflow added minutes before the health check got a `workflow-not-starting` alert - "no scheduled run in the last 24 hours" of a workflow that had existed for 20 minutes. The same check logged "Could not read runs ... list index out of range" for it: slicing an empty paginated list of runs raised.

- `core/health_checks.schedule_findings`: no finding for a workflow the host first knew after the window's start (an open alert stays as it is)
- Repo host optional capability `workflow_created_at(file)` (`integrations/repo_host.py`); the GitHub adapter reads the workflow's creation time, and reads its runs with `islice` so a workflow with no runs is "no runs", not an error
- GUIDE alert table; tests in `test_run_c_findings.py`; TEST_TRACK E130. Not tested live yet: E130

---

## November 2026 — the health check closes every alert of a workflow that is gone (#372)

**Why:** a workflow alert closes when its workflow file is deleted or no longer scheduled - but only the `workflow-failing` alert did. Found on the health issue: two throw-away workflows deleted after validation cycle 1 still had open `workflow-not-starting` alerts, and nothing would ever close them.

- `scripts/pipeline_health_check.apply`: both workflow alerts (`workflow-failing:<file>`, `workflow-not-starting:<file>`) close as "no longer scheduled" when `<file>` is not among the scheduled workflows (`_workflow_alert_name`)
- GUIDE: the alert table gains its `workflow-not-starting:<file>` row (it had none)
- Test in `test_pipeline_health.py`; TEST_TRACK E129. Not tested live yet: E129

---

## November 2026 — a removed key is never added back, and the nightly summary names what it read as declared (#368)

**Why:** two findings of the E22 after-deployment run (a removal story's key declared `removed`, its selector reading gone, and a live element the crawl names the same):

- the nightly inventory update retired the key and then added the same name back with the live selector - one pull request that undid the story's declaration and its `REMOVED by` note;
- `Inventory Health` reported "every selector resolved to exactly one element" and `87 selector(s) resolve to exactly one element` while the removed key read zero (as declared), and with `--only-problems` no line anywhere showed it gone.

- `core/inventory_update.build_update`: the keys declared `removed` are read before the retirement; a new element with one of their names is refused with the reason (GUIDE, Inventory update table)
- `scripts/verify_locators`: the readings a declaration explains (gone, conditional, planned, a family) are collected per run; the summary counts them apart from the keys that resolve to one element and names each key declared removed and measured gone. `scripts/inventory_health_report`: the healthy sentence says the same
- Tests in `test_removed_elements.py`, `test_inventory_health_report.py`, `test_inventory_health_summary.py` (the healthy sentence of its reference script); TEST_TRACK E127, E128. Tested live 10 Nov: E127, E128 (evidence in TEST_TRACK)

---

## November 2026 — a signed-in scenario owns its starting state only if it clears it itself (#363)

**Why:** the code-generation gate's persistent-state rule decided per step-definition file whether the state is owned: one step anywhere in the file that clears it (or asks for a fresh identity) exempted every scenario. Found live on R2: a review fix removed one scenario's clearing step, and the gate passed that scenario - signed in as the shared account - asserting "exactly 1 row", because another scenario in the file removes every product.

- `validators/method_resolution_validator._scenarios_not_owning_state`: with the feature at hand (the batch, else `features/<stem>.feature`), ownership is judged per scenario, Background included; the error names the scenarios that assert without clearing. An unreadable feature keeps the file-level answer; anonymous files stay exempt
- Tests in `test_persistent_state_assertions.py`; TEST_TRACK E126. Tested live 10 Nov: E126 (evidence in TEST_TRACK)

---

## November 2026 — each kind of splice correction gets its own retry (#359)

**Why:** the splice's step writer had two answers in all, shared by three kinds of correction (a step answered "needs a page-object method", an unknown method, a gate rule broken - #358). Live on a Run G change story, the needs-a-method retry took the only second answer and a broken absence rule reached the final gate uncorrected.

- `agents/agent2_coder._splice_step_defs_incremental`: one correction per kind, at most four answers; a second failure of a kind ends as before
- Test in `test_splice_grounding.py`; TEST_TRACK E125 covers it. Tested live 10 Nov: E125 (evidence in TEST_TRACK)

---

## November 2026 — the splice runs the repair loop's rules on the step functions it adds (#358)

**Why:** a change story's splice runs after Agent 2's repair loop and checked its new step functions only for unknown page-object methods; any other rule they broke reached the final gate unrepaired. Found live on a Run G change story: a spliced absence step that asserted nothing refused the story "after the repair loop exhausted its attempts" - attempts it had never been given (R2).

- `agents/agent2_coder._new_repairable_errors`: the repair loop's collector, run on the step file before and after the splice (feature and page objects as context); the errors the splice added are fed back to the writer once; still broken, the final gate decides
- Tests in `test_splice_grounding.py` (`test_step_def_splicing.py`'s tier tests stub the rules); TEST_TRACK E125. Tested live 10 Nov: E125 (evidence in TEST_TRACK)

---

## November 2026 — the literal-selector scan never reads prose inside a docstring (#357)

**Why:** found live on a Run G change story's retry: the page-object literal-selector scan reads source lines and skipped only lines starting with a quote, `#` or `*`. A line in the middle of the page object's docstring (a quoted address followed by a period, and later an apostrophe) matched as a quoted selector, and the final gate refused a story whose code held none.

- `validators/method_resolution_validator._string_statement_lines`: every line of a docstring or bare string statement (AST); the generation gate and the committed-tree scan (`test_page_object_selectors.py`) both skip them
- Test in `test_page_object_selectors.py`; TEST_TRACK E124. Tested live 10 Nov: E124 (evidence in TEST_TRACK)

---

## November 2026 — a named entry in backticks is a named entry (#356)

**Why:** found live on R3. Agent 1's persistent-state rule treats "no row" as relative when its clause names an entry in quotes; the quote pattern knew straight and curly quotes, not backticks. A signed-in draft's "No row for \`<item>\` is present in the cart" - the relative absence the remedy asks for - was refused twice and the story handed back.

- `core/test_case_rules._QUOTED`: backticks count as quotes
- Test in `test_test_case_rules.py`; TEST_TRACK E123. Tested live 10 Nov: E123 (evidence in TEST_TRACK)

---

## November 2026 — one story by key is settled only when the scan would settle it (#354)

**Why:** found live on R6. A change story retried after its undo (`impact-check`, nothing coded yet) was run by key; `reconcile_one` sent every story that was not `impact-applied` to the new-story path, which set it back for the previous attempt's closed pull request - a "story-reset" comment for an attempt reconcile had already undone. The scan selects only coded stories that are not a change undone.

- `core/impact_reconcile.reconcile_one`: the change path when `impact-applied`; the new-story path when it carries the completion label and is not `impact-reverted`; otherwise left alone
- GUIDE (Reconcile)
- Test in `test_reconcile_new_story.py`; TEST_TRACK E122. Tested live 10 Nov: E122 (evidence in TEST_TRACK)

---

## November 2026 — the splice routing allows two rounds per owner file (#352)

**Why:** live after #351, the first owner's step file needed two page-object repairs (its second answer asked for one more method); that used the second file's only round, and the second file's single stop was refused.

- `agents/agent2_coder.run`: two routing rounds per owner file, plus one; the same stop twice is still refused
- Test in `test_splice_grounding.py`; TEST_TRACK E121 covers it. Tested live 10 Nov: E121 (evidence in TEST_TRACK)

---

## November 2026 — an unmet splice step names its page object; each new stop is routed (#351)

**Why:** live after #350: the routing repaired the run's page object and the first owner's step file spliced; the second owner's file then needed a check on another page - a committed page object the run had not touched - and #348's single, run-only route could not reach it.

- `agents/agent2_coder`: the step writer names the page-object class that shows an unmet check (`needs a page-object method: <PageObjectClass>: <check>`); `_extend_page_objects_for_splice` sends each check to that class's file - one the run wrote, or a committed one that is not reserved, which joins the batch - and to the run's own page objects when none is named
- `run()` routes each new stop again, at most one round per owner file; the same stop twice is refused
- Tests in `test_splice_grounding.py`; TEST_TRACK E121. Tested live 10 Nov: E121 (evidence in TEST_TRACK)

---

## November 2026 — an agent started with python -m is one module, however it is imported (#350)

**Why:** every workflow starts Agent 2 as `python -m agents.agent2_coder`, so the file runs as `__main__`; `agents/agent2_impact.py` and several core modules import `agents.agent2_coder` by name, which loaded a second copy with its own classes and module state. Found live: the change-story splice raised the copy's `SpliceNeedsPageMethods`, `run()`'s `except` named the `__main__` class, and #348's routing to the page-object repair never ran.

- `agents/agent2_coder.py`, `agents/agent0_impact.py`: started as `__main__`, the module registers itself under its own name before anything imports it
- `tests/unit/test_entry_module_single_copy.py`: every module a workflow starts with `python -m` and another module imports by name must do so; a subprocess test starts Agent 2 as `__main__` and checks the named import is the same module (it fails without the alias)
- TEST_TRACK E120 now covers this fix too. Tested live 10 Nov: E120 (evidence in TEST_TRACK)

---

## November 2026 — a change story's unmet splice step goes back to the page-object repair (#348)

**Why:** the change-story splice runs after Agent 2's repair loop. A method the revised steps need that the plan did not foresee had no way in, and the splice refused the story - an error never routed to the repair (R2). Found live on a Run G change story after #347's retry: one revised step ("a new browser tab or window should not be opened") had no method, and the plan had not asked for one.

- `agents/agent2_coder.SpliceNeedsPageMethods` (a `GateFailure`): raised by a change story's splice with the unmet checks
- `run()` routes it once to `_extend_page_objects_for_splice` - the page objects this run wrote, repaired with each check named (existing methods kept; a degraded answer discarded) - and splices again; still unmet, the story is refused as before
- Tests in `test_splice_grounding.py`; TEST_TRACK E120. Tested live 10 Nov: E120 (evidence in TEST_TRACK)

---

## November 2026 — a change story's splice is told the methods its run wrote before stopping (#347)

**Why:** found live on a Run G change story. Its run extended the page object with the methods its revised steps need (the plan said so), the splice's step writer still answered three steps "needs a page-object method", and the splice stopped on that first answer with the ai-update remedy ("add `ai-regenerate`") - a label a change story never has. Nothing reached a second attempt.

- `agents/agent2_coder._page_methods_written_in_run`: the methods the page objects written in this run add over their committed copies. When there are any, the writer is asked once more with them named; still unanswered, the stop names them and says to run Agent 2 again by key or reword the test case. An ai-update (no page object written) keeps its one-answer stop and remedy
- Tests in `test_splice_grounding.py`; TEST_TRACK E119. Tested live 10 Nov: E119 (evidence in TEST_TRACK)

---

## November 2026 — Inventory Health's multi_match note names only families measured thin; GUIDE re-analysis wording (#346)

**Why:** observation O13. Inventory Health's "declared multi_match not multiple right now" note listed every declared family on every page: the set it subtracted held only UNDECLARED ambiguous keys. Families measured with dozens of matches (the listing's cards, the test-case panels) were named, and on Run G's removed-element branch a key declared `removed` was named with "do NOT remove". Separately, the GUIDE said a re-analysis updates the report in place; it updates the open Impact Review in place and posts a new report whose second line is the delta.

- `scripts/verify_locators._verify_page`: the note names the declared families measured as one element, or none while declared conditional (`thin_family`)
- GUIDE (How a story is analysed, step 1)
- Test in `test_removed_elements.py`; TEST_TRACK E118. Tested live 10 Nov: E118 (evidence in TEST_TRACK)

---

## November 2026 — Agent 1 refuses absolute claims on a kept page only when the test signs in (#340)

**Why:** Agent 1's persistent-state rule refused every absolute claim ("only", "empty", "no rows", "exactly") on a `persistent_state` page, whether the test case signed in or not. The code-generation gate draws the line elsewhere on purpose: the state is kept against the signed-in user, and a scenario that never signs in opens a fresh browser context that starts with nothing. Found live on a Run G cart story: its criterion "emptying the only product shows the empty-cart message" was refused twice - every draft of it is absolute - and the story was handed back with no test case, although the anonymous scenario passes Agent 2's gate.

- `core/test_case_rules`: the absolute-claim check runs only for a test case that signs in (`_signs_in`: a shared account named, or a sign-in mentioned anywhere that is not negated); the refusal also offers not signing in. The signed-in quantity rule is unchanged
- `prompts/agent1_analyst.md`, `prompts/agent1_impact_aware.md`: the same line
- Tests in `test_test_case_rules.py` (existing cases now sign in explicitly and still fail); TEST_TRACK E117. Tested live 10 Nov: E117 (evidence in TEST_TRACK)

---

## November 2026 — context update: the REMOVED note is always written; a reworded passage is still rewritten (#339)

**Why:** two flaws in the change-story context update, found live on Run G's first hand-overs:
- **No REMOVED note.** A removed element was declared in the page's `removed` list, but its `REMOVED by <story>` note was left to the model's rewrite of the element's note. An element with no note had nothing to rewrite: the model aimed at the key's `multi_match` / `conditional` entries, both rewrites were dropped, and the key went out with no note.
- **A rewrite dropped after a wording change.** Wording replacements run first; the model copies each passage from the notes as they were, so a rewrite of a sentence the wording change had just edited no longer matched and was dropped as "not verbatim" - the part the story makes untrue stayed.

Changes:
- `core/context_update._declare_removed(..., story_key)`: the note starts `REMOVED by <story>` - a new note for an element without one, the old note kept after the marker, a note the model rewrote that way left as it is. `propose(..., story_key)`; the hand-over passes it
- `core/context_update._apply_rewrites`: a passage not found is tried again with the story's applied wording replacements (`_replace_passage`)
- GUIDE (Context update)
- Tests in `test_removed_elements.py`, `test_context_update.py`; TEST_TRACK E115, E116. Tested live 10 Nov: E115, E116 (evidence in TEST_TRACK)

---

## November 2026 — stale claims: a closed change story and a drift that is gone no longer block tests (#336)

**Why:** two Impact Reviews went on blocking tests in other change stories after nothing called for them, both found before Run G's change stories were analysed:
- **A closed change story.** The in-flight guard's list of open reviews and the hand-over's list of stories selected `impact-proposed` in any status. A change a person dropped (story closed, review left as it was) claimed its tests for good, and a Done review on it would still have been handed over.
- **A drift that is gone.** The nightly drift job returned before reaching the drift maintenance story when no test was affected, so a review opened for a drift since fixed (validation cycle 1's broken selectors) stayed open and "blocked" the Test Cases tests in every change story.

Changes:
- `agents/agent0_impact._proposed_selection`: `impact-proposed` and a status in `selection.allowed_statuses`; used by the claims and by the hand-over
- `agents/agent0_impact.settle_drift_story`: a night that measured pages and found no drift affecting a test supersedes the drift story's open review (`_supersede_open_review`, shared with `publish`), takes `impact-proposed` off and posts the night's report, so the same drift coming back is analysed again. A Done review and a night that measured no page are left alone
- GUIDE: the in-flight guard and the nightly drift trigger
- Tests in `test_change_in_progress.py`; TEST_TRACK E113, E114. Tested live 10 Nov: E113, E114 (evidence in TEST_TRACK)

---

## November 2026 — the context update names what it read (#335)

**Why:** the change-story context update reads only what the story's Components select (F-10), but nothing said what that was: the run log held neither the prompt nor a list, so a check of a run (E20) or the reviewer of the PR could not tell whether another Component's module was offered.

- `core/context_update.read_scope`: the notes modules and the inventory pages whose notes the rewrite call is shown, in words; logged before the model calls and written into the PR body (*Read for this update: ...*)
- GUIDE (Context update) says where to find it
- Tests in `test_context_scope.py`; TEST_TRACK E112. Tested live 10 Nov: E112 (evidence in TEST_TRACK)

---

## November 2026 — one open defect per test; flaky window 14 days; Agent 5 names a red unit run; Agent 3 flags removed scenarios of other stories (#328)

**Why:** findings of validation cycle 1 and the open observations:
- **Duplicate defects.** The triage kept one defect per test *and cause*. The cause is a heuristic reading, so the same problem reads differently on another night: one run raised four duplicates next to open defects of the same tests (SCRUM-349/350/351 beside 327/328/329).
- **Flaky window.** `flaky_tests.window_days` 30 kept a fixed flake on the health issue's table for a month.
- **O12.** Agent 5 wrote "All 1 tests passed" on a pull request whose check was red from the framework's unit tests.
- **L53.** A pull request removing another story's scenarios was flagged by no agent.

Changes:
- `core/defects`: a failure updates the open defect of its test and cause, else the open defect of its test (the newest not flagged passing). That defect takes the new cause and lists `Causes seen before`. A closed defect still makes the next failure a new one. F51's unflagging stays for defects raised before this change
- `flaky_tests.window_days` 14 (config, `core/ops_settings`, `core/flaky_tests`, GUIDE): about ten working days of nightly and PR runs, so a repeat flake is visible and a fixed one leaves the table in two weeks
- `agents/agent5_reporter`: when `junit-unit.xml` beside the app tests' report has failures, the comment opens with "Pull request check red: N of M framework unit tests failed"
- `agents/agent3_reviewer.removed_scenarios_of_others`: a marker removed by the diff and not added back, owned by another story (or by anyone, on a person's branch), becomes a `major` / `missing_coverage` finding. It is found by code, listed first, advisory
- Docs: every "one defect per test and cause" statement updated (config, GUIDE, TECHNICAL_DEEP_DIVE, README, VALIDATION L37 and F-22, `scripts/triage_failures`); VALIDATION's duplicate L49/L50 ids renumbered L53/L54
- Tests in `test_defect_triage.py`, `test_agent5_outside_failures.py`, `test_review_changed_lines_only.py`; TEST_TRACK E109-E111. Not tested live yet: E109, E110, E111

---

## November 2026 — a defect's test failing for another cause is no longer called passing (#326)

**Why:** the triage keeps one defect per test and cause. On main a test whose old defect was flagged `ai-defect-passing` ("suggest closing") failed again, but the diagnosis gave another cause. A new defect was raised (correct), and the old one went on suggesting it be closed while its test failed. Nothing pointed it to the new defect.

- `core/defects.triage`: when a test fails, an open defect of the same test under another cause loses `passing_label` and gets one comment naming the defect of this run ("not passing any more; if both describe one problem, close one of them"); reported in `failing_again`
- Tests in `test_defect_triage.py`; TEST_TRACK E108. Not tested live yet: E108

---

## November 2026 — one base URL for the tests, the agents and the application check (#324)

**Why:** a throw-away run that pointed `app_under_test.base_url` elsewhere still ran every E2E test against the live application. The tests (`tests/conftest.py`) read a top-level legacy `base_url`; the agents, the application check and the inventory tools read `app_under_test.base_url`. A project that edits only the documented key would run its tests against the previous application while the health check judges another. REUSE_FOR_NEW_PROJECT asked for both edits by hand.

- `tests/conftest.resolve_base_url`: `BASE_URL` env, then `app_under_test.base_url`, then a top-level `base_url` (older configs) - the order `scripts/app_probe.py` already used
- `config/config.yaml`: the legacy top-level `base_url` removed
- GUIDE and REUSE_FOR_NEW_PROJECT: one key to set; an old top-level one is to be deleted
- Tests in `test_app_health_and_retry.py`; TEST_TRACK E107. Not tested live yet: E107

---

## November 2026 — a story refused after its element was missing is told so (#319)

**Why:** a story needed an element the inventory did not have. The repair loop spent four attempts (about $0.80): each time the validator said the key was on no page, and the model deleted the page-object methods that used it. The step definitions still called them, and the story was refused for *method resolution*. The blocked comment blamed the model and the test case. #302 (F45) gave the missing **page** this treatment; a missing **element** had none.

- `validators/method_resolution_validator.elements_missing_from_inventory`: `page.key` for each element a page object uses that is on no inventory page (a near-miss spelling stays repairable)
- `agents/agent2_coder`: the repair loop records each missing element with the validator's message; it still repairs, since dropping the behaviour can leave a partial pull request. If the story is refused in the end, the refusal names the missing element(s) first, with the remaining errors after
- `core/blocked`: the blocked comment names the element(s) and gives the `scripts.plan_inventory element` command instead of blaming the test case
- Tests in `test_page_missing_from_inventory.py`; TEST_TRACK E106. Not tested live yet: E106

---

## November 2026 — the golden-rule guard sees issue keys, UI text and the app's name; the leaks it found are gone (#318)

**Why:** a review of this run's fixes against the golden rule found framework comments, unit tests and one agent prompt naming the application. The harvest-based guard (`test_no_framework_file_names_anything_the_application_coins`) did not see these, because it harvested only element keys, class names, selector fragments and file stems:
- the Jira project's issue keys (258 in 59 files)
- a page heading and other UI text quoted in selectors
- the app's host
- story history written in plain words (a page's sections, its headings)

- `tests/unit/test_committed_tree_resolves.py`: the guard also harvests the issue-key prefix from the markers of the application's own feature files, multi-word or address UI text quoted in inventory selectors, and the configured app name and host; a key matches only as `KEY-<number>`; "Test Cases" joins the framework's conventional vocabulary (the issue type Agent 1 creates); a test fails if the new sources stop being harvested
- Framework files: issue keys replaced by the neutral `PRJ-` (comments, docstrings, help text, fixtures; none was functional); story-history comments rewritten without the app's pages, sections or texts; the letter-case prompt example and its test use a neutral heading; a test that read the inventory by its file name reads it from `config.yaml`
- GUIDE, README and TECHNICAL_DEEP_DIVE examples use `PRJ-`; CHANGES, VALIDATION, TEST_TRACK, AI_CONCEPTS and DECISIONS keep their history
- TEST_TRACK E105. Not tested live yet: E105

---

## November 2026 — a story never regenerates another story's test files (#314)

**Why:** SCRUM-330 (a new story on the Test Cases page) was planned into the existing Test Cases feature file and its step definitions, which SCRUM-293 owns. Agent 2 writes whole files, so its pull request deleted both of SCRUM-293's scenarios and their steps. No gate, review or test run noticed: Agent 0 saw no affected test, Agent 3 approved, and the suite passed with fewer tests.

- `agents/agent2_coder._retarget_test_files_owned_elsewhere`: after the plan, a planned feature or step-definition file whose feature holds another story's scenarios (another `owner:`, a test case not this story's, or an unmarked scenario) is renamed for this story (stem + story key) before anything is generated; a story regenerating its own file keeps it
- Tests in `test_auto_extend_page_objects.py`; TEST_TRACK E104. Not tested live yet: E104

---

## November 2026 — the coverage audit reads implied checks; its note asks for a look first (#312)

**Why:** for SCRUM-293 the coverage audit (#298) reported that a scenario asserting "each test case title should be rendered as a clickable link" did not check "the page lists test cases". The note then told the person to add an inventory element. Asserting every item of a list already shows the list, so the finding was false and the advice wrong.

- `prompts/agent2_coverage_audit.md`: a step that asserts something of every item of a list, or of part of an element, checks that the list or element is shown; a step that acts on an element checks that it is there
- `agents/agent2_coverage.audit_partial`: the note says it is the model's reading - check the scenario first - before the inventory advice
- Test in `test_run_c_findings.py`; TEST_TRACK E103. Not tested live yet: E103

---

## November 2026 — validation close-out: notes budget restored; no empty Page column (#307)

**Why:** `module_budget_chars` was lowered to 7800 in #296 only to drive E23 live; that is proven (the SCRUM-293 notes PR named `core.md` at 7924 characters), so the shipped value goes back. The nightly inventory PR of 5 Nov confirmed two planned elements and showed a `Page` column empty in every row - the column is only for a whole planned page going live.

- `config/config.yaml`: `context_update.module_budget_chars` back to 8000
- `core/inventory_update.render_body`: the `Page` column of "Planned elements now live" is shown only when a row has its page confirmed
- `test_inventory_planned_shared` checks the column is left out; TEST_TRACK E102 and the evidence of Runs A-C. Not tested live yet: E102

---

## November 2026 — a new page object must name its page in the inventory (#303)

**Why:** for SCRUM-292's page, missing from the inventory, the model's third way round the missing-page stop was a page object declaring no `INVENTORY_PAGE` at all; the selector check skipped it as "not a page object", and four repairs ended on other errors.

- `validators/method_resolution_validator.validate_page_object_selectors`: a new `BasePage` subclass with methods and no `INVENTORY_PAGE` is refused (repairable); committed page objects, stubs and helpers are unchanged
- `test_repair_loop` pinned the gap and is updated; TEST_TRACK E101. Not tested live yet: E101

---

## November 2026 — a spliced step never substitutes an unrelated check (#302)

**Why:** SCRUM-293's `ai-update` spliced a step for a feedback section no page object could read, and the writer - told to "assert with one that does" - asserted the title links instead: a step that passes whatever the page shows. The notes-addition PR of the same story said its tests had passed, though the story's PR was merged while they ran and two failed.

- `agents/agent2_coder._generate_missing_step_functions`: a step no listed method checks is written as `raise NotImplementedError("needs a page-object method: ...")`, never with another check; the splice stops with the step named and `ai-regenerate` as the remedy; `run_update` posts one `[agent2:update-stopped]` comment and removes the update label
- `core.context_update.render_addition_body`: claims nothing about the story's tests; merge once they pass on main
- `_validate_generated_files`: a page the inventory does not have is checked first, so the blocked comment names the page and the `plan_inventory page` command, not whichever later check failed (SCRUM-292)
- Tests in `test_splice_grounding.py`; TEST_TRACK E98-E100. Not tested live yet: E98-E100

---

## November 2026 — Agent 2 names what a scenario does not check; text compared without letter case (#298)

**Why:** SCRUM-293's pull request left out one expected result of a test case (an element the inventory lacked) and still claimed it automated - a marker proves pairing, not content (L31) - and its heading checks failed because the page shows the heading in capitals.

- `agents/agent2_coverage.audit_partial()` with `prompts/agent2_coverage_audit.md`: after the gate, one structured call per batch lists, per test case, each expected result its scenario (with the Background) does not check; each becomes "covered, but needing a person" on the PR and the story. Fails open; `agents.agent2_coder.coverage_audit` switches it off
- `prompts/agent2_coder_generate.md` rule 6a: compare displayed text case-insensitively unless case is what the test case checks; `core.failure_diagnosis`: a case-only mismatch reads `CAUSE (letter case)`
- Tests in `test_run_c_findings.py`; TEST_TRACK E96, E97. Not tested live yet: E96, E97

---

## November 2026 — no test pins a tunable config value (#296)

**Why:** lowering `context_update.module_budget_chars` for validation step C1 turned the unit suite red - a test pinned the shipped value to the default, the flaw #288 fixed in two other tests.

- `test_notes_budget`, `test_inventory_planned_shared`, `test_run_c_findings`: the shipped `module_budget_chars`, `layout_min_pages`, `schedule_window_hours` and `schedule_min_expected` are checked for being configured and sensible, not for equalling the default; tests comparing names or structure are unchanged
- `config.yaml`: `module_budget_chars: 7800` for E23 (back to 8000 after Run C)
- TEST_TRACK E95

---

## November 2026 — budget alerts follow the limit; a forced re-analysis retries the context update; a backlog story is told why it waits; a new refusal reason is posted (#293)

**Why:** found while running the validation on 4 Nov 2026: today's budget alerts stayed open all day after `per_day_usd` was raised; a forced Agent 0 run on SCRUM-207 could not retry its context update because an earlier "no update needed" verdict stood; and the not-selected notice of #276 never found a story with no sprint at all - the very case it was built for.

- `scripts/pipeline_health_check.housekeeping`: today's `budget-day` / `budget-warn` alert closes when today's spend is below the current limit / warning share
- `core.context_update.propose_for_story(force=)`: forced, a verdict or a closed PR no longer stands; an open PR still does; Agent 0 passes `--force` through
- `integrations/jira_client.find_unselected_stories`: outside the scope includes `sprint is EMPTY` (JQL never matches an empty sprint in a negated condition)
- `core.blocked`: the blocked comment carries a digest of its reasons; a retry by key refused for another reason posts it (the scan's skip still reads the inputs only)
- `pages/nav_page.py` (application code, a person's step): `go_to_test_cases()` - the remedy SCRUM-293's refusal asks for
- Tests in `test_spend_budget.py`, `test_change_story_retry.py`, `test_run_b_findings.py`, `test_blocked_story.py`; TEST_TRACK E91-E94. Not tested live yet: E91-E94

---

## November 2026 — a committed page object the steps need a method on joins the repair (#292)

**Why:** SCRUM-293's step definitions called a method the home page object did not have; the plan had not named that file, so only the step definitions were repaired, and after three attempts the story was refused.

- `agents/agent2_coder._bring_in_page_objects()`: a committed, non-reserved page object the steps call a missing method on joins the batch as an extension, with its own feedback (add the named methods through its inventory keys, keep every existing one), repaired before the step definitions
- Tests in `test_run_c_findings.py`; TEST_TRACK E90. Not tested live yet: E90

---

## November 2026 — the health probe asks the output room the agents ask (#291)

**Why:** the model gateway reserves a request's cost from its `max_tokens`: with its credit low it answered 4,096-token requests and refused 16,384-token ones with HTTP 402, while the health check, asking for 1 token, reported the model as answering.

- `core.health_checks`: the completion probe asks the code-generation output room for each model; billed on the tokens used, it still costs a one-word reply
- Tests in `test_pipeline_health.py`; TEST_TRACK E89. Not tested live yet: E89

---

## November 2026 — a provider refusing calls for money stops the run; the health check probes every model (#290)

**Why:** on 4 Nov 2026 the model gateway answered HTTP 402 Payment Required to every call of the coding model: Agent 2 failed with a traceback, a scan would have failed story after story, and Pipeline health reported the model as answering - it probed only the light model.

- `core.llm_client`: HTTP 402 or a provider's credit / budget message raises `BudgetExceeded` with scope `provider` (`stops_the_run`, like a day stop); a plain rate limit is still `QuotaExhaustedError`
- Agents 0, 1 and 2 stop their scans at the first refusal, red, with one `[BUDGET]` line saying a person must raise the provider's budget; no story is handed back, held or blocked
- `core.health_checks.check_model`: every model in `LLM_MODELS_TO_CHECK` (the workflow lists `LLM_MODEL_LIGHT` and `LLM_MODEL`) probed once; one `credential:model` alert naming each refused model; a provider refusal is an alert, the pipeline's own budget still is not
- Tests in `test_spend_budget.py`, `test_scan_budget.py`, `test_pipeline_health.py`; TEST_TRACK E87, E88. Not tested live yet: E87, E88

---

## November 2026 — a new page object may not borrow another's inventory page (#289)

**Why:** SCRUM-292's page is not in the app inventory. The refused page object (printed in the log since #288) set `INVENTORY_PAGE` to the navigation entry, navigated by a hard-coded path and resolved no element, so no check named the missing page and the story was refused after every repair with advice to change its test case.

- `validators/method_resolution_validator`: a page object naming a page another committed page object implements, in another file, and resolving none of its elements, is refused (repairable); the repair names its own page, and a page missing from the inventory then stops the run (E49)
- `core.blocked`: if that error survives, the comment says the page is likely missing and gives the `plan_inventory page` command
- `config.yaml`: `reconcile.closed_scans` back to 2 (validation step B5 done)
- Tests in `test_run_c_findings.py`; TEST_TRACK E86. Not tested live yet: E86

---

## November 2026 — tests own their settings; a refused story names its errors; scans spend only on work (#288)

**Why:** step B5 of the validation sets `reconcile.closed_scans: 1`, and nine unit tests went red because they read the shipped config; and SCRUM-292 (4 Nov 2026) was refused with a one-line summary blaming the method names, while the eight errors under it - two of them methods a reserved page object lacks - never reached the person; and scans paid a plan for every repeat of the same wait, gave their places to stories that did nothing, and ran a story given by key in the wrong mode.

- Reconcile tests fix the scan count they walk (`pin_closed_scans`); the Agent 0 settings guard checks every key is present with a value of the right kind, not its value
- Agent 0's report writes its table only when there are rows ("Affected: 0" had an empty header)
- Every specific final-gate check in Agent 2 raises `GateFailure` with its errors: the `[agent2:blocked]` comment and the review fix's refusal list them
- `core.blocked`: a method a reserved page object lacks is listed (`<Class>.<method>`, file) with a person's step - add it or reword the test case - instead of "the test case asks what the application cannot show"
- Each file the final gate refuses is printed in a folded group of the run log, workflow commands stopped while it prints
- `core.in_flight.still_waiting()`: a story whose last wait (same inputs, same open pull request, same file) still holds waits again before the plan - SCRUM-293 had been planned seven times ($0.79) to reach the same wait
- Agent 2 `--story` (the workflow's `story_key`) runs the mode the story's labels ask for (`ai-update`, `ai-regenerate`); SCRUM-201 with `ai-update` had run in normal mode and been marked coded with "no work needed"
- A scan story that did nothing (blocked, or a wait before any model call) hands its place to the next deferred story - a blocked and a waiting story had taken both places on every scan
- `config.yaml`: `reconcile.closed_scans: 1` for B5 (back to 2 after Run B)
- Tests in `test_run_b_findings.py`, `test_run_c_findings.py`, `test_in_flight.py`, `test_scan_budget.py`; TEST_TRACK E80-E85. Not tested live yet: E81-E85

---

## November 2026 — a start never cancels a run already waiting to start; a yes/no predicate is not a misnamed reader (#285)

**Why:** the repository host keeps one waiting run per workflow: a second start replaces the first, cancelled without a word. On 4 Nov 2026 a run started by hand for SCRUM-296, and a run Agent 0's hand-off started, were both cancelled by later hand-off starts.

- `core/handoff.start()`: a workflow with a run not started yet (queued, pending, waiting, requested) is not started again - that run takes the waiting stories; a host that cannot say starts as before
- Agents 1 and 2: a one-story run's restart step leaves out the progress rule (it took only its own story), so it starts the scan the waiting stories need
- `validators/method_resolution_validator`: the reader-naming rule skips a predicate (`-> bool`, or named is_/has_/...) - SCRUM-296's `has_product_with_price() -> bool` was refused through every repair attempt and the story failed
- `tests/unit/test_run_c_findings.py`; TEST_TRACK E78, E79. Not tested live yet: E78, E79

---

## November 2026 — what Run C of the validation found (#284)

**Why:** starting Run C on 4 Nov 2026 showed seven more places (and #276's evidence explained an eighth) where work stopped or went wrong with nothing reporting it: the repository host started almost none of the agents' scheduled runs and no check noticed; a planned list of titles was never confirmed; a new story was drafted as one test case saying its page "is not defined in the Application Under Test"; one story needing a person turned the run red, and the hand-off then left every other waiting story to a schedule that rarely starts; and that story was taken first again on every scan.

- `core/health_checks.schedule_findings()` with a five-field cron reader (`cron_fires`): a scheduled workflow whose cron lines asked for at least `pipeline_health.schedule_min_expected` (3) runs in the last `schedule_window_hours` (24), none of which the host started, raises `workflow-not-starting:<file>`; one started run closes it
- `scripts.plan_inventory --family`: a planned selector naming a list is declared `multi_match` too, so its several live matches confirm it instead of reading as AMBIG
- `core/test_case_rules`: a test case saying something is not defined / described / present in the Application Under Test, the app context, notes or inventory, the reference notes or the provided context is sent back; both Agent 1 prompts say a thing the story asks for that the section lacks is new
- Agents 1 and 2 start themselves again after a red run too (`!cancelled()`); the progress rule of #262 still stops a run that took no waiting story, and `handoff.max_chain` bounds the chain
- Agent 1's scan hands back a story that needs a person (a partial set of test cases): `ai-ready` off, one `[agent1:stopped]` comment saying what to do
- F-32: #276's evidence on SCRUM-296 was an empty answer after 12,288 tokens - the model reasoned through the whole budget before answering. The impact-aware budget is 12,288 + 2,048 per approved case (at most 32,768); `truncation_evidence()` names an empty truncated answer as reasoning
- Agent 0: an analysis that finds nothing while an earlier Impact Review is open rewrites that review with no rows and a *Superseded* line and takes `impact-proposed` off (SCRUM-295 kept both `ai-ready` and `impact-proposed`, and its stale review stayed open)
- `core/context_update.free_branch()`: a context update or notes addition whose earlier pull request was closed unmerged is proposed on `<branch>-<n>` (the closed branch stays - the repository forbids deleting it); while one is open, nothing is proposed
- `tests/unit/test_run_c_findings.py`; TEST_TRACK E70-E77
- Not tested live yet: E70-E77

---

## November 2026 — what Run B of the validation found (#276)

**Why:** Run B drove SCRUM-291 and SCRUM-296 through the agents on 4 Nov 2026. The flaws it found, with those from Run A, were each a place where something went wrong without anything saying so or stopping it. Some were silent: a story never selected, a truncated answer with no evidence, a PR table whose two cells read the same. Some repeated: a failed draft paid for every 30 minutes. Some were contradictions: the orphan clean-up against the page-object contract, a quote the story never stated, a copy of an existing test.

- `core/llm_client.truncation_evidence()`: an answer that runs out of output room is logged - its size, how much of it repeats (*LIKELY A LOOP* at a quarter or more), the most repeated piece and its last 800 characters - so a loop can be told from genuine size before a cap is raised
- `agents/agent1_analyst`: `stops_retrying()` / `hand_back()` - a scheduled scan whose draft ran out of room or broke the test-case rules twice (`core.test_case_rules.DraftRejected`, a `ValueError`) removes the trigger label and posts one `[agent1:stopped]` comment, instead of paying for the same failure on every scan. Other failures keep the label
- Agent 1's normal draft is shown the scenarios that exist (`existing_scenario_titles()`, the impact-aware block): a criterion one already verifies unchanged cites it; a new test titled as one is sent back (`repeats_of_existing()`)
- `agents/agent2_coder`: a planned file generated exactly as on `main` is not committed (`unchanged_files_dropped()`), and the PR lists it under *Planned, but unchanged*; every file unchanged stops before a branch is made
- `core/selection_notice.py` (new) and the optional tracker capability `find_unselected_stories()`: a story carrying an agent's trigger label that the scan's status or sprint filter leaves out gets one `[pipeline:not-selected]` comment per agent and reason (Agents 1 and 2, every selection). `JiraClient._effective_sprint()` is the one sprint resolution
- Agent 0: `--force` / the workflow input `force` analyses one unchanged story again; its code-change comment is markdown on the pull request (`for_pull_request()`: the table's separator row, the data folded away); each element path names the element's selector, and the judge is told that finding an element is not reading its text
- `core/context_update`: a rewrite that puts in quotes a text neither the story nor the notes state is not applied (`invented_quotes()`, and a prompt rule); the PR table shows each rewrite from its first difference to its last (`changed_part()`)
- `validators/page_object_contract.orphaned_on_purpose()`: a method the orphan clean-up commented out under `# AI-ORPHAN:` is not a lost method. `cleanup_orphans_after_removal(called_elsewhere=)` with `agent2_coder.methods_called_in_open_prs()`: a page method an open pull request calls is not orphaned; unreadable open pull requests orphan no page method
- `tests/unit/test_run_b_findings.py` (28). TEST_TRACK: E59-E69; the impact-aware output budget (F-32) waits for E59's evidence
- Not tested live yet: E59-E69

---

## November 2026 — a notes change touches only the story's own pages; the small backlog (#267)

**Why:** before Run A, the rename update was run on the real inventory and notes for the two validation stories (SCRUM-295 with Component Cart, SCRUM-290 with none). With the Component, a `core.md` line about the all-products cards was renamed too - `core.md` is always in scope. Without one, the seeded details page widened through its Components (Products, Cart) to every page sharing them, and the all-products selector `text=Add to cart` was rewritten - the listing's tests would have broken after merge. Both came from #265.

- `core/context_update.propose()`: when the old text is also on a page outside the scope, only the in-scope pages' own inventory values change; notes lines, `core.md`, shared inventory values and `always` pages holding it are listed for review (`Proposal.review`), not changed. Text only inside the scope changes its notes as before
- `propose_for_story(seeds=)`: the inventory pages are the seeded pages (plus `always` pages), never every page sharing their Components; the Components still choose the notes modules
- Checked on the real repository, both flows: with the Component and without, only the details page's own notes change; the listing's selector and `products.md` are listed *not changed*, `cart.md` and `core.md` for review. The notes addition offers `core.md` + `products.md` with a Component (SCRUM-283) and `core.md` + `home.md` plus a new `contact_us.md` without one
- The small backlog: a repair is shown a feature file as it stands and told to keep titles, markers and tags (`_previous_attempt_worth_showing`); `get_review_comments` leaves out every bot comment, not only replies; the jira library's false "link type is not present" warning, logged on every link, is dropped around the call; Gherkin tags are free markers (`filterwarnings` in pytest.ini); the duplicate-step check loses its unreachable half; `get_property` returns plain JSON by its signature; the review fix says why its two write-access rules differ; `opening_step` names its sort key
- TEST_TRACK: the runbook - one ordered sequence with the validation stories (SCRUM-290 to SCRUM-298), every open row in one step (checked by script); E14 re-targeted (PR #211 is closed); E57's expectation updated; the small backlog closed
- `tests/unit/test_notes_follow_the_page.py` (20), `tests/unit/test_small_backlog_fixes.py` (11)

---

## November 2026 — a notes change reaches only the page it is about; several reviewers on one pull request (#265)

**Why:** before merging SCRUM-284's notes addition the question was asked: the same text sits in several notes files and pages - does a change for one page stay on that page, especially with no Component tagged? And does the review fix still work with several reviewers? Reading the code: (1) a change story's wording replacement was applied to **every** notes module and **every** inventory value, selectors on pages the story never touched included; (2) a story with no Component had every module offered for its new facts and none could be started for its own page - SCRUM-284's went into the home page's module; (3) a new fact was dropped as "already stated" when **another** page's module used the same words; (4) GitHub keeps one waiting run per pull request, so with a fix running, a second reviewer's request could be cancelled by a third's, and its own text (the review's summary, the words after `/fix`) was lost; (5) the workflow checked who **started** a run, but line comments were taken from anyone.

- `core/context_update.propose(narrowed=)`: the wording replacement is applied inside what the story's Components select (`core.md` and their modules; their pages, `always` pages and shared inventory values); the same text elsewhere is listed under *not changed*. With no Component (`narrowed` False), text on more than one inventory page or in more than one notes module is listed as *not applied* - nothing says which the story means. A caller without a story (`narrowed` None) replaces everywhere, as before
- A change story with no Component is scoped by the pages Agent 0's impact analysis found it changes (`seed_pages()` over the report's `seeds`, `components_of_pages()`; `agent0_impact._propose_context` passes them): a control repeated on several pages and changed on one changes there only. Without seeds (an older report) it is judged as above
- `components_from_tests()`: a story with no Component takes its Components from the inventory pages its merged tests use (feature files by `# JIRA:` marker → step-definition fixtures → `INVENTORY_PAGE` → the page's `components`; `always` pages left out). Checked on main: SCRUM-284 gives Contact Us + Home (and so a new `contact_us.md`), SCRUM-283 gives Products, Cart, Search
- `propose_additions()`: a new line is compared with the target module, `core.md` and the story's earlier additions only
- `agents/agent2_review_fix.py`: `unhandled_requests()` - each run also takes the text of every earlier Request-changes review and `/fix` comment, by a person with write access, that no run handled; the summary records them (`also handled: …`), and `handled()` reads that line. `WRITE_ACCESS` (the workflow's own list): a line comment by anyone else is not taken, and the summary names its author. A host that cannot say (no `association`) is trusted, as before
- `RepoHost.get_pr_reviews()`, `get_pr_comment_records()` (GitHub: PyGithub reviews and issue comments with `author_association`); `get_review_comments()` now carries `association`; both are reads for the dry run
- `tests/unit/test_notes_follow_the_page.py` (17), `tests/unit/test_several_reviewers.py` (8); the two fake hosts of the host-abstraction tests implement the two new methods; 12 deliberate breaks each fail a test
- Not tested live yet: E57, E58

---

## November 2026 — a scenario opens a page before it acts on one; Agent 3 sees the page-object methods a pull request calls (#265)

**Why:** SCRUM-284's first run (its pull request, 4 Nov) failed both scenarios: the test case said "navigate to the home page, then click Contact us", and the generated Background only clicked. Every test starts on the browser's empty page, so each waited 30 seconds for a link that could never appear, and the failure read as a selector problem. Every check passed - the method existed, the selector was right. Agent 3 then blocked the pull request over `go_to_contact_us()` "possibly not existing": it was on `main`, merged the hour before, outside the diff. A person's line comment and `/fix` repaired it.

- `validators/opening_step.py` (new): `validate_scenarios_open_a_page_first()` - the first Given/When step each scenario runs (its Background's, else its own) must make, as its first page-object call, a call to a method that navigates (`self.navigate` / `goto`, directly or through another method of its class). Only what can be read is judged: no page-object call, an unknown class or method, an unmatched step, or a scenario that opens on a Then is left alone. One error per step, not per scenario. Repairable: in `_collect_repairable_errors()` (28 calls; 33 distinct checks)
- `validators/gherkin_analyzer.step_functions()`: the step functions of a file with their decorator phrases, as Python reads them (the AST reader of #253, now public)
- `pages/base_page.py`: `_refuse_the_empty_starting_page()` - an action on `about:blank` with nothing in it fails at once with "No page is open ... the scenario's first step must open a page"; a page a test filled itself (`set_content`) and anything unreadable are left alone. `core/failure_diagnosis.py`: diagnosed as *no page opened before acting*
- `agents/agent3_reviewer.py`: `page_object_methods_called()` - every page-object method the changed step definitions call (BasePage helpers excluded: they have their own section), with signature and first docstring line, from the pull request's version of the page file or else `main`'s; the prompt's new *Page-Object Methods Called* section says they exist and are never reported missing
- `tests/unit/test_a_scenario_opens_a_page_first.py` (17, two in a real Chromium); 7 deliberate breaks (navigate not recognised, no helper recursion, no de-duplication, no Then scope, the guard removed, the guard on every empty page, Agent 3 reading only the diff) each fail a test. The full suite caught two faults of the first draft, both fixed: the validator imported inside the function (the routing contract patches module names) and the rule applied to a scenario that opens on a Then (the gate-agreement contract)
- Checked on the real case: SCRUM-284's branch before its fix gives one error, after it none; every feature on `main` passes
- TEST_TRACK: E56; E48 confirmed by SCRUM-284's pull request
- Not tested live yet: E56

---

## November 2026 — the hand-off restarts an agent only after progress; the top menu reaches the contact page (#262)

**Why:** overnight (3-4 Nov) SCRUM-284 carried `human-approved` but was blocked (its earlier refusal). Agent 2 skips it, yet it matched Agent 2's selection, so after each delayed scheduled run the hand-off started Agent 2 again - five empty runs, twice - until `max_chain` stopped it. And SCRUM-284's test cases open the contact page from the top menu, which `NavPage` (reserved for Agent 2) could not do.

- `core/handoff.start(waiting_before=)`: an agent starting itself starts again only if its run took at least one of the stories that waited when it began; progress is judged on up to `PROGRESS_LIMIT` (50) waiting stories. Agent 0 starting Agent 1 passes nothing (new work)
- `scripts/start_agent.py --record-waiting PATH` / `--waiting-before PATH`; a missing or unreadable record decides as before; recording never fails the run
- `agent1_analyst.yml`, `agent2_coder.yml`: *Record the stories waiting before the run* right before the agent; the restart passes it
- `pages/nav_page.py` (application page object, a person's change): `go_to_contact_us()`, as `go_to_products()` / `go_to_cart()` - `nav.contact_us_link` was already in the inventory
- TEST_TRACK: the live evidence of 4 Nov (E51-E54 and parts of E45c, E47, E48, E52)
- `tests/unit/test_agents_start_the_next_agent.py` +9 (35); 4 deliberate breaks (restart without progress, progress judged on one story, the record not passed by the script or the workflow) each fail a test
- Not tested live yet: E55

---

## November 2026 — a Jira issue property reads back as the JSON that was stored (#260)

**Why:** Agent 5's second report on SCRUM-283's pull request (4 Nov) crashed - "'PropertyHolder' object has no attribute 'get'" - reading its own last-report fingerprint; *Post Results to Jira* went red with every test passing. The jira SDK parses an object value into a PropertyHolder (attributes, no `.get()`), and `JiraClient.get_property()` returned it. Every reader that treats the value as the dict it stored was affected: Agent 5's repeat check crashed; the flaky-test names and Agent 0's outcome check fell back silently (their reads are wrapped).

- `integrations/jira_client.get_property()`: the value from the response's raw JSON (dict, list, str, number), as stored; a missing property is None, other errors raise, as before
- `tests/unit/test_jira_property_values.py` (9) against the SDK's real `IssueProperty`, including Agent 5's `_last_report()` and a test that fails if the SDK stops wrapping; the old method fails 3 of them
- Not tested live yet: E54

---

## November 2026 — review fix reads a person's reply in a thread (#259)

**Why:** iterating on SCRUM-283's pull request (4 Nov), the reviewer answered in the existing thread - the usual way to ask again. `get_review_comments()` left every reply out, and the thread's first comment was already handled, so `/fix` would have found nothing to act on.

- `integrations/github_client.get_review_comments()`: each thread's first comment and a person's reply (`reply_to`: the thread's first comment); bots' replies - Agent 2's own answers - still left out
- `agents/agent2_review_fix`: a reply is an item of its own, recorded as handled by its id; Agent 2 answers in its thread (GitHub replies through a thread's first comment)
- `tests/unit/test_agent2_review_fix.py` +2 (43); 3 deliberate breaks (replies dropped again, bots' replies read as requests, answering on the reply) each fail a test
- Not tested live yet: E53

---

## November 2026 — review fix keeps the feature file's scenarios through the repair, and declines dropping an approved check (#258)

**Why:** the first live review loop (SCRUM-283's pull request, 4 Nov). A comment asked to reword a step that the approved test case states ("no login prompt is shown"); the reworded file dropped that check, the absence-claims rule flagged it, and the repair loop regenerated the whole feature file in the ordinary mode - invented marker hashes (`1a2b3c4d`, ...), no `owner:`, a new title, a Scenario Outline - which was pushed. The rule "a feature file keeps its scenarios, titles and markers" was checked on the review change only, before the repair. The branch was reset by hand.

- `agents/agent2_review_fix._fix()`: after the repair loop, every changed feature file must still have its scenarios, titles and markers; otherwise nothing is pushed and the summary says which file
- `_drops_an_approved_assertion()`: a review change to a feature file that adds an absence-claims error (drops a check an approved test case states) is declined with the way to get it - change the test case, then `ai-regenerate`; a gap that was already there is not blamed on the comment
- GUIDE: both
- `tests/unit/test_agent2_review_fix.py` +4 (41); 3 deliberate breaks each fail a test
- Not tested live yet: E52

---

## November 2026 — review fix: a review takes the earlier line comments; a budget stop records nothing (#257)

**Why:** validating the review loop on SCRUM-283's pull request (3 Nov). The reviewer added two line comments with GitHub's "Add single comment" - each became a review of its own - then submitted "Request changes" with a text only: the review fix saw only the text. And the day's model budget was spent: the run's summary read "Nothing needed a code change" and recorded the review as handled, so neither a re-run nor a later `/fix` would have taken those comments again.

- `agents/agent2_review_fix.collect_items()`: a review takes its own inline comments, then every earlier inline comment not handled before (as `/fix` already did), then its text
- A budget stop (deciding or generating): status `not_done`, summary `[agent2:review-fix:not-done]` saying nothing was decided or changed and how to retry; no review or comment is recorded as handled
- GUIDE: both
- `tests/unit/test_agent2_review_fix.py` +4 (37); 4 deliberate breaks (earlier comments ignored, the stop marked handled, the deciding-stage stop not flagged, handled comments taken twice) each fail a test
- Not tested live yet: E51

---

## November 2026 — Agent 4 checks out the event's commit by SHA (#255)

**Why:** #253 was merged while its Agent 4 run was still going; the report job then failed at checkout - "couldn't find remote ref refs/pull/253/merge" - and Agent 5's report was lost. #245 checked out `github.ref` by name, and GitHub deletes `refs/pull/<n>/merge` once the pull request is merged or closed. A story's pull request merged quickly would never get its results on the story.

- `agent4_runner.yml`: the `test` and `report` jobs check out `github.sha` - the same commit (on a pull request the merge commit the event was raised for), fetched by SHA, which stays fetchable after the ref is gone
- `tests/unit/test_agent4_tests_the_merge_result.py`: by SHA, and no job checks out a ref merging deletes (5); putting a job back on `github.ref` fails two tests
- Not tested live yet: E50

---

## November 2026 — a story that needs a page the inventory lacks stops at once, and says how to add it (#254)

**Why:** validating SCRUM-284 (3 Nov) - a contact form whose page the inventory did not have. The generated page object was refused ("not a page in the app inventory"); the repair loop "fixed" it by deleting what it could not anchor, the step definitions then called methods that no longer existed, and after four attempts ($1.50) the story was blocked with a comment blaming the model and the test case. No repair can add a page: the inventory is curated by a person.

- `validators/method_resolution_validator.pages_missing_from_inventory()`: the pages a generated page object names that the inventory lacks - not a misspelling of one it has (no close match), which a repair can still fix
- `agents/agent2_coder._attempt_step_coverage_repair()`: stops before repairing when there is one; the final gate reports it
- `core/blocked.blocked_comment()`: names the page and the command that adds it (`scripts.plan_inventory page ...`), then "run Agent 2 with this story's key"; every other refusal reads as before
- GUIDE (troubleshooting): what to do with such a comment
- `tests/unit/test_page_missing_from_inventory.py` (11); 3 deliberate breaks (the loop repairing, a misspelling read as missing, the comment without the page) each fail a test
- Not tested live yet: E49

---

## November 2026 — step decorators are read as Python reads them (#253)

**Why:** validating SCRUM-284 (3 Nov), Agent 2 wrapped a long step phrase over several string literals - Python's usual line break, joined into one string before pytest-bdd sees it. The validators read decorators with a pattern that stopped at the first closing quote, so they reported "no matching decorator", "unused step definition" and "drifted wording" for a step pytest-bdd resolves. Four repair attempts "fixed" a non-problem and the story was blocked ($1.50) with a comment blaming the model and the test case. A decorator with keyword arguments (`target_fixture=`) was not seen at all.

- `validators/gherkin_analyzer._extract_decorator_phrases()` parses the file (`_decorators_from_ast()`): literals joined, escapes resolved, comments dropped, keyword arguments allowed, source order kept; every validator and Agent 2's own checks use it. A file that does not parse falls back to the patterns, as before
- `tests/unit/test_step_decorators_read_by_the_parser.py` (11), including SCRUM-284's shape validated clean and the same files failing with the patterns alone; 4 deliberate breaks each fail tests
- SCRUM-284 also needs its page in the inventory (a page outside it is refused) - Agent 2 stopping early with that message is the next change
- Not tested live yet: E48

---

## November 2026 — Agents 0, 1 and 2 scan every 30 minutes, off :00 and :30 (#252)

**Why:** the repository owner (3 Nov): stories approved at 15:58 were still waiting at 17:04 - "is it started to break apart?". Nothing broke: since at least 8 Sep GitHub started 4 of Agent 1's and Agent 2's 19 weekday runs a day (two clusters, about 16:30 and 22:30-00:15 IST); that day none before 17:00. GitHub drops scheduled runs of a quiet repository, those at the start of an hour or half hour first - ours were on :00 and :30. Agent 0's story scan ran once a day. Asked: all three scan every 30 minutes in working hours.

- `agent0_impact.yml`: a story scan every 30 minutes, weekdays 10:02-19:02 IST (:02/:32); the `scan` job runs on every schedule but the nightly drift. Reconcile keeps its one daily run (10:45) - its two-scan rule counts scans, so every 30 minutes would undo a change within an hour
- `agent1_analyst.yml` :07/:37 (10:07-19:07), `agent2_coder.yml` :12/:42 (10:12-19:12): never on :00/:30, never together, in pipeline order
- An idle scan costs no model call (Agent 0's stage 0, Agents 1 and 2 find nothing) and about 30 runner seconds; the repository is public, so Actions minutes are free
- The schedules stay the safety net; the hand-off (#248) and the tracker rule are what start the agents when work arrives
- `tests/unit/test_schedules_off_peak.py` (11) and three rows in Agent 0's trigger table; 5 deliberate breaks (Agent 1 back on :00/:30, a gap in Agent 0's, reconcile every 30 minutes, the scan on the drift run, Agents 1 and 2 together) each fail tests
- Not tested live yet: E47

---

## November 2026 — a raised defect carries no code label (#250)

**Why:** the repository owner (3 Nov): Jira's label picker listed `ai-defect-ff8881ed6e`, `ai-defect-21bf9029c9`, ... - one meaningless code per failing test and cause, kept by the 14 closed defects too - "clumsy, and we don't know what that defect is". The code was the triage's fingerprint (sha1 of test and cause), and every defect's triage data already names both.

- `core/defects.py`: a new defect gets `defects.label` only (plus the unmapped / passing labels as before). `fingerprint_of()` computes the fingerprint from the triage data; a defect raised before, or one whose data was edited away, is still found by its code label (`legacy_labels()`: only `<label>-<10 hex>`), which is removed when the triage next updates it (a refused removal is reported in `errors`). A defect with neither is logged and left alone
- `scripts/tidy_defect_labels.py`: one-off pass - lists by default, `--apply` removes the code from every defect whose triage data identifies it or that is closed; an open defect whose data cannot be read keeps it (it is how the triage finds it) and is listed. Exit 0; refusals listed
- GUIDE: how a repeat is matched, the tidy pass, and a saved filter to see the defects
- `tests/unit/test_defects_without_code_labels.py` (13), two existing tests updated; 7 deliberate breaks (the code written again, the data not read, no label fallback, the code kept on update, the tidy pass removing an open unreadable defect's code, applying by default, a loose code shape that would take the passing label) each fail tests
- Not tested live yet: E46

---

## November 2026 — the hand-off's chain cap warns only when a story is left waiting (#249)

**Why:** Agent 3's review of #248: `core/handoff.start()` applied `handoff.max_chain` before asking what waits, so a chain ending with an empty queue - the normal end - printed a `::warning::`.

- `core/handoff.py`: what waits is asked first; the cap is reported (and warned) only when it leaves a story for the schedule
- `tests/unit/test_agents_start_the_next_agent.py` +1 (25); the old order fails it

---

## November 2026 — an agent that leaves work for another starts it (#248)

**Why:** in end-to-end validation (3 Nov) SCRUM-283 and SCRUM-284 reached ai-ready at 13:22 IST; at 14:10 not one of Agent 1's half-hourly scheduled runs had started that day. Over the two weeks before, GitHub started about 4 of its 19 daily runs, some hours late (one at 03:34 IST); Agent 2's schedule showed the same. GitHub drops scheduled runs of a quiet repository, so a story waited hours, not the 30 minutes the schedule promised. Agreed with the repository owner: Agent 0 starts Agent 1; the schedules stay as the safety net.

- `core/handoff.py` + `scripts/start_agent.py`: start an agent's workflow when a story waits for it - asked with that agent's own selections (every `*selection` block under `agents.<key>`), in scan mode, carrying `chain` (runs started in a row); stops at `handoff.max_chain` (5). Never raises; the script always exits 0 (a refused start is a warning and a job-summary line)
- `agent0_impact.yml` (story analysis job): starts Agent 1 after Agent 0, also after a failed analysis (a story released before it still waits); not on a dry run. Job permission `actions: write` (was read)
- `agent1_analyst.yml`, `agent2_coder.yml`: start themselves again while stories wait past `max_stories_per_run` - on success only, so a failing story is retried by the schedule, never in a loop; a `chain` input; `repository_dispatch` with the agent key as event type, for a tracker rule (GUIDE: the Jira Automation rule that starts Agent 2 on approval - optional, the person's token stays in the rule); `actions: write`
- `integrations/github_client.dispatch_workflow()` (optional repo-host capability); `handoff` block in `config.yaml` / `core/ops_settings.py`
- `tests/unit/test_agents_start_the_next_agent.py` (24); `test_uncovered_snapshot.py` pins the scan job's permissions at `actions: write`; 9 deliberate breaks (no chain bound, start without work, selection order, not scan mode, a refused start raising, Agent 1 looping after a failure, the chain input pasted into the script, Agent 0 not starting Agent 1, the script failing the run) each fail a test
- Not tested live yet: E45a-d

---

## November 2026 — a story that changes nothing existing rewrites no reference note (#247)

**Why:** validating the pipeline end to end (3 Nov), SCRUM-283 "Write a review for a product" - coverage of a review form the application already has - went straight to ai-ready, so Agent 0 ran the hand-over context update at once. Asked which notes the story makes untrue, the model narrowed a correct, fuller note in `products.md` ("All three fields are required ... blocked by the browser's own validation") to the story's own sentence and opened a context-update pull request (branch `context-update/scrum-283`, closed unmerged). Agent 0 already classifies every requirement story (`ChangeSeeds.change_type`) and already trusts `new_behaviour` to mean nothing existing changes (its element seeds are dropped) - the context update never saw that classification.

- `core/impact_analysis.report_dict(change_type=)`: a requirement report keeps the story's change type (`analyse_requirement` passes the model's classification); the pull-request and inventory triggers pass none, so their reports are byte-for-byte as before. The readable report shows "Change type: ..."
- `core/context_update.propose_for_story(change_type=)`: `new_behaviour` → no model call, a `[agent0:context-update]` "No context update needed" marker naming the classification and pointing at the notes addition (what such a story ADDS reaches the notes when its tests merge). Every other type, and none (a report written before this), runs the update as before
- `agents/agent0_impact._propose_context(report=)`: straight to ai-ready it uses the report just made; at hand-over it reads the published one. A report that cannot be read runs the update as before (logged)
- Saves the two context-update calls (about $0.09 on SCRUM-284) on every new-feature story
- `tests/unit/test_new_behaviour_rewrites_no_note.py` (18); 5 deliberate breaks (skip removed, type not passed, in-memory report ignored, key always written, unreadable report not tolerated) each fail a test
- Not tested live yet: E44

---

## November 2026 — Agent 4 tests a pull request merged with main, not the branch alone (#245)

**Why:** PR #241 went red on "unrecognized arguments: --app-probe" while every one of its tests passed. On a pull request GitHub takes the workflow file from the PR merged with main; Agent 4 then checked out the branch alone, so a branch cut before #242 ran main's new workflow step with its own older script. Any pull request open while main changes a workflow and its script together hit the same false red. Agreed with the repository owner.

- `agent4_runner.yml`: the `test` and `report` jobs check out `github.ref` - `refs/pull/<n>/merge` on a pull request (the same commit as the workflow, and what main will hold after the merge), the event's own ref otherwise. One run per push, as before. A pull request that conflicts with main gets no run at all - GitHub's rule, before and after: update it with main. The branch name is still read from the event (`github.head_ref`, `GITHUB_HEAD_REF`)
- `tests/unit/test_agent4_tests_the_merge_result.py` (4); 2 deliberate breaks (either job back on the branch) each fail a test
- Not tested live yet: E43

---

## November 2026 — every auto-raised defect is linked to its test case and story (#244)

**Why:** a defect the nightly triage raised named its test case and owning story in its description only - neither the test case nor the story showed it, and nothing could be filtered by feature. Closing the 14 defects of 28 and 30 Oct showed the worse half: five of them (the login reference tests) read "test case: not marked" and traced to nothing - the reference files carry no `# JIRA:` markers on purpose, since a marker would make them a target for `ai-update` and Agent 0's revisions. Asked by the repository owner: map every auto defect to its test or story.

- `core/defects.py`:
  - links each defect: "<defect> **blocks** <test case>" (the test case shows "is blocked by") and "<defect> **relates to** <story>" - new link kinds `defect_of` / `defect_story` in `tracker.link_types` (defaults Blocks / Relates; another tracker or project names its own)
  - the defect takes the story's **components** (`copy_components`; best-effort - a project whose defect screen refuses the field is logged, never a failure)
  - `trace_of()`: traced from the scenario's marker; else the one story every marked scenario of its feature file shares; else `defects.trace_owners` (feature file → story, for files that must not carry markers); else **not traced** - label `ai-defect-unmapped` and a "NOT TRACED" line saying what to add
  - kept current on every update: missing links added (defects raised before this included), a moved owner or test case moves its link, the label removed once traced
  - a trace naming an issue that no longer exists is a *stale trace* for a person, not a refused write (the issue is read back to tell it from a link type the tracker lacks - Jira answers both with 404)
  - `open_defects()` reads only `<label>-<10 hex>`: the unmapped and passing labels share the prefix (without it an untraced defect passing again was flagged twice - found by a deliberate break)
- `scripts/triage_failures.py`: one `defects-unmapped` alert for untraced defects and stale traces; the `defects-not-written` text also names a missing link type
- `integrations/jira_client.py`: `set_components()` (optional capability); `integrations/tracker.py`: the two link kinds
- Jira: story **SCRUM-282 "Login (reference tests)"** (component Login, Done) created and mapped in `config.yaml` (`defects.trace_owners: features/login.feature`); `login.feature` itself is unchanged
- `tests/sandbox/fake_jira.py`: a new issue never takes a key a test seeded by hand (as in Jira; a raised defect had been overwriting story SBX-1 in the sandbox)
- `tests/unit/test_defect_traceability.py` (23)
- Verification: 10 deliberate breaks (no links, no feature-file fallback, `trace_owners` ignored, the unmapped label read as a defect label, the label never removed, an old link never removed, every refused link read as stale, a components failure turning the triage red, no untraced alert, older defects never linked) - each fails a test. Full unit suite passed
- Not tested live yet: E42a-d

---

## November 2026 — the nightly inventory check says when the application was not up (#243)

**Why:** the *Inventory Health* run of 31 Oct found the login page loaded with none of its 11 elements, refused to report (correctly) and headlined "Login failed — inventory NOT checked: check the credentials". The night before, the application had served the nightly test run its pages without their content. Nothing in the check asked whether the application was up, so a site problem read as a credential problem. Asked by the repository owner: the same check on the nightly run, with no token spent, generic for any application.

- `inventory_health.yml`: when the verifier does not pass, *Check the application is up* runs `scripts/app_probe.py` (#242: the pages and elements in `app_under_test.health_check`, a browser and no model). Job timeout 20 → 30 minutes for its wait; its report goes into the artifact
- `scripts/inventory_health_report.py` (new): the summary the inline script wrote, plus two readings - **the application is not up** (neither drift nor credentials, change nothing; what the browser was shown), and a failed login on an application found **up** (the credentials or the login form). Every other summary is byte-for-byte what the inline script wrote (proven by running the old script beside the new one)
- `tests/unit/test_inventory_health_summary.py` (19)
- Verification: 5 deliberate breaks (the finding ignored, the credentials hint never used, the check run every night, the report not given the finding, a healthy night overridden) - each fails a test. Full unit suite passed; actionlint clean
- Not tested live yet: E41 - a night the application is not up

---

## November 2026 — an application that is not itself is an outage, not 17 failures; a defect only after a failed rerun (#242)

**Why:** on 30 Oct every one of the 17 tests failed in the nightly run on `main`: the login form, the search box, the product list and the newsletter field never appeared - on four different pages that were served (no HTTP error, no navigation timeout) without their content. The next night all 17 passed with no change. Nothing told "the application was not itself" from "17 tests are broken": more than ten failures switched the retry off (`MAX_RETRIED_TESTS` = 10, on the theory that so many meant an outage), and the triage then raised ten defects (SCRUM-272 to SCRUM-281) from the first run alone, plus a `defects-capped` alert for the other seven. Asked by the repository owner: rerun the failed tests, and raise a defect only after the rerun.

- **The application health check** - `core/app_probe.py`, `scripts/app_probe.py`: opens the pages in `app_under_test.health_check` (inventory page keys and elements always shown on them; this application: the home page's logo and newsletter field, the login form's email field, the products page's search box - exactly what was missing on 30 Oct) through `BasePage.navigate`, and checks each element is visible. Not up: checked again every `app_health.interval_seconds` for up to `app_health.wait_minutes` (8), so a short outage is waited out. The report says what the browser was shown instead (URL, title, the start of the page text, redacted). A wrong setting, or no browser, is `unknown`: the run carries on as before. Nothing configured: the base URL only (status), which cannot catch a page served without its content
- **Agent 4** (`agent4_runner.yml`): after a run with failures, *Check the application is up* runs before the retry.
  - Not up: the retry is skipped and `finalise_junit --app-probe` marks every failure `outage`, with the finding as `outage_reason` - not judged, never a defect; the check stays red (nothing was tested)
  - Up (or `unknown`): **every** failed test is run again - the cap is 100, a guard against doubling a huge run, no longer a guess that many failures mean an outage
- **Defects only after a rerun** - `core/defects.py` (`defects.only_after_retry`, on): a defect is raised or updated only for a test that failed, was run again and failed again (`retried`). A failure that was not run again raises nothing, and one `failures-not-retried` health alert lists it. The `application-unavailable-on-main` alert now carries what the check found
- `tests/unit/test_app_health_and_retry.py` (23) and `test_defects_after_rerun.py` (4), including:
  - three checks in a real Chromium against a local site: serving itself is up; served without its content (a "back soon" page with HTTP 200) is not up, with its title and text as evidence; an HTTP 503 is not up
  - a replay of 30 Oct: 17 failures and an application found not up raise no defect and one outage alert naming what was served
  - the shipped setting resolves against the shipped inventory, and names no conditional element
- `tests/unit/test_defect_triage.py`: a failure in its fixtures is now one that was run again and failed again (the realistic state)
- Verification: 11 deliberate breaks (the retry not gated by the check, the cap back at 10, the finding not read, an `unknown` check marking outages, an application found down marking nothing, defects from the first run again, no alert for failures not run again, the outage alert without its evidence, elements not checked, no waiting, an unknown element silently skipped) - each fails a test. The script run end to end in Chromium against a local site that comes back during the wait (`available=true` after 2 checks) and one that stays down (`available=false`, title and text named). Full unit suite 3837 passed; actionlint clean
- Not tested live yet: E40 - a real night where the application is not itself, and a real failure that fails twice

---

## October 2026 (end) — one redaction rule for PR comments and alerts; GitHub App tokens and keys covered (#238)

**Why:** found while the agents' GitHub App (F-30) was set up - GitHub announced that App installation tokens are moving to a longer `ghs_` format (about 520 characters, with dots). Agent 3's failure note and the pipeline health alerts each had their own copy of the redaction rules, and both missed things:
- the token pattern knew `ghp_`, `gho_` and `github_pat_` only - not `ghs_` (App), `ghu_` or `ghr_` - and stopped at a dot;
- the two copies named different secrets (the health alerts missed `APP_PASSWORD`; neither named `JIRA_EMAIL`, `APP_USER_REGISTERED` or `GH_APP_PRIVATE_KEY`);
- a private key quoted in an error was caught only by its exact value, and not if cut off;
- found by the deliberate-break checks of this change: `Key=\S+` also swallowed the comma, bracket or full stop after a gateway's key alias.

- `core/redaction.py` (new): `redact()` - every credential the workflows pass (`SECRET_ENV`, longest value first), every token shape at any length, a private key block whole or cut off, a `Key=` alias up to its closing punctuation, emails
- `agents/agent3_reviewer.failure_note` and `core/health_checks._redact` both call it
- `tests/unit/test_redaction.py` (17), including a guard that fails when a workflow passes a secret `SECRET_ENV` does not name
- Verification: 13 deliberate breaks (a secret dropped from the list, a token kind, the length or the dot, the key block whole or cut off, the alias, emails, the length threshold either way, the longest-first order, either caller bypassing the rule) - every one fails a test

---

## October 2026 (end) — every action waits for the page to finish loading; a slow resource no longer fails a navigation; a failed row wait names the page's requests (#239)

**Why:** on 28 Oct, 4 of 8 Agent 4 runs failed cart scenarios that had been green for days (defects SCRUM-268 to SCRUM-271 raised by the triage), with no change to the tests. The trace of one (attached by the repository owner) settled it: the product page was reached by a CLICK; its heading was visible at +11.5 s and the test clicked its add button at +11.5 s, but the script that handles the button finished downloading at +19.1 s (the site's scripts took 7 to 10 s each that morning). The click went to a button nothing was listening to: no add request was made, the confirmation never showed, and on the retry a remove click on the cart page failed the same way. `navigate()` never had this gap - `page.goto` waits for the load event - but a page reached by a click was only waited for up to its element. The remove's failure was also triaged "unclassified": a wait for a row to go carried only Playwright's call log, while `wait_visible` already listed the page's action requests.

- `pages/base_page.py`:
  - `_wait_for_page_scripts()`: before driving the browser, every action helper (31 call sites: click, fill, select, check, hover, drag, upload, click_in_row, click_nth, in-frame actions, ...) waits for the document's load event. One round trip when the page is already loaded. Bounded and fail-open: a page that never finishes loading is acted on after the timeout, as before, with a warning, and that document is not waited for again; a page mid-navigation is left to the action's own wait
  - `navigate()` (found by this PR's own Agent 4 run, which then failed `Page.goto: Timeout 30000ms exceeded ... waiting until "load"` on the home page, first try and retry): a page counts as served once its document is parsed (`domcontentloaded`); the load event is then waited for the same bounded, fail-open way, so one slow resource no longer fails a page whose HTML arrived. A page not served in time is retried like a 5xx - the pending navigation cancelled first, since Chromium aborts a second goto to a URL still loading (`net::ERR_ABORTED`, proven) - and if it never is, the error says "was not served in time ... The page did not load": an outage (`core/failure_diagnosis.py`), reported apart and never a defect, not the generic "timed out" reading about an element not actionable
  - `_network_evidence_on_failure()`: `wait_for_row`, `wait_for_any` and `wait_hidden` failures keep Playwright's message first and add the page's action requests and their outcome, as `wait_visible` does
- `tests/unit/test_act_after_page_load.py` (23), including:
  - a guard that fails when a BasePage helper drives the browser without the wait first
  - the race reproduced in a real Chromium against a local page whose script arrives late: without the wait the click is lost (no request); with it the request is made and the confirmation shows
  - in Chromium, a page whose image holds the load event is navigated to and used; a page never served fails as an outage after a retry that reached the server as a fresh request
  - the four fake pages of earlier navigation tests accept `wait_until` (test doubles only)
- Verification: 13 deliberate breaks (click or click_in_row not waiting, the wait never waiting, DOMContentLoaded instead of load, no memo, a navigating page raising, a row wait losing its evidence, Playwright's message dropped; goto waiting for load again, the pending navigation not cancelled, navigate skipping the load wait, the outage rule or the diagnosis missing) - each fails a test. Full unit suite passed.
- Not in this change: the four auto-raised defects stay open until main passes again - the triage then labels them for closing

---

## October 2026 (end) — the nightly inventory check says what it matched, checks the login page, and fixes a one-element drift by tightening, never by silencing (#237)

**Why:** the pipeline health issue reported *Inventory Health* failing three nights in a row (25-27 Oct). Its report read `AMBIG(2)` for one key and no more, so finding the two elements needed a local reproduction; and it showed the login page as "did not render" every night - the verifier signed in first, a signed-in browser is sent away from the login page, so its selectors had never been checked. The log also began with a `SyntaxWarning: invalid escape sequence '\s'`.

- `scripts/verify_locators.py`: an unexpected multi-match (`AMBIG`, `BACK`) lists up to five matches - tag, id, classes, shown or hidden, text (`_describe_matches`, `_DESCRIBE_JS`; proven in real Chromium on a page with the same shape). The page at the login path is verified signed out, before signing in, and skipped after (`signed_out_pages`); a root that is only a fallback guess is not treated as a login page
- `inventory_tools/browser.py`: the DOM-snapshot JavaScript is a raw string - the same script, no invalid escape (proven byte-for-byte)
- `tests/unit/test_inventory_health_report.py` (12, 8 of which fail on the previous code), including a guard that no source file carries an invalid escape
- GUIDE (*Measure - verify_locators*)
- **The drift itself, and why it would recur (run #90 on the branch named both matches):** the site added a visible `<span>All Products Catalog`; the inventory's `text=All Products` is, in Playwright, a case-insensitive *substring* match, so it caught the span as well as the `<h2>` heading. Worse, the report header and the verifier's suggestion advised declaring such a key `multi_match` - which silences a one-element key instead of fixing it, so the next similar change would slip through the same way. Now:
  - the inventory key uses the exact form `text="All Products"` (proven in Chromium: one match, the h2), with a dated note on why
  - `exact_text_form` + `_count`: for an ambiguous contains-match `text=` key, the report prints a `fix:` line with the exact form when that resolves to one element
  - every run lists, as a note and not a failure, the keys whose contains-match `text=` selector could already be tightened the same way (families and conditional keys are never listed) - so the other 15 such keys are measured before they are changed, not changed blind
  - the family suggestion now leads with "meant to be ONE element? tighten it - never declare it a family to silence it", and leaves out keys with a `fix:` line; the report header, `inventory_readme.md` and the GUIDE say the same
  - tests: 24 in `test_inventory_health_report.py` (12 new)

---

## October 2026 (end) — the agents' GitHub App settings are named GH_APP_*, and its set-up walked through (#236)

**Why:** #235 named them `APP_CLIENT_ID` and `APP_PRIVATE_KEY`, beside the application under test's login secrets `APP_USER_REGISTERED` and `APP_PASSWORD` - a reader could take the App's key for part of the application's credentials. Raised by the repository owner while setting the App up, before either was stored.

- The variable is `GH_APP_CLIENT_ID`, the secret `GH_APP_PRIVATE_KEY` - `GH_` like `GH_PAT` and `GH_REPO`: GitHub's, not the application's. Every workflow, the identity action, the redaction lists, the tests and the docs use the new names; GUIDE says why
- Nothing to migrate: neither had been stored yet
- GUIDE → *Agent identity*: the set-up as a screen-by-screen walkthrough (Parts A-F, 23 steps) written while the owner set the App up - which of the long permission rows to change and which to leave (the "Agent ..." rows, Metadata), where the private key goes (downloaded at once; *Key pairs*, not *Client secrets*), why no bot shows until the App first acts, the ruleset's bypass, how to check the run, and how to undo

---

## October 2026 (end) — the agents write as their own identity: a GitHub App (P4, F-30, #235)

**Why:** the agents wrote to the repository with `GH_PAT`, the reviewer's own token, so the reviewer was the author of every agent pull request (N10, PR #221). GitHub lets no author request changes on or approve their own pull request: the review fix's *Request changes* trigger could never fire (only `/fix` worked), merging needed a ruleset bypass, and a required approval (F-26) was impossible. The token also expired and had to be rotated by hand.

- `.github/actions/agent-identity` (new, a composite action): with the variable `APP_CLIENT_ID` (and the secret `APP_PRIVATE_KEY`) it creates a GitHub App installation token for this repository with `actions/create-github-app-token@v3` - contents, pull requests and issues write, actions read; one hour; revoked at the job's end. Without the App it gives `GH_PAT`, with a warning in the run. A configured App that cannot make a token fails the step (never a silent fallback). Outputs `token` and `kind` (`app` / `personal`)
- Every job that writes as the agents takes its `GITHUB_TOKEN` from it: Agent 0's scan, reconcile, code-change (the step taken from the `base/` checkout, never the pull request's `head/`) and drift; Agent 2 and its review fix; Story Done on merge (now `timeout-minutes: 30`); the pipeline health check; the sweeper. `agents/` is unchanged: the identity is a credential
- `core/health_checks.repo_host_findings(per_run=)`: a token created per run (`REPO_HOST_TOKEN_PER_RUN`, from the step's `kind`) has no expiry to warn about, and an earlier expiry alert closes; a refused token is still an alert
- `APP_PRIVATE_KEY` added to the values Agent 3's failure note and the health alerts redact; `APP_CLIENT_ID` is an identifier (a variable - `test_workflow_secrets.py`)
- Workflow comments no longer say the agents push with `GH_PAT`
- **Security, found by actionlint on the way:** Story Done on merge pasted the pull request's branch name into its shell script; a branch name may hold shell syntax, and the job holds the secrets. It now reaches the script as an environment variable. `tests/unit/test_workflow_injection.py` fails on any `run:` script that pastes contributor-chosen text (branch names, titles, bodies, messages - actionlint's untrusted fields), and runs actionlint itself where it is installed: every workflow passes
- Tests updated: `test_context_additions.py`, `test_inventory_update.py` (the proposal steps take the identity step's token), `test_test_track.py` (the not-built group has a fixed name, *Not built yet*)
- Docs: README (secrets, troubleshooting), GUIDE (new *Agent identity* with the App's set-up steps, Route 2b, branch protection, the environment table, the sweeper, troubleshooting a token not created), TECHNICAL_DEEP_DIVE (9.6, the review fix), REUSE_FOR_NEW_PROJECT (Change 9; the agents' identity on GitLab, Azure DevOps, Bitbucket), DECISIONS ADR-025 (and a note on ADR-008), VALIDATION_AND_KNOWN_GAPS (N10 closed, F-30 done, L47, L48), TEST_TRACK (TG-10: E36a-g)

Pinned by `tests/unit/test_agent_identity.py` (47: every agent job found and wired, no step writing with `GH_PAT` directly, the step only from trusted code, every agent job inside the token's hour, the action's permissions, fallback, warning and failure, the health check's per-run token, the review fix's trigger and its own replies). `test_workflow_injection.py` (13). 15 deliberate breaks, each caught. **Not proven live: the App itself** - it is created by the repository owner (TEST_TRACK E36a-g).

---

## October 2026 (end) — a story says each thing once (P4, F-31, #234)

**Why:** a story's comments were mostly the agents' own bookkeeping (N11). On SCRUM-187, 41 of 71 comments were `[LLM-USAGE]` / `[LEDGER-RESET]`; each agent run posted its cost and every Agent 5 report repeated all of it as a table that grew by one row per run. Agent 0's report on a change story copied the Impact Review's data block; a re-analysis posted its delta and its report as two comments; the no-Component note repeated the report's own line; Agent 0's outcome was a second comment at the moment Agent 5 reported. Watchers were emailed for each. And a story whose budget hold a person released read over 100% of one budget (L40).

- **The property ledger** (`core/usage_ledger.py`): each run is the hidden issue property `llm.usage.<time>.<id>`, a new attempt `llm.reset.<time>.<id>`, a budget hold `llm.hold.<time>.<id>`. The story shows ONE cost comment per attempt, edited in place after every run (`refresh_cost_comment()`, `render_cost_comment()`): a row per agent with its modes and run count, the total, the story budget. Posted again when a person deletes it; never a new comment per run when an edit is refused; a render that missed a concurrent entry renders again. A reset closes the old comment with a line saying why. `story_ledger()` reads either store: a story's `[LLM-USAGE]` comments count until its first property reset. `has_usage()`, `spend_budget.begin_story()` and Agent 5 read through it
- `mode()`: the property ledger when the tracker has issue properties and `update_comment` and `usage_ledger.store` (new, `auto`) is not `comments`; otherwise the comment ledger, unchanged
- **Agent 5:** one cost line linking the cost comment instead of the table (property ledger); Agent 0's outcome measured before the report and shown as its line, kept once as `agent0.outcome.<hash>` (`record_outcome(save=False)`, `save_outcome()`, `outcome_recorded()` - an old `[agent0:outcome]` comment still counts); a re-run on the same commit with the same results posts nothing and calls no model (`report_fingerprint()`, property `agent5.report`), its flakes recorded only when it is another run of the tests
- **Agent 0:** with an Impact Review, the story's report keeps its readable table and points to the review for the data block (`_render_report(data_in=)`); a re-analysis's delta is the report comment's second line (`_with_delta()`), on its own only when an approved review stands; the no-Component advice is in the report's line, no separate comment
- **L40:** `spend_budget.allowance()` shared by the budget and the budget line, which reads "raised after a budget hold" for a released story
- **Tracker capabilities** (optional, `integrations/tracker.py`): `properties(issue, prefix)` (one request, `?properties=*all`) and `update_comment(issue, ref, body)` - Jira edits without notifying where the account may (a project administrator), otherwise with the notification; `LookupError` when the comment is gone. `core/dry_run.py`: the capabilities that only read pass through (`CAPABILITY_READS`)
- Not done, on purpose: the "no update needed" notes stay (the only record of that check); D7 is not needed (the cost comment shows a stopped story's cost)
- Tests updated: `test_usage_per_story.py` (a tracker with the Protocol only), `test_p2_scan_end_to_end.py`, `test_a_series_open_items.py` and `test_spend_budget.py` (both stores), `test_agent0.py` (the delta in the report, the data in the review, no separate no-Component comment, the outcome kept once in either store), `test_test_track.py` (the not-built group is TG-10; a built fix may not stay in it)
- Docs: README, GUIDE (cost tracking, Agent 5 steps, budgets, config, marker table, new hidden-properties table, troubleshooting), TECHNICAL_DEEP_DIVE (Agent 5, the ledger, the capability table), REUSE_FOR_NEW_PROJECT, AI_CONCEPTS (#52), DECISIONS ADR-024, VALIDATION_AND_KNOWN_GAPS (N11, L40 closed; F-31 done; L43-L46), TEST_TRACK (TG-9: E35a-k; E3, E32d, H5)

Pinned by `tests/unit/test_comment_dedup.py` (26: both stores, the cost comment and its edits, a reset, an old story, a deleted or refused comment, a concurrent run, the quiet-edit fallback, L40, Agent 5's line, re-run and outcome, the dry run, a reset of a story costed before, and a whole story - 4 comments where the comment ledger posts 16). 24 deliberate breaks, each caught.

---

## October 2026 (end) — production readiness: health issue, nightly run and defects, outages and flakes, spend budgets (P3)

**Why:** the pipeline could stop or overspend without anyone being told. No run tested `main` unless a PR opened (N1); a test failing on `main` reached nobody (N2); a scheduled agent failing in a row or a refused / expiring credential was only a red run in the Actions tab (N3); nothing limited model spend, and a spent provider budget stopped every agent at once (N4). A failure the application's outage caused read like a test failure (L14), and a failure was final on the first try with no count of flakes (L22).

- **F-23:** `core/pipeline_health.py` - one tracker issue (found by `pipeline-health`, created when first needed, the oldest wins), watched by the team: `[health:open] <id>` / `[health:resolved] <id>` comments only on a change, the description as the current picture, append-only records (one new issue property per record). `core/health_checks.py` + `scripts/pipeline_health_check.py` + `pipeline_health.yml` (08:50, 12:50, 16:50 IST): scheduled workflows read from the workflow files, `consecutive_failures` failed scheduled runs in a row; the repo host token and its expiry (GitHub header); the model endpoint (one-token call, or a free listing); a refused tracker fails the run; an alert for a workflow no longer scheduled closes. Tracker OPTIONAL CAPABILITIES (`create_issue`, issue properties, `check_access`) via `integrations.tracker.capability()` - not in the Protocol, so existing adapters stay valid; JiraClient and FakeJira implement them; `RepoHost` runs may carry `event` / `created_at` / `url`; `GitHubClient.check_access()`. `core/ops_settings.py` reads the four new config blocks over defaults
- **F-7:** `core.failure_diagnosis.is_outage()` (failure text only, never a captured log) and a named diagnosis for a page load refused on every attempt; `scripts/finalise_junit.py` marks `outage` in junit.xml; `core/junit_marks.py` is the one reader. Run summary: own row and section; Agent 5: `TestResult.outage`, *Not judged* warning and section, verdict `unavailable`, never an outside failure, no model call when nothing could be judged; Agent 3: outcome `outage` (no evidence); owners' result lines "not judged"
- **F-19:** the E2E step keeps pytest's exit code; *Retry failed tests once* (`--last-failed`, at most 10); `finalise_junit --retry` merges (`flaky`, `outage_recovered`, `retried`, `first_failure`); *Decide the E2E result* fails the job on what still fails; test job timeout 40. `core/flaky_tests.py` records each flake on the health issue (no comment); the summary and Agent 5 name them; Agent 3 reads green runs too, and a flaky scenario refutes no prediction
- **F-21:** `agent4_runner.yml` nightly on `main` (03:10 IST), its own concurrency group; the wait step lists every event and `scripts/e2e_turn.py` takes turns with `schedule` runs
- **F-22:** `triage` job after every run on `main` (schedule, manual on main, a push that ran the E2E): `scripts/triage_failures.py` + `core/defects.py` - one defect per test and cause (`ai-defect-<hash>`), owner from the marker, repeat updates without a comment, `ai-defect-passing` + one comment when it passes (not on a flaky pass), never closed by the pipeline; `max_new_per_run`; outage, flood and missing-report health alerts
- **F-24:** `core/spend_budget.py` checked in `LLMClient._call_with_quota_check` before every call; `BudgetExceeded(BaseException)`; per story (ledger since the last reset + this run; `budget-hold` label + one `[budget:hold]` comment; removing it allows one more; a ledger reset restarts it), per day (every process's spend recorded at exit as `spend.<day>.<micro-USD>.<unique>` on the health issue; warn and limit alerts; past days' alerts closed and old records pruned by the health check); `llm_client` lifetime counter; scans defer for the day (green) and fail a held story once; Agent 3 *Not reviewed: model budget reached*; Agent 5 code-written prose and a story-budget line; review fix pushes nothing and says why; every selection (config and Agent 0's defaults) excludes `budget-hold`. CI only (`PIPELINE_BUDGET=on/off`); without prices nothing is enforced
- Tests updated: `test_in_flight.py` (the wait step's guard and the runs listing), `test_review_scenario_evidence.py` (a green run's report is read now), `test_impact_handover.py` defaults (Agent 0's selection excludes `budget-hold`)
- Docs: README, GUIDE (Agents 4 and 5, what runs per event, labels, config, cost, CI schedule, test suites, new *Operating the pipeline*, onboarding step 8, troubleshooting), TECHNICAL_DEEP_DIVE (layout, Agent 4 steps and triage job, Agent 5, llm_client, the adapters' optional capabilities, labels, schedules), REUSE_FOR_NEW_PROJECT (Change 8), DECISIONS ADR-023, VALIDATION_AND_KNOWN_GAPS (N1-N4, L14, L22 closed; F-7, F-19, F-21-F-24 done; L35-L41; N11 and F-31 for P4's comment de-duplication; E27-E32 in UC-7; P1-4 / P2 rows now cite #229 / #230)

Pinned by `tests/unit/test_pipeline_health.py` (48), `test_outage_reported_apart.py` (32), `test_flaky_retry.py` (26, one a real pytest run and `--last-failed` retry), `test_defect_triage.py` (23), `test_spend_budget.py` (36) and `test_p3_night_end_to_end.py` (1: two nights on main through the finalise, verdict, triage and health-check scripts) - 166, plus 5 in updated files; 41 deliberate breaks, each failed a test.

---

## October 2026 (end) — story state and scans (P2)

**Why:** running several stories per scan, and several changes at once, left six gaps: a failed story's cost landed on the next (M1); up to six stories in a 10-minute Agent 2 job (M2); a page-object edit no plan named, or a PR opened during generation, unchecked (G1); two change stories revising one test case (G2); Agent 3 giving up on a queued runner result (M3); a new story whose PR closed unmerged left coded and In Review (G8).

- **F-3:** `core.usage_ledger.story_usage()` around every story Agents 0, 1 and 2 run - counter at zero; a failed run posts `<agent> (failed)` on its own story; `has_usage_comments()` reads it as that agent
- **F-1:** `agent2_coder._last_in_flight_check()` - a fresh snapshot of the open PRs against every file the batch commits, after the final gate, in `run()` and `run_update()`
- **F-2:** `_owners_and_blocks()` also blocks by `impact-applied` stories and other open reviews listing the test (`_claimed_by_open_reviews()`); `impact_handover` refuses a test another change is still revising (`_revised_elsewhere()`), so the scan waits and retries
- **F-16:** `impact_reconcile.reconcile_unmerged_story()` / `_reset_unmerged()` / `reconcile_one()` - a coded story's PR closed unmerged on `closed_scans` scans → `reconcile.story_reset_labels` off, `status_workflow.on_close_unmerged` (To Do, `board_status.move_card_on_close_unmerged()`), retry comment; `reconcile_all()` lists only acted-on stories
- **F-4:** `agent2_coder.plan_scan()` - one `max_stories_per_run` budget for the three passes; `scan_deadline_minutes` (12); `[DEFER]`; `agent2_coder.yml` timeout 25
- **F-5:** `agent3_reviewer.RUNNER_WAIT_SECONDS` = `E2E_TURN_CAP_SECONDS` (900) + `E2E_RUN_SECONDS` (480); `agent3-reviewer.yml` timeout 30; M4 burst size documented
- Tests: `test_only_the_normal_scan_pass_skips` checked `main()`'s source text; it now runs the scan
- Docs: README, GUIDE (Agent 3, Agent 0 analysis and hand-over, reconcile, board, config, in-flight, cost, troubleshooting `[DEFER]` / closed PR / hand-over waiting, label table), TECHNICAL_DEEP_DIVE (Agent 3, §9.9, §18.5, config, labels), DECISIONS ADR-022 (+ a later note on ADR-014), VALIDATION_AND_KNOWN_GAPS (G1, G2, G8, M1-M3 closed; M4 documented; L3, L6 updated; F-1-F-5, F-16 done; UC-5 rewritten step by step; E26)

Pinned by `tests/unit/test_usage_per_story.py` (11), `test_last_in_flight_check.py` (7), `test_change_in_progress.py` (10), `test_reconcile_new_story.py` (18), `test_scan_budget.py` (7), `test_runner_wait.py` (4) and `test_p2_scan_end_to_end.py` (1: one Agent 2 scan through the real `run()`) - 58; 30 deliberate breaks, each failed a test.

---

## October 2026 (end) — planned inventory entries, new pages, shared elements listed once (P1-4)

**Why:** the inventory comes from the live crawl and Agent 2 may use inventory keys only, so a test for an element not deployed yet could not be written (L19); a new page was never crawled and nothing said it existed (L25); and the first nightly inventory-update PR (#228) proposed a footer field - already one page's key - again on four other pages (G14).

- **Shared (G14):** the crawl marks other pages' live keys on each page with their owner (`SHARED_ATTR`, `collect_uncovered(shared=)`); `uncovered_entry()` returns them as `shared`; the update lists them (*Not added - already covered on another page*) and never adds them. A new element on every measured page (`inventory_update.layout_min_pages`, 3) is listed once (*Not added - new on every page: a shared section*), not added per page - found by a real-browser run of this change
- **Planned (F-12, L19):** page list `planned`, page flag `planned_page`; `core/inventory_planned.py` + `scripts/plan_inventory.py` add them with the shared refusal rules; `diff_page(declared_planned=)` → `planned_live` / `planned_waiting`, never `missing`; the update never treats a planned key as stale, confirms a live one (not on a held page), skips a planned page until one of its planned keys is live, then adds its live elements (L25); `verify_locators` `PLAN` / `LIVE` / `PLANNED PAGE`; `promote_draft` prunes `planned`; `onboarding` warns on unconfirmable entries; Agent 2's PR lists *Uses planned elements - not deployed yet* (`uses_planned` in the result)
- **Unlisted pages (L25):** `introspect.unlisted_paths()` - same-origin links matching no inventory url or `{template}` - listed in the PR body
- Tests: two fakes of `collect_uncovered` take the new `shared` keyword
- Docs: README, GUIDE (the update's table, planned entries, the inventory fields), TECHNICAL_DEEP_DIVE (layout, inventory update), `inventory_tools/inventory_readme.md`, REUSE_FOR_NEW_PROJECT, DECISIONS ADR-021, VALIDATION_AND_KNOWN_GAPS (L19, L25, G14 closed; F-12 done; L32-L34; E25 for UC-7)

Pinned by `tests/unit/test_inventory_planned_shared.py` (40); 35 deliberate breaks, 34 failed a test (the survivor is equivalent: a same-page filter the next condition also enforces). Validated end to end with a real Chromium against a local site in three phases - before deployment, a placeholder at the planned url, after deployment - running the real crawl, update, `verify_locators` and `plan_inventory`: 37 of 37 checks passed. The browser part is kept as an opt-in test: `INVENTORY_E2E=1 pytest tests/integration/test_inventory_update_local_site.py` (not in CI: it needs a browser).

---

## October 2026 (end) — no approved test case is dropped in silence (P1-3)

**Why:** when Agent 2 could not automate an approved test case, the model left it out and said so in the plan's `notes`, printed only in a dry run; marker injection logged a warning; the story still got `ai-coded`. The duplicate check's title clash and `ai-update`'s unmarked match were logged the same way (G5).

- **`agents/agent2_coverage.py` (F-13):** `missing_from_batch()` - each test case the run was given with no markered scenario, with the plan's `Skipped: <KEY> -- <reason>` line (`notes_about()`), or the cause when its key cannot be held by a marker; `skipped_gaps()` - the dedup's `title_clash` (not covered), `modified` and `legacy` (covered, need a person); `unmarked_scenarios()`; `pr_section()`, `comment()`, `record()` (one `[agent2:incomplete]` comment; `ai-incomplete` set, or cleared - only when present)
- **`run()`:** coverage after marker injection and the change-story splice, over the story's own files; a run covering none of its new test cases (and no change-story work) is refused by the final gate (`GateFailure` → `core.blocked`); the PR body gets the section; the story is told BEFORE `ai-coded`; the no-work path reports a title clash too; dry run prints it; `not_automated` in the result and the scan summary
- **`run_update()`:** the same rule for the file it updates - a generated scenario that lost its marker is missing, an unmarked legacy match is listed, not appended or counted; only unmarked scenarios the update added are listed; the label is cleared when nothing is uncovered (also on a no-op)
- Config: `agents.agent2_coder.incomplete_label: "ai-incomplete"`; `reconcile.reset_labels` adds it (config and `impact_settings.DEFAULTS`). Plan prompt: every test case left out gets a `Skipped: <KEY> -- <reason>` line. `core.blocked`'s comment names both refusals
- Tests: the in-memory tracker of `test_pipeline_tool_agnostic.py` minted keys (`ACME-T1`) no marker can hold - now `ACME-201`; its pipeline run's fake model wrote one scenario for two test cases - now two
- Docs: README, GUIDE (Agent 2 steps, label tables, config, troubleshooting), TECHNICAL_DEEP_DIVE (§5.7, §5.8, §5.11, labels, §11, §16), REUSE_FOR_NEW_PROJECT, DECISIONS ADR-020, VALIDATION_AND_KNOWN_GAPS (G5 closed, F-13 done, L30, L31, E24 (a)-(e) for UC-7; P1-1/P1-2 rows now cite #224/#225)

Pinned by `tests/unit/test_no_silent_drop.py` (24); each rule was broken on purpose (25 mutations), and each break failed a test.

---

## October 2026 (end) — the app notes follow every story, and stay small (P1-2)

**Why:** the context update ran only at a change story's hand-over and could only replace wording or rewrite untrue passages. A new feature never reached `prompts/app_context` (the next story on it was drafted from its own text alone); an element a change story removed stayed in the inventory as "stale" every night after deployment, raising its absence test as affected; the rewrite call read every module whatever the story touched; and nothing measured the notes, which go into every prompt.

- **F-10 - one selection rule:** `core.app_context.select_note_modules()` (core.md + the story's Component modules, all when none match) and `selected_page_names()`; Agent 1 calls it (behaviour unchanged); the change-story rewrite call reads only that scope (`scoped_sources()`, `_notes_block(pages=)`), and a rewrite of a file it was not shown is dropped
- **F-8 - additions at merge:** Story Done on merge runs `scripts/propose_context_addition.py` after moving the card; `propose_addition_for_story()` makes one call (`prompts/agent0_context_additions.md`, `NoteAddition` / `NoteAdditions`) over the story, its test cases, its merged scenarios and its scoped notes; `propose_additions()` places facts under a heading, as a new section or a new Component module, refuses other files and the inventory, and drops every line the notes already state (`near_duplicate()`); PR on `context-update/<key>-notes-<hash>`, `[agent0:context-addition]` marker, once per content of the story and its test cases (an `ai-update` that edits only the test cases is proposed again); cost on the story
- **F-11 - removed elements declared:** `NoteRewrites.removed` (`page.key`, from element keys - never selectors - the call is shown); `_declare_removed()` adds each valid one to the page's `removed` list; `introspect.diff_page(declared_removed=)` reads missing as expected and present as `reappeared` (drift); `verify_locators` `GONE` / `BACK`; Agent 0 seeds only a reappeared one; the inventory update retires a still-gone key no code names (never the row family); `promote_draft` prunes it
- **F-9 - size budget:** `context_update.module_budget_chars` (8000); the unit suite fails on a committed module over it; `notes_report()` lists over-budget modules and repeated sentences in the notes PR; `core.onboarding.notes_checks()` warns; `_paragraphs()` joins hard-wrapped lines so sentences, not fragments, are compared
- Docs: README, GUIDE, TECHNICAL_DEEP_DIVE (§9.7, §18.4, tree), REUSE_FOR_NEW_PROJECT, AGENT0_ONBOARDING (step 6), `inventory_tools/inventory_readme.md`, DECISIONS ADR-019, VALIDATION_AND_KNOWN_GAPS (L15, L16, L17, L18 closed; F-8, F-9, F-10, F-11 done; L27-L29; E20-E23 for UC-7)

- **Found by this PR's own review:** Agent 3 failed on it with no comment - every changed file went into the prompt whole, and the large guides made it ~964,000 characters (~241k tokens). `format_changed_files_for_prompt()` now shows a file no test reads while it runs (`prompts/`, `docs/`, Markdown - `core.test_runtime`) as its diff, and caps the section at 300,000 characters, the largest full contents falling back to their diffs first; this PR's prompt is now ~86k tokens. Test-code PRs are shown exactly as before (byte-for-byte on PRs #214, #217, #221, #223). A review that fails now says so on the PR (`failure_note()`: the error, every configured secret value redacted) instead of leaving a red check and no comment

Pinned by `tests/unit/test_context_scope.py` (16), `test_context_additions.py` (34), `test_removed_elements.py` (21), `test_notes_budget.py` (11) `test_review_prompt_budget.py` (6) and `test_review_failure_note.py` (5); each P1-2 rule was broken on purpose once (26 mutations), and each break failed a test.

---

## October 2026 (end) — the nightly crawl proposes the inventory update as a pull request

**Why:** the drift job measured stale selectors and uncovered live elements every night, but nothing wrote the inventory back. A new feature's elements never reached it - so Agent 2, which may use inventory keys only, left those test cases out - dead keys stayed, and a changed selector waited for someone to run the proposal scripts by hand.

- `core/inventory_update.py` (pure) and `scripts/propose_inventory_update.py`, a new step of the Agent 0 drift job (`if: always()`, `GH_PAT`): one proposal at a time on a dated branch `inventory-update/<date>`. A stale key is **replaced** when the crawl finds the element the generator names the same with a durable selector, **removed** when no code names it - on `main` or on an added line of an open pull request - and it is not the row family (its note and `multi_match` / `conditional` entries too), otherwise **kept** and listed; uncovered live elements are **added** with the generator's declarations (`multi_match`, `conditional`) under the proposals file's refusal rules, at most `max_additions_per_page` per page; elements the generator flags for review (no durable handle, `>> nth=` members, hidden when crawled) are listed, never added; a page with more than `hold_ratio` of its selectors stale is **not edited**. Ambiguous selectors, unreachable pages and untracked test-ids are listed. The file keeps its own JSON format, so the diff is the change
- One proposal: the same findings leave it alone; new findings close an untouched proposal (`RepoHost.close_pull_request`, new; branch deleted best-effort, since a repository may forbid deletion) and open a fresh one on a new dated branch; nothing left closes it; a proposal a person committed to - or any PR on the prefix without the marker - is never touched and no second one opened (one `kept-edited` comment per finding). Nothing is proposed or closed for a crawl that measured no page or a report older than `uncovered_max_age_hours`; no key is removed when the open pull requests cannot be read; `--dry-run` and Agent 0's shadow mode print the PR body; each body table is capped at 60 rows. No model
- `check_inventory_staleness --compare` also writes `new_element_declarations` (`introspect.uncovered_entry()`; `uncovered_elements()` unchanged). `core/inventory_proposals.refusal_reason()`: the one refusal rule for both writers. `RepoHost.close_pull_request` (20 operations; adapter, dry-run classification, both fakes); `list_open_prs(strict=True)` raises a read failure instead of returning a partial list, so the inventory update never mistakes "could not read" for "none open" (the default stays best-effort for its other callers). Settings `agents.agent0_impact.inventory_update` (defaults in `core/impact_settings.py`, equal to the shipped block)
- Docs: README (Agent 0, schedule table, tree, inventory health, RepoHost 20), GUIDE (inventory update section, drift row, config, markers, troubleshooting; the drift section no longer says Inventory Health runs `check_inventory_staleness`), TECHNICAL_DEEP_DIVE §9.6 RepoHost table, §18.1, §18.6 and the file tree (also `acceptance_coverage.py`, `blocked.py`, `collapse_junit_reruns.py`, which were missing), REUSE_FOR_NEW_PROJECT, `inventory_tools/inventory_readme.md`, DECISIONS ADR-018, VALIDATION_AND_KNOWN_GAPS (G12 closed, L18 and F-11 narrowed, L25, L26, E19; G11 credited to #215)

Pinned by `tests/unit/test_inventory_update.py` (50 tests: each rule above, flip-flop prevention, open-PR keys and their failure, report age, file format and the real inventory's byte-for-byte round trip, body limits, the PR's open / same-day / unchanged / superseded / closed / undeletable-branch / person-edited / unmarked / duplicate / failed-write paths, the script's empty, old, dry-run, shadow, no-host and live paths, the workflow step, config = defaults, the new RepoHost write, the adapter's strict listing, no duplicate proposal on an unreadable list) and `tests/unit/test_check_staleness_compare_flag.py::test_compare_records_the_generators_declarations_for_uncovered_elements`. Each rule was broken on purpose once to confirm a test fails.

---

## October 2026 (end) — `/fix <text>` also takes the open inline comments; a skipped event cannot cancel a waiting `/fix`

**Why:** found in the live E18 run on PR #221. `/fix <text>` acted on its text alone, so a reviewer who left inline comments and then wrote `/fix please address these` had every inline comment ignored - Agent 2 answered only the sentence. (In the run the text was an attribution footer the posting tool appended; a person's own words fail the same way.)

- `agents/agent2_review_fix.py` `collect_items()`: a `/fix` comment takes every inline comment no earlier summary lists, then its own text if any; a bare `/fix` is unchanged. A review is unchanged (its own inline comments, then its text). No new reach: a bare `/fix` already read those comments
- `.github/workflows/agent2_review_fix.yml`: the concurrency group moves from the workflow to the job. In the same run, Agent 2's three thread replies each fired a "review submitted" run; at workflow level those runs entered the group although the job's `if` skips them, and each cancelled the one waiting before it. A person's `/fix` posted while a fix was running would have been cancelled by Agent 2's own replies. A skipped job never enters a job-level group (the lesson Agent 4 learned on #178). The other workflows were checked: Agent 0's and Done-on-merge's groups cannot displace a run that matters
- Docs: workflow header, GUIDE (Agent 2), TECHNICAL_DEEP_DIVE §5.10, DECISIONS ADR-017

Pinned by `tests/unit/test_agent2_review_fix.py::test_fix_with_text_takes_the_open_inline_comments_and_the_text` (replaces the text-alone test) and `::test_only_a_job_that_runs_waits_its_turn`.

---

## October 2026 (end) — the review fix edits a regenerated story's own files

**Why:** the review fix took "added by this pull request" to mean "this story's file". An `ai-regenerate` or `ai-update` pull request rewrites the story's existing feature and step files, so they arrive as "modified" - and every comment on them would have been declined as "another story's file", leaving only page objects fixable.

- `agents/agent2_review_fix.py`: `feature_owned_by()` - a feature file is the story's own when every `# JIRA:` marker in it is one of the story's test cases and names no other owner; `owned_by_story()` - such modified feature files and their step files (`tests/step_defs/test_<stem>.py`) become editable. A file holding any other story's scenario (a change story's splice) stays protected; an unreadable file is not owned. Ownership is read from the markers on the PR's branch, never from the file status or a story name
- Docs: GUIDE (Agent 2, Route 2b, troubleshooting), TECHNICAL_DEEP_DIVE §5.10, DECISIONS ADR-017, README troubleshooting. They also note that GitHub does not let a pull request's author request changes: with `GH_PAT` as the reviewer's own account, Agent 2's pull requests are the reviewer's, so `/fix` is the route

Pinned by `tests/unit/test_agent2_review_fix.py` (32 tests; new: a regenerated story's modified files are editable, a feature holding another story's scenario or another owner's marker is not, a step file follows its feature, a comment on a regenerated feature is fixed and pushed).

---

## October 2026 (end) — Agent 2 fixes what a pull request's reviewer asks for

**Why:** no agent read a review comment. A reviewer who wanted one line changed on an Agent 2 pull request fixed it by hand - unchecked by the validators until Agent 4 ran - or added `ai-regenerate` and threw the whole pull request away.

- `agents/agent2_review_fix.py` and `.github/workflows/agent2_review_fix.yml`: a "Request changes" review on an `auto/*` pull request, or a `/fix` comment (`/fix <what to change>`, or a bare `/fix` for every inline comment not handled yet), from a person with write access - never a bot. One model call (`ReviewFixPlan`) decides fix / decline / no_change per comment; Stage 2's generator rewrites each named file in a new review mode (`generate_file_content(review_feedback=...)`: the current file shown whole, whatever its format); the repair loop and the final gate run over every code file of the pull request; the result is pushed to the same branch, so Agents 3, 4 and 5 run again. Each comment gets a reply in its thread and the pull request one `[agent2:review-fix]` summary, which also stops a second run on the same review
- Safeguards: only files the pull request added and page objects it extends (never another story's spliced files, reserved or framework files); a feature file keeps its scenarios, titles and markers; a comment asking to test something the approved test cases do not state is declined with the way to get it (update the test case, then `ai-regenerate`); a degraded regeneration is discarded; a gate failure, or a repair reaching a file that is not editable, pushes nothing; `review_fix.max_files` (6) caps one review
- `RepoHost` gains `get_review_comments` and `reply_to_review_comment` (19 operations; classified for dry runs); schemas `ReviewFixDecision`, `ReviewFixPlan` (24); config `agents.agent2_coder.review_fix`; prompt `prompts/agent2_review_triage.md`; ADR-017
- Docs: README, GUIDE (Agent 2, workflows, events, markers, config, troubleshooting), TECHNICAL_DEEP_DIVE, REUSE_FOR_NEW_PROJECT, VALIDATION_AND_KNOWN_GAPS (E18)

Pinned by `tests/unit/test_agent2_review_fix.py` (28 tests: every safeguard above, the workflow's guards, the generator's review mode, and a gate refusal that names each rule still broken).

---

## October 2026 (end) — the two gates agree on a quantity; a refused story stops retrying

**Why:** SCRUM-187's approved test case expected "a row for '<item>' with quantity 1" after signing in as the inventory's shared account. Agent 1's check let it through (it looked for "exactly", "only", a row count and "empty"); Agent 2's gate refuses an exact value read from a persistent page whenever the scenario signs in, because a run that stopped before cleaning up leaves the same entry behind and the next run reads 2. Four repair attempts failed on the same rule (about $2.50), nothing was written to Jira, and the scheduled scan retried the story every 30 minutes.

- `core/test_case_rules.py`: an exact quantity (`quantity 1`, `a quantity of 2`, `qty: 3`, `3 items`, `a total of 1500`) on a persistent page is rejected in a test case that signs in with a shared account - the inventory's `test_users`, named in the text or the test data. A test case that never signs in keeps its quantities (a fresh session starts empty), exactly where Agent 2's gate draws the line. Agent 1's normal and impact-aware drafts both apply it; without accounts the rule is off, as before
- `core/blocked.py`, Agent 2: when the final gate refuses a story, one `[agent2:blocked] inputs: <fingerprint>` comment lists the rules still broken and what to do. The scheduled scan's normal pass skips a story whose story and test-case text still match the fingerprint - no model call, `[BLOCK]` in the summary. Any edit to them retries on the next scan; a manual run with `story_key` always runs. `GateFailure` (a `ValueError`) carries the remaining errors
- `BasePage.click_in_row()` waits (default timeout) for a row with the text before calling it missing. It counted at once, so the first row action after a navigation - "View Cart", then delete a product's row - could read the page before its rows were drawn (this PR's own Agent 4 run, `test_cart_management`). A row that never appears still fails with the same message
- A failed E2E test names the temporary server errors its own requests met. This PR's next Agent 4 run failed two tests during a burst of HTTP 503: an add-to-cart call and a followed link were refused, and the steps after them failed with "row not found" and "element never appeared". Neither message named an HTTP error, and the re-run rule of #213 (`--only-rerun`) reads only the exception message, so neither was re-run. `pytest_runtest_call` in `tests/conftest.py` now restates a failure as `ApplicationUnavailableError` naming every 5xx/429 the test's action requests met and never recovered from (`BasePage` `unrecovered_server_errors()`, `with_server_errors()`); a request the server later answered (a retried page load) is not named. `core/failure_diagnosis.py` reads it as "application temporarily unavailable"
- Docs: GUIDE (troubleshooting, markers, failure recovery, Agent 4 steps), README troubleshooting, TECHNICAL_DEEP_DIVE §`core/blocked.py` and §7, VALIDATION_AND_KNOWN_GAPS (G11 closed, N4 narrowed, E16, L14 and F-7)

Pinned by `tests/unit/test_signed_in_quantity.py` (both gates on one sentence, signed in and anonymous), `tests/unit/test_blocked_story.py`, `tests/unit/test_click_in_row_waits.py` and `tests/unit/test_server_errors_are_named.py` (the re-run rule read from the workflow itself).

---

## October 2026 (end) — a temporary HTTP error from the application is retried (#213)

**Why:** from CI the application under test answered some requests with HTTP 503 in short bursts while it loaded fine in a browser. One run failed five of seventeen tests that way - four page loads and one add-to-cart request - none for anything the change did (L14).

- `BasePage.navigate()` retries a page load the server answered with a 5xx or 429, after the waits in `browser.navigation_retry_delays_ms` (config, default 3 s then 8 s; `[]` turns it off). A 4xx fails at once, as before; the final message names the attempts
- Agent 4 re-runs a BDD test whose failure names a 5xx or 429 - which covers an action's own request - up to twice, 20 s apart (`pytest-rerunfailures`, pinned; `--only-rerun`). An assertion, a 404 or a timeout is never re-run
- `scripts/collapse_junit_reruns.py` (Agent 4 step, always runs, never fails) keeps only each test's final attempt in `junit.xml`, so Agent 5's counts and Agent 3's per-scenario evidence see one result per test
- Docs: README and GUIDE troubleshooting, GUIDE Agent 4 and config, TECHNICAL_DEEP_DIVE §7, AI_CONCEPTS (#51), VALIDATION_AND_KNOWN_GAPS (L14 partly fixed, F-7 and L22 updated, E15)

Pinned by `tests/unit/test_outage_retry.py` (library application; 7 break-it proofs) and the updated `test_navigation_guard.py`.

---

## October 2026 (end) — Agent 3 judges a prediction on its own scenario (#212)

**Why:** PR #211 (SCRUM-206) stayed blocked on a finding that the add-from-card click would hit two controls in one card. That scenario passed on the commit; the run was red only because another test hit an HTTP 503 from the site - and a change story's PR is red by design before deployment. The helper the finding was about (`click_in_row`) documents that it clicks the visible copy, but the reviewer never saw its docstring.

- A red runner result now refutes each prediction whose own scenario passed: Agent 3 reads the run's `junit.xml` (artifact `pytest-report-<run id>`) and maps the finding to its scenario - the new optional `scenario` field on `ReviewIssue`, or a scenario quoted in its failure scenario. A green run refutes every prediction, as before. No scenario, no match, an unreadable report: the whole run decides, exactly as before. Security and "passes wrongly" findings are never refuted by a pass
- An outline's prediction is refuted only when every example passed
- `RepoHost.get_run_artifact_file()` (17 operations): one file from an artifact a run uploaded; `get_workflow_runs()` dicts carry the run `id`. Classified as a read for dry runs; GitHub adapter fails soft
- Agent 3's prompt lists every BasePage helper the PR's added page-object lines call, with its signature and docstring; a finding about a helper's behaviour must agree with it
- Docs: README, GUIDE, TECHNICAL_DEEP_DIVE (Agent 3, §9.6 adapter table, §9.7 schema table - 22 classes, missed in #209), REUSE, AI_CONCEPTS (#16 updated, #50 new; duplicate #48 from #209 renumbered to #49), ADR-016, VALIDATION_AND_KNOWN_GAPS (E14, G10 closed)

Pinned by `tests/unit/test_review_scenario_evidence.py` (library application; replay of the PR #211 shape; 7 break-it proofs).

---

## October 2026 (end) — every acceptance criterion verified by a test that can fail (#209)

**Why:** validation story SCRUM-206 removed a field; the revised tests stopped using it, nothing asserted it was gone, and every test passed against an application that still had the field (ADR-015).

**Agent 1 (both modes)**
- The acceptance criteria are read from the story text (`core/acceptance_coverage.py`: numbered, bulleted, checklist or Given/When/Then lists under an "Acceptance criteria" heading, wiki markup or markdown) and listed in the prompt as AC1, AC2, ...
- The draft returns a coverage map (`CriterionCoverage`, schema 22): every criterion with the test case(s) that verify it. A missing criterion or an unknown citation sends the draft back once; a second miss writes nothing
- Obligations, from the criterion's wording: removed / replaced / renamed / hidden / "no longer" / "no X is shown" needs a step asserting the old thing is absent, naming it; only X can / Y cannot needs the refusal; a limit or validation rule (at most N, required, valid format) needs the violation rejected
- Impact-aware: a revision counts only if it carries that step; an unchanged existing scenario may be cited for a criterion without an obligation (no duplicate drafted)
- The map is posted on the story (`[agent1:coverage]`) and in the impact-aware gate comment; both prompts carry the obligation table, now with a limit/rule row

**Agent 2**
- Three checks (`validators/absence_claims.py`, gate now 32 checks): a scenario keeps its test case's "is not shown" step; a Then step worded as absence asserts absence (a page-object method that answers absence counts, whatever its name); a new or changed absence predicate on a permanent element proves its page is loaded first (`return self.is_loaded() and self.is_gone(...)`). Committed code is not re-judged
- The single-scenario writer (`ai-update`, change-story splice) is told the test case's absence claims and retries once if it drops one
- Generation prompt: the feature-file rule, a section on proving something was removed, and rule 17 / the absence rule extended for permanent elements

**Docs:** README, GUIDE, TECHNICAL_DEEP_DIVE §4/§14/§19, AI_CONCEPTS (#49), REUSE, ADR-015, VALIDATION_AND_KNOWN_GAPS (E11–E13, UC-6, L24, L18/F-11 amended: keep and mark a removed element instead of deleting it).

All generic, pinned by `tests/unit/test_acceptance_coverage.py` and `tests/unit/test_absence_claims.py` (written for a library application; every guard has a break-it proof). Suite: ~3,080 tests.

---

## October 2026 (second half) — validation fixes after A3

**Agent 0's manual-run inputs mean what they say**
- "Print the report; write nothing" now reaches every job: the full scan (analysis and hand-over), reconcile and drift. The real code runs against tracker and repo-host wrappers that perform no writes and print each one (`core/dry_run.py`; reads are allow-listed, so a new operation is intercepted until classified). Before, a full-scan dry run handed reviews over for real and reconcile always ran live
- A `story_key` scopes reconcile to that story too (it settled every `impact-applied` story)
- `mode` = `drift` with a `story_key` stops with an error instead of ignoring the key
- Inputs reach the reconcile shell as environment variables, not pasted into the script

**Test-lifecycle gaps recorded**
- `docs/VALIDATION_AND_KNOWN_GAPS.md` sections 3.5–3.9 and fixes F-8 to F-20: notes never gain shipped knowledge (L15), size, scope and cleanup of the notes (L16–L18), tests before deployment (L19), an approved test case silently not automated (G5), requirement or test-case edits after coding go unnoticed (G6, G7), a rejected new-story PR leaves the story looking coded (G8), and deployment, suite size, flakes and bug stories (L20–L23); operating the pipeline continuously (N1–N9, fixes F-21 to F-29): no scheduled app-test run on `main`, no failure-to-defect triage, no alert on failing schedules or expiring credentials, no spend budget, stale agent PRs, merging a red PR, shared test data, one environment and browser, no health metrics

**One file for validation and known gaps**
- `docs/VALIDATION_AND_KNOWN_GAPS.md`: what has been validated live, the clubbed validation runs still to do (A4–A6, B, C, held-out stories, the new behaviour from #199–#201), and every known gap (stories in flight, several stories per scan, Agent 0, generation) with its status and planned fix

**Documentation audit (completeness, not only truth)**
- Model calls per story are stated for a change story as well as a new one (README, GUIDE): Agent 0's context update, Agent 2's per-scenario splices and Agent 3's review of the context-update PR were missing from every count
- Docs describe the stories-in-flight guards, the pull-request browser gate and Agent 0 on the cost ledger everywhere they apply (README, GUIDE, TECHNICAL_DEEP_DIVE, AI_CONCEPTS, REUSE_FOR_NEW_PROJECT); "stories are independent, no shared state" corrected, with the open multi-story gaps listed
- TECHNICAL_DEEP_DIVE no longer carries source line numbers or file sizes, which went stale with every pull request; every function is named with its file
- New ADR-014 (stories in flight)

**Stories in flight at the same time**
- Agent 2 never writes a file another open pull request is changing, and never generates a scenario another open PR already adds: the story waits (`waiting_for_open_pr`, `[WAIT]` in the scan summary), labels unchanged, one `[agent2:waiting]` comment per reason, retried on the next scan. Covers normal, regenerate, change-story owner files and `ai-update`. Fails open (`core/in_flight.py`)
- Duplicate detection compares a test case's title without its `[type]` tag (the stored summary is `[Positive] <title>`, the scenario is `<title>`, so the title fallback could never match a case the pipeline created)
- Agent 4's browser runs take turns across pull requests (first come, first served, bounded at 15 minutes, fail-open; `scripts/e2e_turn.py`): every PR tests the same live application with the same accounts

**A-series open items (closed)**
- `reconcile.closed_scans` is honoured: an undo happens after that many scans see the same close (default 2, as before; 1 = immediately)
- `config.yaml`'s `context_update` comment describes both wording changes and note rewrites
- The golden-rule test scans every `prompts/agent*.md` (a glob, so new prompts are covered); `agent0_*.md` and `agent1_impact_aware.md` were missed
- Agent 0's model cost is posted to the story ledger; Agent 1 no longer treats Agent 0's entries as a previous run, and a genuine new attempt still resets
- The drift job can be run on demand (`Run workflow`, `mode` = `drift`)
- Test cases carry their story's Jira Components; a project that rejects them still gets the test case
- A pull request that changes only `prompts/`, `docs/` or Markdown (e.g. a notes-only context update) runs the unit suite but no browser, and posts no Jira report; any other file runs the E2E, and the check fails open. Agent 3 does not read that unit-only green as evidence against a predicted failure. One rule for both: `core/test_runtime.py`

All generic, each pinned by unit tests (suite: ~2,900 tests).

**Agent 0**
- #175 a change story undone by reconcile can be retried as a new attempt; docs no longer claimed Agent 0 posts a cost ledger (it did not then; it does since the A-series items above)
- #185 a context-update marker blocks a new proposal only while its PR is open; a closed PR no longer suppresses the retry's update
- #186 *using is not changing*: a story classified `new_behaviour` (new functionality, or a new journey through existing behaviour) keeps no seeds, and adjudication needs a named difference, not overlap

**Agent 1**
- #185 the story wins over the app notes where they disagree
- #187 → #188 "no row / zero rows" is judged by the entry it names (quoted or test-data value): absence of a named entry is relative, not a row count. #188 replaces #187's word list

**Agent 2**
- #181, #182 orphan step clean-up, Agent 4 visibility of failures, and an absence predicate every gate accepts
- #185 `click_in_row` clicks the visible copy when a row holds two of one control
- #190 new validator `validate_reused_steps_keep_their_meaning` (29 checks): a Then step re-defined for another feature may not assert more than the committed definition; a bare `# JIRA: KEY` marker is completed in place
- #193 every repairable error reaches the repair loop, whatever its wording (`_route_to_generated_file`); the step-definition prompt shows the committed body of every Then step the feature reuses (`committed_then_definitions`)

**Step definitions (supersedes the two Phase 2 entries below)**
- Generated step-definition modules are self-contained: each declares every step its own feature uses. `tests/step_defs/conftest.py` holds fixtures only (page-object fixtures registered automatically, `credentials` by login role from `APP_USER_<ROLE>` / `APP_PASSWORD_<ROLE>`). The duplicate-step check is same-file. Details: ADR-012's 2026-10 note in [DECISIONS.md](./docs/DECISIONS.md)

**CI**
- #192 Actions storage kept inside the quota: `artifact_cleanup.yml` (daily, deletes artifacts older than 2 days, `scripts/cleanup_artifacts.py`); Agent 4 uploads only what Agent 5 needs, kept 3 days

- `ai-update` comments out step functions a removed or modified scenario left unused (`comment_out_step_defs_unused_by()`, as the change-story splice does), so the unused-step gate no longer fails the run; the PR body lists them instead of claiming they were "removed by regeneration"
- The step-coverage check counts only the paired module and applicable `conftest.py` files; a sibling module generated in the same batch no longer counts (runtime cannot see it). Closes ADR-012's follow-up

**Docs**
- #197 README and docs brought in line with `main` after #193
- Line-by-line audit of `docs/` against `main` (`3289394`): the change-story selector wording rule (wording changes may update a selector; note rewrites never do), self-contained step files, login roles, the `main` rulesets, Agent 5 posting a new report on every re-run, `ai-update`'s step-definition splice, current line numbers and counts

---

## October 2026 — Agent 0 (impact analysis) and the change-story pipeline

A sixth agent, Agent 0 (Impact Analyst), runs before Agent 1 for a story that
changes behaviour existing tests rely on. Design record: [ADR-013](./docs/DECISIONS.md);
operator guide: [GUIDE.md → Change stories — Agent 0](./docs/GUIDE.md#change-stories--agent-0).

**Agent 0, built in phases (all PRs merged 10–12 Oct):**
- #126 Phase A — foundations; #127 Phase B — impact graph and marker backfill (`scripts/backfill_markers.py`)
- #130 Phase C — hand-over pipeline: Impact Review, hand-over, Agent 1 impact-aware mode, Agent 2 owner splice, reconcile
- #131 Phase D — Agent 0 itself (seeds, candidates, adjudication, ranking, publish), switched off by default; #132 design-audit fixes
- #134–#139 Phase E — uncovered live elements (`--compare`, inventory proposals), onboarding kit for applications outside this repository (`scripts/onboarding_check.py`, `docs/AGENT0_ONBOARDING.md`), generality audit
- #159 shadow mode on; #163 live mode for a single-story trial
- #164 Impact Review reads decisions from linked keys and refuses an unreadable review; #165 scenarios without a test case are shown
- #166 context-update PR: the wording a story replaces, proposed for the inventory and app notes

**Validation series A1–A3 (real change stories) — generic fixes:**
- #169 Agent 2 splice writers get the same grounding as the full-file writers, plus one corrected retry; `test_splice_grounding.py` fails any ungrounded model writer
- #171 the orphan cleanup's file is committed even when the splice adds no step function
- #172 `core/json_block.py` reads stored review data however Jira re-stores an edited code block
- #173 the model's verdict caps the tier; short evidence per row; a re-analysis that changes nothing says so; the context update also rewrites passages a story makes untrue (`NoteRewrites`); a revision repeating an existing scenario is flagged; new validator `validate_absence_not_asserted_with_waiting_probe` (28 checks); scenario marker placed below the tags; after an undo, reconcile retires the story's unshipped tests, resets its pipeline labels (`reconcile.reset_labels`), moves the card to To Do (`status_workflow.on_label.impact-reverted`) and posts the retry steps

**Rest of the pipeline in the same period:**
- #140 committed page objects are extended automatically and keep their methods (`validate_extended_page_objects_keep_methods`)
- #141 Agent 1 named "Test Designer" (distinct from Agent 0, the Impact Analyst)
- #142 Agent 1 checks drafted test cases (`core/test_case_rules.py`) before writing them; #160 its run summary handles every outcome
- #143 every validator error is routed to the repair loop; #144, #146 new validator rules
- #149–#152, #162 Agent 3 blocks only for a named failure in lines the PR changed, checks a predicted failure against Agent 4 on the same commit, and is always the reviewer on `main`
- #153 golden-rule guard: application names harvested from the inventory and page objects may not appear in framework files
- #155 Agent 5 scopes the report to the story's own tests and renders Jira markup; #158 the PR title names the story

**Docs:** README, GUIDE, TECHNICAL_DEEP_DIVE, AI_CONCEPTS, REUSE_FOR_NEW_PROJECT and AGENT0_ONBOARDING brought up to date with six agents; ADR-013 added.

---

## Phase 2 — Shared step definitions moved to `tests/step_defs/conftest.py` (superseded)

> Superseded in October 2026: step-definition modules are now self-contained and `conftest.py` holds fixtures only. See the top entry and ADR-012's note.

Fixes a runtime failure that every validator passed. Agent 2 generated a feature
reusing `Given I am on the SauceDemo login page` (defined in the reference module
`tests/step_defs/test_login.py`); Agent 4 failed at collection with
`StepDefinitionNotFoundError`.

**Root cause.** pytest-bdd implements step definitions as pytest **fixtures**,
which are **module-scoped**. A step defined in one step-def module is invisible
to every other module. The step-coverage validator had assumed the opposite
("registers the step globally... no conftest required") and so green-lit code
that cannot run — the PR #9 class of defect. Verified empirically: sibling module
-> `StepDefinitionNotFoundError`; same step in `conftest.py` -> passes.

- **NEW `tests/step_defs/conftest.py`** — shared page-object fixtures
  (`login_page`, `inventory_page`) and the five shared step definitions. This is
  pytest's only supported cross-module sharing mechanism. Located under
  `step_defs/` (not `tests/`) because both validators discover on-disk steps with
  `tests/step_defs/*.py`; shared steps in `tests/conftest.py` would run but be
  invisible to the validator.
- **`tests/step_defs/test_login.py`** — shared steps MOVED out (not copied: both
  validator globs include `conftest.py`, so duplicates would trip the
  duplicate-step guard). Retains two feature-specific steps so the reference
  still demonstrates step authoring, plus a docstring stating the rule: *needed
  by more than one feature -> conftest; specific to one feature -> paired module.*
- **`features/login.feature`** — new 4th scenario (error dismissal) exercising
  those local steps via existing `LoginPage.dismiss_error()` /
  `get_error_message()`. No page-object change required.
- **All quoted-value decorators now use `parsers.re` with `[^"]*`** — the `parse`
  library cannot match empty quoted values, which validation scenarios rely on.
  Each pattern is kept on ONE line: the validator reads first-quote to
  last-quote, so multi-line implicit concatenation corrupts the pattern and every
  step using it stops matching.
- Docs: REUSE_FOR_NEW_PROJECT.md gains **Change 5** (mandatory for every new
  app); DECISIONS.md gains **ADR-012**.
- Suite: **270 passing**, unchanged.

**Open follow-up (closed October 2026):** the step-coverage validator treated decorators in
sibling step-def files as available. It now counts only `conftest.py` plus the paired module.


## Phase 2 — Tier 3 follow-up: complex-locator support in the inventory tooling

Extends `inventory_tools/` to handle the controls real-world apps use, still
fully app-agnostic. Suite 259 -> **267 passing** (+8). No agent/config/workflow
change.

- **Custom widgets via ARIA role / tabindex / contenteditable / stable id.** The
  collector no longer captures only native `input/button/select/textarea/a` +
  test-id elements — it now also captures div/span-based widgets that carry an
  interactive role (`combobox`, `listbox`, `switch`, `slider`, `menuitem`, …), a
  `tabindex >= 0`, `contenteditable`, or a **non-generated `id`** (catches
  drag-drop targets like `#draggable`). These get a churn-proof Playwright role
  locator (`role=combobox[name='Country']`, or a nameless `role=slider` when a
  widget has no accessible name) instead of brittle css, and `element_kind`
  names them sensibly (combobox → dropdown, switch → toggle, …).
- **iframe traversal.** `collect_descriptors` now walks every child frame and
  tags each element with its frame-chain selector, emitted with a ` >>> `
  convention: `iframe#pay >>> [data-test='card']` → 
  `page.frame_locator('iframe#pay').locator("[data-test='card']")`. Nested frames
  chain. The staleness checker resolves these via `frame_locator`, and framed
  test-ids are no longer false-flagged as drift.
- **Open shadow DOM.** The collect/test-id JS recurses into open `shadowRoot`s, so
  web-component controls are captured (closed roots remain inaccessible by
  design). role=/css locators pierce open shadow DOM automatically at runtime.
- **Unstable-selector flag.** Any element whose only handle is a fragile css
  fallback (no test-id, role, label, or text) is listed under a page's
  `_unstable_selectors` with guidance to add a `data-test` — drift risks are now
  visible instead of silently shipped as brittle css.

What still needs a human: un-accessible custom controls (a plain `<div onClick>`
with no role/tabindex/id/test-id can't be detected from the DOM), per-row/per-cell
list & table handling (capture the container + a parametrized locator by hand),
and any element the app gives no stable hook — the real fix there is adding a
`data-test` in the app, which no crawler can manufacture. Validated in a real
Chromium against the full control spectrum of a known practice page (native
inputs, radios, checkboxes, single/multi selects, file inputs, jQuery-UI
datepickers & slider, autocomplete, drag-drop, a custom combobox, an iframe, and
an open-shadow-DOM section) — all captured; only data-table rows and the app's
un-hooked elements remained (as expected).

## Phase 2 — Tier 3 follow-up: inventory tooling made fully app-agnostic

The 3.1 inventory tools shipped working but carried a few SauceDemo-shaped
defaults. This pass removes them so the tools are genuinely reusable across
applications. Additive/refactor only — no agent, config, or workflow code
changed. Suite 254 -> **259 passing** (+5 app-agnostic tests).

- **Configurable test-id attributes.** The attribute allowlist (was hardcoded to
  `data-test`/`data-testid`/`data-qa`) is now a `TEST_ID_ATTRS` constant with a
  broad default (`data-test, data-testid, data-test-id, data-qa, data-cy,
  data-automation-id, data-tid`), threaded through selector ranking, element
  naming, family-collapsing, drift detection, and the browser collect JS, and
  overridable per run with `--test-attrs`. Family-collapse now preserves whichever
  attribute the app actually uses (e.g. `[data-cy^='buy-item-']`).
- **Generic login.** Replaced the `username_input`/`password_input`/`login_button`
  + page-key `"login"` assumption with type-based field auto-detection
  (`input[type=password]`, etc.) and explicit `--login-url` /
  `--username-selector` / `--password-selector` / `--submit-selector` overrides.
- **Scrubbed docstrings.** No `SauceDemo` / `standard_user` / `secret_sauce` in
  any generic file; examples use neutral placeholders. Audited: zero app-specific
  keywords remain in `inventory_tools/` or the inventory scripts.
- New tests prove the full generate→staleness pipeline on a `data-cy` app with
  zero SauceDemo assumptions.

## Phase 2 — Tier 3 (3.1 inventory tooling, 3.4 sweeper) + page-level errors

All additive — new packages, scripts, one workflow, and data. No existing agent
code or workflow changed. Suite 218 -> **254 passing** (+36).

### Inventory generation + staleness checker (backlog 3.1)
New `inventory_tools/` package with browser-free, unit-tested logic
(`introspect.py`: selector ranking, element naming, repeated-family collapsing,
draft page assembly, staleness diff) and a thin Playwright layer (`browser.py`).
Two CLIs: `scripts/generate_inventory.py` crawls the live app and emits a DRAFT
inventory (machine-fillable fields populated; `elements_notes` / `key_methods` /
`errors` / `components` left as visible stubs — a machine can't infer behaviour,
intended API, or exact error strings), and `scripts/check_inventory_staleness.py`
diffs the committed inventory against the live DOM, reporting stale selectors
(the dangerous kind), untracked live data-tests, and unreachable pages, warning
on pages with no `elements_notes`, and exiting non-zero under `--fail-on-drift`
for CI gating. 22 tests in `test_inventory_introspect.py`. Requires
`playwright install chromium` to run live.

### Sweeper — stalled-PR backstop (backlog 3.4)
`.github/workflows/sweeper.yml` (hourly cron + dispatch) runs
`scripts/sweep_stalled_prs.py`. Cron agents (1/2) self-heal; event-driven agents
(3 review, 4/5 run+report) don't — a cancelled or missing `pull_request` run
strands a PR. The sweeper finds open `auto/*` PRs whose Agent-3 or Agent-4
workflow has no settled run (success/failure/timed_out) for the current commit
and reopens them to re-fire the event chain. It reuses Agent 2's `GH_PAT`
deliberately: the built-in GITHUB_TOKEN does not re-fire workflows, and Agent 5's
report job is gated on `pull_request`, so a workflow_dispatch re-run would skip
the report — reopening re-runs the whole chain. Loop-safe: a real pass/fail is
left alone, and each nudge drops a commit-SHA marker comment so a PR is nudged at
most once per commit. 14 tests in `test_sweeper.py`.

### Page-level errors (schema)
`app_inventory/saucedemo.json` — page-specific error strings moved from the flat
top-level `common_errors` into each page's new `errors` field (login errors ->
login, checkout errors -> checkout_step_one). This keeps messages next to the
screen that raises them and lets them ride the 2.2 component filter (a Login
story injects only login errors). Backward compatible: nothing parses errors;
`common_errors` is retained for genuinely cross-cutting errors. No code change.

## Phase 2 — Tier 2 (batch 2: 2.2 / 2.3 / 2.4)

Three enhancements, each backward-compatible and each with a safe fallback. Suite
grew 170 -> **218 passing** (+48 tests across three new files).

### Component-wise inventory filtering (backlog 2.2)
`agents/app_context.py` gains `filter_inventory_by_components()` and a
component-aware `load_page_inventory_json(components=None)`. When a story's Jira
Components are passed, only the inventory pages tagged with those components are
injected, plus any page flagged `"always": true` (shared pages such as the menu) —
mirroring the module-wise app-context selection (2.1). Matching is
case/space/hyphen-insensitive; the internal `components` / `always` /
`_inventory_conventions` tagging keys are stripped from the string sent to the LLM.
**Safe defaults:** a no-argument call is byte-identical to before, and a story with
no components — or a component that matches no page — gets the full inventory
(context is never silently dropped).

Wired at Agent 2's two entrypoints (`run` and `run_update`), which already fetch
the story and account for ~92% of input tokens. Agent 3 keeps the full inventory
so a review never false-flags a filtered-out selector.

`app_inventory/saucedemo.json` was completed from login-only to all eight SauceDemo
modules (login, inventory, inventory_item, cart, checkout_step_one/two/complete,
and the shared menu), each tagged with its Jira Component. A Login story now injects
~56% fewer inventory characters. New `tests/unit/test_inventory_filtering.py` (18).

### Error-type-aware repair prompts (backlog 2.3)
`agents/agent2_coder.py` — the repair loop used to answer every validator failure
with the same "add your @given/@when/@then decorator" instruction. It now classifies
each error by its validator prefix (import resolution, method resolution, duplicate
step-def, filename consistency, Gherkin structure, step coverage) and emits a hint
targeted at that class, de-duplicated and in a fixed order, via
`_classify_error()` / `_build_error_type_guidance()`. An import error is no longer
told to add a step decorator. New `tests/unit/test_repair_error_types.py` (14).

### Update-mode step-def splicing (backlog 2.4)
`agents/agent2_coder.py` — ai-update already spliced the feature file
scenario-by-scenario but fully regenerated the step-def file every time.
`_splice_step_defs_incremental()` now works in tiers: **unchanged** (existing file
already covers the spliced feature — kept as-is, zero LLM calls), **spliced** (only
the genuinely new step functions are generated and appended, passing functions
untouched), or **regenerated** (Tier-C fallback to the previous whole-file
regeneration on any ambiguity — no file on main, unparseable, LLM returned nothing
usable, still-uncovered after splice, or a duplicate-step collision). Post-splice
re-validation plus the fallback mean a splice can never ship broken step defs.
The step-def `GeneratedFile` purpose records which mode ran. New
`tests/unit/test_step_def_splicing.py` (16).

## Phase 2 — Tier 2 (app-context token savings)

Both changes are backward-compatible; the SauceDemo app now ships in the module
layout as a worked example.

### Inventory minification (backlog 2.6)
`agents/app_context.py` — `load_page_inventory_json()` minifies the inventory JSON
at injection time (file on disk stays readable; only the prompt string is compacted).
~15% on the SauceDemo inventory, more as inventories grow, zero information loss.
Malformed JSON falls back to raw text with a warning (pre-2.6 behaviour); a missing
file still raises FileNotFoundError.

### Module-wise app context (backlog 2.1)
`agents/agent1_analyst.py` `load_app_context_block()` is now module-aware and
`agents/jira_client.py` `get_story()` returns the story's Jira Components (additive).
If `prompts/app_context/` exists, Agent 1 injects `core.md` (always) + one
`<component>.md` per Jira Component; otherwise the single `prompts/app_context.md`
is used exactly as before. Matching is case/separator-insensitive; a story with no
components (or an unknown one) safely gets all modules.

SauceDemo's `app_context.md` is split into `prompts/app_context/`: `core.md` +
`login.md` / `inventory.md` / `cart.md` / `checkout.md`. A Login story now injects
~49% fewer context tokens than the single file. Tag stories with their Jira
Component to realise the saving; untagged stories are unaffected (safe default).

New `tests/unit/test_app_context_modules.py` — 19 tests (module selection, all safe
defaults, minify round-trip / malformed-fallback / missing-file). Suite: 151 → **170**.

---

## Phase 2 — Cross-file duplicate step-definition guard (SCRUM-54 lesson) (superseded)

> Superseded in October 2026: the duplicate-step check is now same-file, because self-contained modules each resolve their own copy of a step. See the top entry and ADR-012's note.

**The failure.** A new login-adjacent feature (`test_login_edge_and_validation.py`)
re-declared `@given("I am on the SauceDemo login page")`, a step the reference
`test_login.py` already defines. pytest-bdd registers step definitions GLOBALLY
across the `tests/step_defs/` package, so two files declaring the same step collide
at collection time. Agent 3 caught it as a Major advisory issue; this change makes it
a permanent, enforced guard so it cannot silently recur.

**The fix — "prompt asks, validator enforces" (the framework's standard pattern):**

1. **Validator** — `validate_no_duplicate_step_definitions()` in
   `agents/gherkin_analyzer.py`. After generation it scans the generated step-def
   files PLUS the on-disk reference for identical decorators across files. It is
   deliberately NARROW to avoid false positives: it flags only a genuine
   `(keyword, parser_type, phrase)` collision across two different files. It does
   NOT flag different phrases, different keywords, a bare string vs a `parsers.parse`
   of the same text, parameterised steps differing only in variable name, or
   duplicates within a single file. A regenerated file supersedes its on-disk copy,
   so `ai-update`/`ai-regenerate` never false-positive against the stale version.
   Wired into `_validate_generated_files()` (final gate) and, in `repair_format`,
   into `_collect_repairable_errors()` so the repair loop can regenerate the
   offending GENERATED file (never the reserved reference) with the feedback baked in.

2. **Prompt rule** — `prompts/agent2_coder_generate.md` gains rule 13 (and a
   reinforcement in the step-def section): do not re-declare a step the reference
   already defines; reuse it, or move a truly shared step into
   `tests/step_defs/conftest.py`. This reduces occurrences; the validator guarantees
   they're caught.

**Verification.** New `tests/unit/test_duplicate_step_defs.py` — 14 tests covering
true positives (new-vs-new, new-vs-reference, parse decorators), every false-positive
guard (different phrase/keyword/parser-type, parameterised varname, within-file dup,
non-step-def files, regenerated-file supersession), and the repair-format contract
(targets the generated file, matches the loop's grouper regex). Confirmed the
validator produces ZERO errors against the current repo's existing step-defs.
Catalogued as lesson #15 in `docs/AI_CONCEPTS.md`. Suite: 156 → **170 passing**.

---

## Phase 2 — Tier 2 (batch 1: low-blast-radius token savings)

Both changes are **fully backward-compatible** — with no new files or folders
added, behaviour is byte-identical to before.

### Inventory minification (backlog 2.6)

`agents/app_context.py` — `load_page_inventory_json()` now minifies the inventory
JSON at injection time (`json.dumps(..., separators=(",",":"))`). The file on disk
stays human-readable; only the string sent to the LLM is compacted, trimming input
tokens on every Agent 2 and Agent 3 call at zero information loss. On the SauceDemo
inventory this is ~15%; the saving grows with inventory size.

**Safety:** if the inventory is not valid JSON, the method logs a warning and returns
the raw text unchanged — identical to the pre-2.6 behaviour, so a malformed file can
never make it start failing. A *missing* file still raises `FileNotFoundError` as
before (only parse errors fall back).

### Module-wise app context (backlog 2.1)

`agents/agent1_analyst.py` — `load_app_context_block()` becomes module-aware, and
`agents/jira_client.py` — `get_story()` now returns the story's Jira Components
(additive; all existing keys unchanged).

Two layouts, chosen automatically from the filesystem:

- **Single file (default, unchanged).** `prompts/app_context.md` — the original
  behaviour. Used whenever `prompts/app_context/` does not exist.
- **Module-wise (opt-in).** Create `prompts/app_context/` with `core.md` plus one
  `<component>.md` per module. Agent 1 then injects `core.md` (always) plus the files
  matching the story's Jira Components, instead of carrying every module's rules on
  every call. For a large app this focuses the prompt and cuts Agent-1 input tokens.

Matching is case- and separator-insensitive ("User Management" → `user_management.md`).
Safe defaults: a story with no components, or a component with no matching file,
injects **all** modules — context is never silently dropped.

**To adopt** (optional, per app): split `prompts/app_context.md` into
`prompts/app_context/core.md` (roles, global errors, auth flow) + one file per Jira
Component, and tag stories with their Component. Until you do, nothing changes.

### Tests

New `tests/unit/test_app_context_modules.py` — 19 tests covering both features:
single-file compatibility, core-always, multi-component, name normalisation,
all safe-default fallbacks, empty/absent folders, and for minify: valid-JSON
round-trip, colons-in-values, unicode, malformed-fallback, and missing-file-still-raises.
Suite: 137 → **156 passing**.

---

## Phase 2 — Tier 1

### Ledger reset boundary — fixes a cost double-count bug (backlog 1.3)

**The bug.** Deleting a story's Test Cases and resetting it to `ai-ready` left the
previous run's `[LLM-USAGE]` comments on the story. Agent 5's next aggregation
summed the discarded run *and* the new one, so the "End-to-end LLM usage & cost"
table reported inflated totals.

**The fix.** `agents/usage_ledger.py` gains a `[LEDGER-RESET]` boundary marker:
`format_reset_comment()` / `post_reset_to_story()` post it (best-effort, never
raises); `_comments_after_last_reset()` returns only comments posted after the most
recent boundary; `aggregate_story_usage()` aggregates just that slice.
**Backward compatible** — with no marker present every comment counts, as before.
`has_usage_comments()` lets an agent ask "has this story been costed since the last
boundary?".

`agents/agent1_analyst.py` posts the boundary when processing a story that already
carries usage entries. Scoped deliberately to Agent 1: `ai-update` and
`ai-regenerate` are rework on the same costed story, so their usage *should*
accumulate into the lifetime total — only a fresh `ai-ready` cycle restarts
accounting. Skipped in `--dry-run`; wrapped in its own try/except so a ledger
failure can never fail a run.

14 new unit tests. Suite: 123 → **137 passing**.

### Model routing (backlog 1.2)

`agent1_analyst.yml` and the Agent-5 job in `agent4_runner.yml` now read
`LLM_MODEL_LIGHT`, falling back to `LLM_MODEL` and then Opus. Agents 2 and 3 always
use `LLM_MODEL`. **No-op until the repo variable is set** — the fallback chain
preserves current behaviour exactly. Set `LLM_MODEL_LIGHT` (e.g.
`claude-sonnet-4-6`) to route test design and report prose to a cheaper tier.

### Gateway probe (new manual tool)

`scripts/gateway_probe.py` — lists the models the LLM gateway exposes and tests
whether Anthropic prompt caching is passed through, trying the `cache_control`
breakpoint on both `system` and `user` message placements. Manual only; not run by
CI. Result on the adesso hub (July 2026): 45 models available; **caching not
passed through** — all cache counters zero on a 2,356-token prefix across both
placements, so backlog item 1.1 is blocked pending a gateway config change.

### Credential hygiene for real-app onboarding (backlog 1.5)

`docs/REUSE_FOR_NEW_PROJECT.md` — the `test_users` step is now a security note.
SauceDemo's public demo credentials are safe to commit; real ones are not, because
`config.yaml` and `app_context.md` are committed permanently *and* `app_context.md`
is injected into every Agent 1 prompt. Documents the env-var pattern.

### Documentation accuracy

- `docs/GUIDE.md` — removed 16 stale references to Google Gemini as the LLM
  (agent descriptions, troubleshooting, and the Mermaid architecture diagrams).
  The framework has run on Claude via an OpenAI-compatible LiteLLM gateway since
  the provider swap; the guide still described the original Gemini build.
- `README.md` — removed the dead `docs/reference/` index row (those files were
  never added to the repo).
- Test-count references updated 123 → 137.

### Already in place

Backlog item 1.4 (move `pages/base_page.py` to `reserved_paths`) was found already
applied in `config/config.yaml` — no change needed.

---

## July 2026 — Accurate story reporting + failure evidence capture

**Report scope fix (unit vs app tests).** Agent 4 previously ran `pytest tests/`
(unit + E2E together) into one junit.xml, so Agent 5's Jira report counted the
123 framework unit tests alongside the story's app tests — inflating and
confusing the numbers. Now split into two steps:
- `pytest tests/unit/` → `reports/junit-unit.xml` — framework self-test gate
  (runs first; failing it signals the framework itself is broken).
- `pytest tests/step_defs/` → `reports/junit.xml` — the app E2E results Agent 5
  reads. Story reports now reflect ONLY the feature's tests. No Agent 5 code
  change (it still reads junit.xml, which is now app-only).

**Failure evidence.** The `page` fixture in tests/conftest.py now records, on
test FAILURE only: a full-page screenshot (`.png`), a video (`.webm`), and a
Playwright trace (`.trace.zip`) into `reports/failure-evidence/`. Passing tests
discard video/trace to keep artifacts small. All three ride along in the
existing `reports/` workflow artifact for human inspection on the PR. A
`pytest_runtest_makereport` hook exposes each test's outcome to the fixture.

---

## July 2026 — LLM token & cost instrumentation + end-to-end story cost ledger

Token usage and cost are now MEASURED, tracked as two separate quantities,
and aggregated per story across all agents.

### Per-run tracking (agents/llm_client.py)

- A usage tracker records input/output tokens for every LLM call (both
  structured and text mode). Per-call log lines show the call's tokens plus
  running totals.
- At the end of each story run, TWO separate summary lines are logged:
  `LLM TOKEN USAGE [...]` (exact, API-reported) and `LLM COST [...]`
  (derived from pricing, split into input + output cost). The summary dict
  is returned in agent results under `llm_usage`.
- Pricing comes from two optional repo Variables (USD per 1M tokens):
  `LLM_PRICE_INPUT_PER_1M`, `LLM_PRICE_OUTPUT_PER_1M` — now exposed in all
  four agent workflows. Unset → tokens still logged, cost shows "n/a".
- Endpoints that don't report `usage_metadata` are counted and flagged as a
  lower bound. Tracking never raises.

### End-to-end story ledger (agents/usage_ledger.py — NEW)

Each agent runs in a separate CI process, so in-memory totals can't span the
pipeline. The Jira story itself is now the ledger:

- After finishing, every LLM-using agent (1, 2, 3, 5) posts one compact,
  machine-parseable comment: `[LLM-USAGE] agent="..." calls=N
  input_tokens=N output_tokens=N input_cost_usd=... output_cost_usd=...
  cost_usd=...` (skipped in dry-run; best-effort, never fails a run).
- Agent 3 derives the story key from the `auto/<KEY>-` branch convention.
- Agent 5 reads all prior usage comments (new `JiraClient.get_comments`),
  adds its own usage, and appends an "End-to-end LLM usage & cost" table to
  its test report — per-agent rows plus a TOTAL row. Partial pricing is
  flagged as a lower bound; token totals are always exact.

### Tests

27 new unit tests (`test_llm_usage.py`, `test_usage_ledger.py`) — suite
grew 96 → 123, all passing. No existing module behavior changed
(gherkin_analyzer, orphan_cleanup, validators, app_context, schemas,
config.yaml all untouched).

---

## July 2026 — Documentation consolidation (11 → 7 files) + stale reference cleanup

### Why

Doc count had grown to 11 standalone markdown files with overlapping scope,
and several still referenced `test_inventory.py` (renamed to
`gherkin_analyzer.py` in June).

### Consolidation map

| Merged file | Now lives in |
|---|---|
| docs/ARCHITECTURE_DIAGRAM.md | docs/GUIDE.md → "Architecture diagrams" |
| docs/STATE_MANAGEMENT.md | docs/GUIDE.md → "State management deep-dive" |
| docs/LESSONS_LEARNED.md | docs/AI_CONCEPTS.md → "Lessons learned" |
| docs/APP_INVENTORY_SCHEMA.md | REUSE_FOR_NEW_PROJECT.md → "App inventory JSON schema" |
| docs/ADR-008-pat_for_cascade.md | docs/DECISIONS.md (ADR content unchanged) |
| docs/ADR-009-deduplication.md | docs/DECISIONS.md (module refs updated) |

Final doc set (7): README.md and CHANGES.md at root; docs/GUIDE.md,
docs/AI_CONCEPTS.md, docs/DECISIONS.md, docs/REUSE_FOR_NEW_PROJECT.md,
docs/TECHNICAL_DEEP_DIVE.md.

### Also in this release

- Fixed all remaining `test_inventory.py` references in markdown
  (CHANGES, TECHNICAL_DEEP_DIVE, ADR-009 content).
- Updated pointers in code/config that referenced merged docs:
  `agents/app_context.py` error message, `config/config.yaml` comment,
  `.github/workflows/agent2_coder.yml` comment, README doc index,
  GUIDE internal links.
- No behavior change; all 96 unit tests pass.

---

## June 2026 — Dynamic sprint scoping, module rename, documentation refresh

### 1. Dynamic sprint scoping (`sprint: "auto"`)

Previous state: `sprint: "Sprint 0"` was hardcoded in four config blocks and
needed manual editing at every sprint boundary.

Now: all four selection blocks use `sprint: "auto"`. At scan time,
`JiraClient.get_active_sprint_name()` resolves the currently active sprint
from Jira via the new **`JIRA_BOARD_ID`** env var (set once in .env / GitHub
secrets; find the ID in your board URL). The result is cached per run so
Agent 2's three scan passes make one API call. Resolution failures degrade
gracefully to an all-sprints scan with a logged warning — the pipeline never
blocks on sprint lookup.

Priority order remains: `--sprint` CLI flag / workflow input > config value >
no filter. Explicit names (`"Sprint 10"`), `"openSprints"`, and omitting the
key all still work as before.

Files: `agents/jira_client.py`, `config/config.yaml`, both agent workflow
files (added `JIRA_BOARD_ID` to env).

### 2. Renamed `agents/test_inventory.py` → `agents/gherkin_analyzer.py`

The old name looked like a pytest test file (`test_*` prefix), which confused
readers and risked accidental pytest collection. The module is the Gherkin /
step-definition analysis engine (scenario inventory, dedup matching, step
coverage validation) — the new name says so. All imports updated across
`agent2_coder.py`, `orphan_cleanup.py`, and the unit test files; zero
behavior change; all 96 unit tests pass. Historical docs (ADR-009) carry a
rename note rather than rewritten history.

### 3. New documentation

- `docs/STATE_MANAGEMENT.md` (since merged into docs/GUIDE.md, July 2026) — how the pipeline tracks progress (label state
  machine, sticky vs one-shot labels, JIRA hash markers, failure recovery).
- `docs/AI_CONCEPTS.md` — which AI concepts are used and deliberately not
  used, the guardrails analysis, and a demo Q&A.
- `docs/LESSONS_LEARNED.md` (since merged into docs/AI_CONCEPTS.md, July 2026) — the failure catalog: all 14 production LLM
  failure modes, root causes, and where each permanent fix lives.

---

## Hotfix v4 — Output token cap, feedback summarization, degraded-output detection (2026-05-07)

### What broke

After hotfix v3 added the import validator, the next CI run with `gemini-2.5-flash` succeeded at planning (correctly added cart_page and product_detail_page to the plan!) but failed at the step-coverage repair stage. The log showed three repair attempts that all produced ~656 chars of unparseable Python, eventually exhausting retries with all 22 step-coverage errors still present.

Root causes (three separate problems compounding):

1. **`max_output_tokens=4096` too small for code generation.** This cap is a sane default for structured review output (Agent 3) but step def files for complex 15-scenario stories legitimately need more. The LLM hit the token cap mid-generation and returned truncated stubs.

2. **22-error feedback prompt overwhelmed the LLM.** Each error string was ~250 chars × 22 errors = 5,500 chars of nearly-identical "step X has no matching @then() decorator" repetition injected into the prompt. Smaller LLMs respond to this by getting confused and producing shorter, worse output instead of more comprehensive output.

3. **No "degraded output" abort.** When the first repair produced a 656-char syntax-broken stub, the loop happily fed it back as "previous attempt" for retry #2, which produced more garbage. Burning quota on each retry.

### Fix

Three changes, all framework code, all app-agnostic:

#### 1. Separate token cap for code generation

`agents/llm_client.py` now distinguishes:
- `DEFAULT_MAX_OUTPUT_TOKENS = 4096` — for structured outputs (CodePlan, ReviewReport)
- `CODE_GENERATION_MAX_OUTPUT_TOKENS = 8192` — for raw text (entire source files)

`invoke_text()` lazily creates a separate `ChatGoogleGenerativeAI` instance with the higher cap, cached on first call. No change needed to structured output paths.

#### 2. Compact validator feedback summary

New `_summarize_validator_feedback()` extracts only the actionable Gherkin step phrases (e.g., `Then the products should be sorted by name ascending`) and bullet-lists them. For >8 errors, shows the first 8 verbatim plus a count of the remaining with one explanatory sentence about the pattern.

Empirical reduction on the SCRUM-12 failure: **3,377 chars → 365 chars (89% smaller)**. The LLM sees the problem clearly without drowning in repetition.

#### 3. Degraded-output detection — abort early

New `_is_degraded_regeneration()` runs after each repair LLM call. If the new content:
- Is shorter than 500 characters, OR
- Fails to parse as Python (syntax error), OR
- Is less than 30% the size of the prior real attempt

then the repair loop aborts immediately and keeps the prior content. The final validator will raise on the original errors, but we don't waste another LLM call producing more garbage.

New `_looks_like_useful_python()` complements this for the "should I show the previous attempt to the LLM?" decision — if the prior is also broken, omitting it from the prompt produces better results than including it.

### Files changed

| File | Change |
|---|---|
| `agents/llm_client.py` | New `CODE_GENERATION_MAX_OUTPUT_TOKENS = 8192`. `invoke_text()` uses a separate cached LLM instance with this higher cap. |
| `agents/agent2_coder.py` | New `_summarize_validator_feedback()`, `_looks_like_useful_python()`, `_is_degraded_regeneration()` helpers. Repair loop checks for degraded output and aborts early. Feedback prompt rewritten to be compact. |
| `tests/unit/test_step_coverage_repair.py` | 11 new tests covering: feedback summarization (verbatim vs summarized), degraded output detection (short, syntax-broken, dramatic shrinkage), early abort behavior, real-content acceptance. Existing tests updated to use realistic Python content (>500 chars, valid syntax) since they were inadvertently testing with stubs that the new detector correctly flags. |
| `CHANGES.md` | This entry. |

### Test results

- **159 unit tests pass** (up from 148)
- **1 unrelated pre-existing failure** still unchanged (`test_empty_quoted_value_with_parsers_parse_REJECTED` — was failing in original code before any of these hotfixes)
- Smoke-tested helpers against the actual SCRUM-12 production failure data — all detection logic works as designed

### Why this is reusable across projects

- **Token caps** are model-level concerns, not app-level. The constants live in `llm_client.py` and apply to any project using this framework.
- **Feedback summarization** operates only on validator-emitted error strings — the regex pattern matches the framework's own output format, agnostic to what app the validator was run against.
- **Degraded-output detection** uses Python AST parsing and content length thresholds. Doesn't care about the app domain.

### What this fix does NOT do

- Does not change the LLM's actual output quality. If `gemini-2.5-flash` can't produce a valid step def for a 15-scenario story, this fix doesn't make it produce one. What it does is **fail clearly and faster** instead of burning quota on bad retries.
- Does not auto-split large stories. If the underlying story is too complex for the LLM to handle in one generation, you'll still see this fail — just without the wasted retries. Splitting that story into 2 smaller stories is the right human-in-the-loop response.

### What to watch for in the next run

The successful path looks like this in the logs:

```
LLM initialized: gemini-2.5-flash (temp=0.2, max_output_tokens=4096)
Code generation LLM ready: gemini-2.5-flash (max_output_tokens=8192)
...
Stage 1 complete: 5 files planned
...
Generated 4500 chars for tests/step_defs/test_inventory_sorting.py
...
Step coverage check: OK
Import resolution check: OK
PR opened
```

If validators still flag issues:

```
Validators found N issue(s) across 1 file(s). Attempting repair (attempt 1/2)...
  Repair mode: N validator error(s) summarized into ~400 chars of feedback...
Generated 5200 chars for tests/step_defs/test_inventory_sorting.py
Validator repair succeeded after 1 retry attempt(s).
```

If the LLM produces garbage on retry, you'll now see this clear abort:

```
Repair produced degraded output for 'tests/...' (656 chars vs prior 4500 chars,
  syntax-valid=False). Aborting repair to avoid wasting more LLM calls.
```

Then the final validator raises with a clear message about what couldn't be fixed.

---

## Hotfix v3 — Import resolution validator (2026-05-07)

### What broke

After hotfix v2 unblocked the step-coverage failure, the next run produced a PR that opened successfully but failed at the Agent 4 (Runner) test-collection stage:

```
ImportError while importing test module 'tests/step_defs/test_inventory_sorting.py'
E   ModuleNotFoundError: No module named 'pages.product_detail_page'
```

The LLM had generated a step def file that imported page object classes from files that **were never planned** and **don't exist on disk**. Agent 3 (Reviewer) caught it correctly and posted a 🛑 verdict listing all the missing classes, but Agent 4 still ran (Agent 3 is advisory — it's the human's job to read the review before merging) and crashed at pytest collection time.

### Why the previous validators didn't catch this

The framework had three validators before v3:
- **Filename consistency** (Phase 4) — passed: feature filename matched step def
- **Step coverage** (Phase 8) — passed: every Gherkin step had a decorator
- **Path policy** (v1 hotfix) — passed: no reserved files were touched

None of them check that **imports inside Python files actually resolve**. The LLM hallucinated `from pages.cart_page import CartPage` and `from pages.product_detail_page import ProductDetailPage` for files that aren't in the repo and weren't planned. All three existing validators happily passed it through.

### Fix — Import resolution validator

A new **fourth validator** parses every generated `.py` file's import statements and checks that each imported module resolves to:

1. **Python standard library** (auto-detected via `sys.stdlib_module_names`)
2. **Third-party package in `requirements.txt`** (auto-parsed; handles dash-to-underscore name normalization)
3. **An existing file in the repo**
4. **A file in this generation batch** (so cross-file imports within the batch work)

If none of these match → the import is broken. The validator emits an error in the same `<type> error in '<path>':` format the existing repair loop's grouper can parse, so the LLM gets a second chance to fix the import.

### Why this is reusable across projects

- **Pure AST analysis** — no project-specific assumptions
- **Auto-discovers stdlib** — `sys.stdlib_module_names` is built into Python
- **Auto-discovers third-party deps** — reads whatever's in `requirements.txt`
- **Handles common naming aliases** — `pyyaml`/`yaml`, `PyGithub`/`github`, etc., as standard Python ecosystem facts (not project-specific)
- **No hardcoded paths or names** — works for any app, any project

### Files changed

| File | Change |
|---|---|
| `agents/import_validator.py` | **NEW** — parses imports via Python's `ast` module, classifies each as stdlib / third-party / repo-internal / planned-in-batch / unresolvable. Emits errors in the format the repair loop already understands. |
| `agents/agent2_coder.py` | Renamed `_group_coverage_errors_by_step_def` → `_group_validator_errors_by_file` (with backward-compat alias) — now matches any `error in '<path>':` prefix. New `_collect_repairable_errors` aggregates output from both step-coverage and import validators. Final validator (`_validate_generated_files`) now runs the import check too. Repair loop now handles both error types in one pass. |
| `tests/unit/test_import_validator.py` | **NEW** — 28 unit tests covering: SCRUM-13 regression scenario, stdlib imports, third-party imports, repo-internal imports, planned-in-batch imports, requirements.txt parsing, dotted module paths, edge cases (malformed source, empty input, relative imports, non-Python files). |
| `CHANGES.md` | This entry. |

### Test results

- **148 unit tests pass** (was 120 before adding 28 new tests)
- **1 unrelated pre-existing failure** still unchanged
- **End-to-end repair simulation against the actual SCRUM-13 failure** verified: validator catches 2 broken imports, repair loop regenerates the step def file, retry produces clean imports, final validation passes

### Cumulative validator coverage now

The framework now defends against four LLM failure modes:

| # | Validator | Catches |
|:-:|---|---|
| 1 | Filename consistency (Phase 4) | kebab/snake mismatches between feature files and `feature_path()` calls |
| 2 | Step coverage (Phase 8) | Gherkin steps without matching `@given/@when/@then` |
| 3 | Path policy (v1 hotfix) | LLM trying to overwrite reserved reference files |
| 4 | Import resolution (v3 hotfix) | Imports referencing modules that don't exist anywhere |

All four feed the same self-correcting repair loop with up to 2 retries. If retries exhaust, you get a clear final error explaining what the LLM couldn't fix.

### Honest assessment

I cannot promise this is the last bug. The repair loop and validators defend against the LLM mistakes I've seen in production failures so far. Tomorrow's story might surface a fifth failure mode I haven't anticipated. What I can say:

- All four validators are app-agnostic — onboarding a new app changes nothing here
- The repair pattern is extensible — adding a fifth validator is one new module + one line in `_collect_repairable_errors`
- The error message format is stable — `<type> error in '<path>':` — so future validators integrate without touching the repair loop

---

## Hotfix v2 — Self-correcting step coverage repair (2026-05-07)

### What broke

After the v1 hotfix unblocked extension of page objects, the next run of SCRUM-12 hit a different failure mode at the validator stage:

```
Step definition coverage check FAILED with 12 error(s):
  - feature step `Then the products should be sorted by name ascending` has no matching @then() decorator
  - feature step `When I select "Price (low to high)" from the sort dropdown` has no matching @when() decorator
  ... (10 more)
```

The validator was working correctly. The LLM (`gemini-2.5-flash-lite` in CI) had generated 12 Gherkin step phrases in the feature file but didn't write matching `@given/@when/@then` decorators in the step def file. This is the exact pattern from PR #9 — weaker models occasionally skip decorators.

### Why the previous design wasn't enough

The validator design was "validate then abort." When weak models slip up, the entire run is wasted — including the work spent generating other files (feature, page objects). The user has to re-trigger from scratch and pay the full quota cost again.

But the validator already produces structured error messages naming the exact step def file and the exact missing step phrases. That's perfect feedback to give back to the LLM for a second attempt.

### Fix — Self-correcting retry loop

Between Stage 2 generation and final validation, a new repair pass runs. If the coverage validator finds errors, the broken step def file (only that one — not the whole batch) is regenerated with explicit feedback in the prompt:

```
# CRITICAL: Validator Feedback — fix these issues

Your previous attempt at this file was rejected by the automated validator.
The specific problems were:

- Step coverage error: feature step `Then the products should be sorted...` 
  has no matching @then() decorator
- (etc.)

You MUST address every one of these issues...

## Your previous attempt (which had the issues above):
[the broken step def file]
```

The loop is bounded:
- Up to **2 retry attempts** per story (configurable)
- Only the broken file is regenerated (not the whole batch)
- If retries exhaust, the final validator raises clearly so you see the issue

### Why this is reusable across projects

- App-agnostic — the validator already works on any feature/step pair
- Model-agnostic — works whether you're on `-lite`, `-flash`, or `-pro`. Lite needs more retries; flash usually doesn't need any
- Story-agnostic — works for sort, cart, checkout, anything
- Cost-bounded — capped retries, only regenerates the broken file
- No hardcoding — all feedback comes from the validator's own error strings

### Files changed

| File | Change |
|---|---|
| `agents/agent2_coder.py` | New `_attempt_step_coverage_repair()` runs between generation and final validation. New `_group_coverage_errors_by_step_def()` parses validator errors. `generate_file_content()` now accepts optional `validator_feedback` and `previous_attempt` kwargs for repair-mode regeneration. |
| `prompts/agent2_coder_generate.md` | New `{validator_feedback_block}` placeholder. When non-empty, the prompt explicitly asks the LLM to fix specific decorator issues. When empty, no behavior change from v1. |
| `tests/unit/test_step_coverage_repair.py` | **NEW** — 10 unit tests covering: error parsing, no-error-noop, single-retry success, retry exhaustion, targeted-only-broken-files repair, validator-feedback passing, prompt-content verification. |
| `CHANGES.md` | This entry. |

### Test results

- **120 unit tests pass** (was 110 before adding the new tests, 90 before the v1 hotfix)
- **1 unrelated pre-existing failure** unchanged (`test_empty_quoted_value_with_parsers_parse_REJECTED` — was already failing before any of these hotfixes)
- All 10 new repair tests pass, including the regression test that mimics the exact SCRUM-12 failure mode (12 missing decorators all targeting one step def file)
- Verified against real production error data: the 12 errors from your failed run group correctly into 1 repair call

### What you'll see in the next run

```
Step coverage check found 12 missing decorator(s) across 1 file(s).
Attempting repair (attempt 1/2)...
  Repairing 'tests/step_defs/test_inventory_sorting.py' with 12 feedback item(s)...
Stage 2: generating content for tests/step_defs/test_inventory_sorting.py...
  Generated ~7500 chars for tests/step_defs/test_inventory_sorting.py
Step coverage repair succeeded after 1 retry attempt(s). All decorators now match.
```

If the LLM still misses things on retry 1, attempt 2 fires automatically. If both fail, you'll see a clear final-validator error telling you to upgrade the model — most likely from `gemini-2.5-flash-lite` to `gemini-2.5-flash`.

### Cost impact

- **Best case** (LLM gets it right first try): zero extra calls. Same as before.
- **Typical case** (lite model misses 1-3 decorators): +1 extra call.
- **Worst case** (LLM keeps missing things): +2 extra calls before final failure.

So worst case adds 2 calls per failed story. Much cheaper than the alternative of having to rerun the whole pipeline (which is 4-5+ calls).

---

## Hotfix v1 — Two-tier path policy (2026-05-07)

### What broke

After the Phase A+B+C refactor was deployed, the first end-to-end run against story SCRUM-12 ("Product Sorting on Inventory Page") failed at Agent 2's plan-validation step:

```
ValueError: LLM tried to overwrite reserved reference files: ['pages/inventory_page.py'].
```

The LLM correctly identified that adding sort tests requires new methods on `InventoryPage` (the existing page object had only `is_loaded()` and `get_page_title_text()`). But `pages/inventory_page.py` was on the reserved-paths list — meaning "never modify under any circumstances" — so the validator rejected the plan.

### Why it happened

The original reserved-paths design treated every reference file as completely immutable. That worked for login-validation tests (PR #7, #9 — purely new files, no extension). But page objects in a POM framework legitimately **grow**:

- Adding sort tests → needs `select_sort_option()` on InventoryPage
- Adding cart tests → needs `add_to_cart()` on InventoryPage
- Adding checkout tests → needs new methods on multiple pages

The framework had no way to model "page object that may be extended additively." Both the LLM and the validator were doing the right thing under the wrong design.

### Fix — clean two-tier file policy

| Tier | Behavior | Example |
|---|---|---|
| **RESERVED** | Never modified. Style baseline. | `features/login.feature`, `tests/step_defs/test_login.py`, `pages/login_page.py` |
| **EXTENDABLE** | May be modified to add new methods, but existing methods/signatures must be preserved. Stage 2 receives current file contents. | `pages/inventory_page.py`, `pages/base_page.py` |
| **NEW** | LLM creates from scratch. | Anything else |

The split is config-driven, app-agnostic, and reusable — onboarding any new app means listing your reference triplet in `reserved_paths` and your existing-page-objects-that-may-grow in `extendable_paths`.

### Files changed

| File | Change |
|---|---|
| `config/config.yaml` | Split `reserved_paths` into `reserved_paths` + `extendable_paths` blocks. Reference files stay reserved; page objects move to extendable. |
| `agents/app_context.py` | Added `extendable_paths` field on the `AppContext` dataclass plus a `extendable_paths_normalized()` helper. Updated `load()` to read the new config block. |
| `agents/agent2_coder.py` | Renamed `validate_no_reserved_paths` to `validate_paths_against_policy` with two-tier logic. New `_build_extendable_paths_block()` renders the extendable list for the prompt. New `_read_extendable_file_content()` reads the current file from disk when an extendable file is being modified. Stage 2 prompt rendering now injects `{existing_file_block}` containing the current content for extendable files. |
| `prompts/agent2_coder_plan.md` | Replaced the single "RESERVED — DO NOT TOUCH" section with TIER 1 / TIER 2 / TIER 3 explanation. The LLM now understands when to set `is_new_file=false` to extend a page object. |
| `prompts/agent2_coder_generate.md` | Added `{existing_file_block}` placeholder so when Stage 2 generates content for an extendable file, the LLM sees the current methods and preserves them. |
| `tests/unit/test_path_policy.py` | **NEW** — 14 unit tests covering every scenario including the exact SCRUM-12 case that broke production. Pin down the validator contract so future refactors can't silently regress it. |

### How extendable mode works end-to-end

1. **Stage 1** — LLM is shown the extendable list with the rule: "set `is_new_file: false` for these; do NOT remove existing methods."
2. **Validator** — accepts plan if extendable files are marked `is_new_file=false`; rejects if marked `is_new_file=true` (would wipe existing).
3. **Stage 2** — for each extendable file in the plan, Agent 2 reads the file from disk and injects it under "EXTENDING EXISTING FILE — preserve all methods below" in the prompt.
4. **LLM** outputs the complete new file (existing methods + new methods).
5. **GitHub commit** — `create_or_update_file` already handles both create and update. No client changes needed.

### Verification

- **110 unit tests pass** (was 90 before adding the new tests)
- **1 unrelated pre-existing failure** unchanged (`test_empty_quoted_value_with_parsers_parse_REJECTED` — was already failing in the uploaded code before this fix)
- All 14 new path-policy tests pass, including the regression test that mimics the exact SCRUM-12 scenario
- All prompt placeholders match all `agent.replace()` calls (audited)
- No new hardcoded values — everything app-specific lives in `config.yaml` or `prompts/app_context.md`

### Migration

If you have config.yaml from before this hotfix, update the `app_under_test:` block:

```yaml
# OLD (one big list — broken for extension)
reserved_paths:
  - "features/login.feature"
  - "tests/step_defs/test_login.py"
  - "pages/login_page.py"
  - "pages/inventory_page.py"   # ← problematic: blocks extension
  - "pages/base_page.py"

# NEW (two tiers — reference vs page-object-that-grows)
reserved_paths:
  - "features/login.feature"
  - "tests/step_defs/test_login.py"
  - "pages/login_page.py"

extendable_paths:
  - "pages/inventory_page.py"
  - "pages/base_page.py"
```

### Onboarding a new app — updated guidance

When adding `app_under_test:` for a new app:
- Put your **reference triplet** (the one hand-written test you want the LLM to mimic) in `reserved_paths`.
- Put **page objects that exist already and may need new methods added** in `extendable_paths`.
- Everything else (new features, new page objects) — the LLM creates fresh, no config needed.

---

# Original Phase A+B+C Refactor

(Notes from the initial refactor session preserved below.)

## TL;DR

- ✅ All app-specific knowledge moved to `config.yaml` and `prompts/app_context.md`
- ✅ Agent code now reads AUT info via a new `AppContext` module
- ✅ Documentation consolidated from 4 docs into 1 GUIDE.md
- ✅ README rewritten to reflect actual implementation (no aspirational claims)
- ✅ Empty `orchestrator/` folder and `dry_run_output.txt` removed
- ✅ All agents now fast-fail on missing env vars at startup
- ✅ Silent error swallowing in `JiraClient._link_to_story` replaced with loud, re-raised errors
- ✅ New `docs/APP_INVENTORY_SCHEMA.md` documents the page-inventory JSON shape *(since merged into REUSE_FOR_NEW_PROJECT.md, July 2026)*
- ✅ Zero unit-test regressions: 90/90 runnable tests pass identically before and after

## Files added

| File | Purpose |
|---|---|
| `agents/app_context.py` | New module — central loader for `app_under_test` config. Exposes `AppContext.load()` with helpers for reference files, page inventory, reserved paths. |
| `prompts/app_context.md` | App-specific context block (test users, error messages, page flow). Injected into Agent 1's prompt at runtime. The single file to edit when onboarding a new app's analyst guidance. |
| `docs/GUIDE.md` | Consolidated guide — replaces ARCHITECTURE.md + BRANCH_NAMING.md + CONFIGURATION.md + HUMAN_APPROVAL_GATE.md. |
| `docs/APP_INVENTORY_SCHEMA.md` *(merged into REUSE_FOR_NEW_PROJECT.md, July 2026)* | Documents the JSON shape of `app_inventory/<app>.json`. |
| `CHANGES.md` | This file. |

## Files modified

### `config/config.yaml`

**New `app_under_test:` block** at the top of the file. This is now THE single source of truth for AUT-specific values:

```yaml
app_under_test:
  name: "SauceDemo"
  base_url: "https://www.saucedemo.com"
  inventory_file: "app_inventory/saucedemo.json"
  reference_files:
    feature: "features/login.feature"
    step_def: "tests/step_defs/test_login.py"
    page_object: "pages/login_page.py"
  reserved_paths:
    - "features/login.feature"
    - "tests/step_defs/test_login.py"
    - "pages/login_page.py"
    - "pages/inventory_page.py"
    - "pages/base_page.py"
```

Previously these values were hardcoded as Python constants in agent files. Now they live in YAML.

### `agents/agent1_analyst.py`

**Before:** Hardcoded prompt assumed SauceDemo (test users, error messages baked into the prompt template).

**After:**
- Loads `AppContext` at run start
- Reads `prompts/app_context.md` (a separate, editable app-specific block)
- Substitutes `{app_name}`, `{app_base_url}`, `{app_context}` into the main prompt template
- Calls `validate_required_env(...)` at startup (fast-fail on missing config)

### `agents/agent2_coder.py`

**Before:**
- Module-level constant `RESERVED_PATHS = {"features/login.feature", ...}` hardcoded
- `load_reference_files()` and `load_page_inventory()` defined inline with hardcoded paths
- One large `run()` function (~270 lines) doing many things

**After:**
- Reserved paths come from `AppContext.reserved_paths_normalized()`
- Reference loading / page inventory loading delegate to `AppContext`
- `run()` extracted into smaller helpers: `_select_new_test_cases`, `_validate_generated_files`, `_print_dry_run_preview`, `_resolve_unused_revision_branch`
- Prompt placeholders now include `{app_name}`, `{reserved_paths_block}`, `{reference_*_path}` (rendered from config)
- `validate_required_env(...)` at startup

### `agents/agent3_reviewer.py`

**Before:** Same hardcoding as Agent 2.

**After:** Same fix — uses `AppContext`. Prompt template now substitutes the configured reference file paths.

### `agents/agent5_reporter.py`

**Before:** No env-var validation at startup; first failure was a deep API error.

**After:** Calls `validate_required_env(REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS)` in `main()`. No structural changes — Agent 5 doesn't touch reference files or app inventory.

### `agents/jira_client.py`

`_link_to_story` previously caught a bare `except Exception` and logged a warning. This silently masked real failures (a missing link means Agent 2 can't find the test cases via `linkedIssues`).

**After:** Catches `JIRAError` specifically, logs at `ERROR` level with status code and response text, and **re-raises** so the caller can decide whether to abort the batch.

### `prompts/agent1_analyst.md`

App-agnostic. App-specific content (SauceDemo users, error messages) moved to `prompts/app_context.md`. Main template uses placeholders:
- `{app_name}` — name from config
- `{app_base_url}` — URL from config
- `{app_context}` — full content of `app_context.md` (or empty string if missing)
- `{story_text}` — the Jira story (unchanged)

### `prompts/agent2_coder_plan.md`

App-agnostic. New placeholders:
- `{app_name}` — for context heading
- `{reserved_paths_block}` — markdown bullet list rendered from config's `reserved_paths`
- `{reference_feature_path}`, `{reference_step_def_path}`, `{reference_page_object_path}` — file paths from config
- `{reference_*_content}` — file contents (unchanged)

The reserved-paths section, which used to hardcode `features/login.feature` etc., now reads from config.

### `prompts/agent2_coder_generate.md`

App-agnostic. Same placeholders as the plan prompt, plus the per-file metadata that was already there. Removed the SauceDemo-specific worked example (now uses generic `valid_user`/`valid_password` placeholder examples).

### `prompts/agent3_reviewer.md`

App-agnostic. Reference file paths now come from config substitution. Removed concrete references to `LoginPage`, `InventoryPage`, `BasePage` — generalized to "page object classes."

### `README.md`

Rewritten. The previous README claimed features that did not exist (e.g., LangGraph orchestration as a load-bearing component). The new README:
- Accurately describes what each agent does
- Explains why Agent 4 has no Python file (it's a workflow file by design)
- Points readers to GUIDE.md for depth
- Has a new "Onboarding a new application" section that walks through the AUT swap

## Files removed

| File | Reason |
|---|---|
| `dry_run_output.txt` | Stale debugging artifact that should never have been committed. |
| `orchestrator/` (folder) | Empty placeholder for future LangGraph wiring. Not load-bearing. Documenting placeholders implies more than is there — better to remove and add later if needed. |
| `docs/ARCHITECTURE.md` | Consolidated into `docs/GUIDE.md`. |
| `docs/BRANCH_NAMING.md` | Consolidated into `docs/GUIDE.md`. |
| `docs/CONFIGURATION.md` | Consolidated into `docs/GUIDE.md`. |
| `docs/HUMAN_APPROVAL_GATE.md` | Consolidated into `docs/GUIDE.md`. |

## Files retained unchanged

- `agents/gherkin_analyzer.py` (renamed from test_inventory.py, June 2026) — has zero SauceDemo coupling. The file is internally well-organized (953 lines but with clear `# ─── ... ───` section headers separating concerns). It has thorough unit-test coverage. **Splitting it was considered and skipped** because the cost (changing imports across the codebase, risking test breakage) exceeds the benefit (no reusability gain — the file is already app-agnostic).
- `agents/jira_client.py` (mostly) — only `_link_to_story` was tightened. The rest is a clean adapter.
- `agents/github_client.py` — already uses targeted `GithubException`. No broad except patterns to tighten.
- `agents/llm_client.py` — already app-agnostic.
- `agents/schemas.py` — already app-agnostic.
- `config/__init__.py`, `config/paths.py` — already app-agnostic.
- All test files in `tests/unit/` — all 90 runnable tests pass identically before and after the refactor.
- All workflow files in `.github/workflows/` — they delegate to Python modules, no SauceDemo references.
- `app_inventory/saucedemo.json` — kept as the canonical example (schema now documented in REUSE_FOR_NEW_PROJECT.md).
- All ADRs in `docs/` — historical decision records, retained.

## Verification

Unit tests run identically against original and refactored code:

```
Original:    7 failed, 90 passed
Refactored:  7 failed, 90 passed
```

The 7 failures are identical in both — all environmental (PyGithub/jira not installed in this sandbox) plus one pre-existing test that was already broken. **Zero refactor-introduced regressions.**

## How to onboard a new app (post-refactor)

You should not need to touch any Python file. The full procedure is in `docs/GUIDE.md` under "Onboarding a new app." High-level:

1. Edit the `app_under_test:` block in `config/config.yaml`
2. Drop a new `app_inventory/<your-app>.json`
3. Replace `prompts/app_context.md` with your app's analyst guidance
4. Author one reference test (`features/<x>.feature` + `tests/step_defs/test_<x>.py` + `pages/<x>_page.py`)

That's it.

## What's intentionally NOT included in this refactor

- **Splitting `gherkin_analyzer.py` (then named test_inventory.py)** into multiple modules. Considered; deferred. The file is well-organized internally and changing imports across the codebase risks breaking tests for no reusability gain.
- **LangGraph orchestration.** The empty `orchestrator/` folder was removed. Workflows currently orchestrate via GitHub Actions, which works fine for the current scope. LangGraph wiring can be added later as a real implementation, not a placeholder folder.
- **End-to-end smoke test of the refactor.** Requires real Jira + Gemini + GitHub credentials. Verification in this refactor is via unit tests + import smoke checks. The next session is the right place for an E2E run with a fresh Jira story.

## Migration checklist (if you have an existing local clone)

1. Pull the changes (or apply this refactor's files on top of your clone)
2. `git status` — verify the deletions in step 3 below
3. Manually delete the removed files if they're still in your tree:
   - `dry_run_output.txt`
   - `orchestrator/` directory (if empty)
   - `docs/ARCHITECTURE.md`
   - `docs/BRANCH_NAMING.md`
   - `docs/CONFIGURATION.md`
   - `docs/HUMAN_APPROVAL_GATE.md`
4. Verify your `.env` is intact — refactor changes none of the env-var names
5. `pytest tests/unit/ -v` — should pass with the same numbers as before
6. Run a smoke test: `python -m agents.agent1_analyst --story <YOUR-KEY> --dry-run`