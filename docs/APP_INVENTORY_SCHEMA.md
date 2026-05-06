# App Inventory JSON Schema

The `app_inventory/<app>.json` file is the LLM's reference for the application under test (AUT) — its pages, selectors, methods, and conventions. This file is interpolated **verbatim** into Agent 2 and Agent 3 prompts, so its quality directly drives the quality of generated tests.

## Where it's used

- **Agent 2 (Coder)** — both Stage 1 (plan) and Stage 2 (per-file generation) prompts include the full inventory JSON. The LLM uses it to pick correct selectors and reference real page objects.
- **Agent 3 (Reviewer)** — uses the inventory to verify selectors in the PR match what the app actually exposes.

## How it's wired in

1. `config.yaml` — `app_under_test.inventory_file` points at the JSON
2. `agents/app_context.py` — `AppContext.load_page_inventory_json()` reads the file as a raw string
3. Agent prompts substitute `{page_inventory_json}` with that string

You can use any JSON shape you want — the LLM doesn't enforce a schema. The structure below is a **strong convention** that has worked well in practice. Deviating is fine; just make sure the LLM has enough context to reason about your app.

## Recommended structure

```json
{
  "app_name": "string — display name",
  "base_url": "string — root URL",
  "description": "string — 1-2 sentences of context",

  "test_users": {
    "<user_alias>": "string — credentials and notes"
  },

  "pages": {
    "<page_alias>": {
      "url": "string — relative path",
      "page_object_file": "string — path to existing page object .py file",
      "page_object_class": "string — Python class name",
      "elements": {
        "<element_alias>": "string — selector"
      },
      "key_methods": ["array of method signatures already implemented"],
      "implementation_status": "optional string — for partial/missing page objects"
    }
  },

  "common_errors": {
    "<error_alias>": "string — exact error message text"
  },

  "selector_strategy": {
    "preferred": "string — what selector type to use",
    "format": "string — example",
    "avoid": ["array of selector types to avoid"]
  },

  "test_patterns": {
    "framework": "string — e.g., Playwright + pytest-bdd + POM",
    "feature_files_in": "string — directory",
    "step_definitions_in": "string — directory",
    "page_objects_in": "string — directory",
    "naming_convention": {
      "feature_file": "string — pattern",
      "step_file": "string — pattern",
      "page_class": "string — pattern"
    }
  }
}
```

## Field-by-field guidance

### `app_name`, `base_url`, `description`
Short context the LLM uses to "set the scene." The description should be one or two sentences — enough to know what the app does without bloating the prompt.

### `test_users`
Map of user aliases to free-form descriptions. Each entry should contain credentials (or how to obtain them) plus any quirks. Examples:

```json
"standard": "standard_user / secret_sauce — normal user, all flows work",
"admin": "admin@test.com / Pass123! — full permissions",
"readonly": "viewer@test.com / Pass123! — cannot edit"
```

The LLM uses these aliases when picking concrete test data.

### `pages`
The most important section. **Each page is a complete unit** the LLM can reason about. Include:

- **`url`** — relative path. The LLM uses this to know where a page lives.
- **`page_object_file`** — relative path to the page object `.py` file. If the file doesn't exist yet, mark it `"... (NOT YET CREATED)"` so the LLM knows it may need to create one.
- **`page_object_class`** — Python class name (PascalCase).
- **`elements`** — map of semantic alias → selector string. The LLM picks elements by alias; the alias should describe intent (`login_button`), not appearance (`blue_button_top_right`).
- **`key_methods`** — list of method signatures already implemented on the page object. The LLM avoids reinventing these.
- **`implementation_status`** — optional. Use when the page object is partial or absent. Tells the LLM "you may need to extend this" or "you'll need to create this."

### `common_errors`
The exact error message strings the app produces. The LLM uses these in `Then I should see the error message "..."` assertions. Get them character-perfect — punctuation, capitalization, and trailing periods all matter.

### `selector_strategy`
Tells the LLM which selector type to use. Crucial for app-specific quirks:

- **SauceDemo:** `[data-test='X']` (stable, always present)
- **A typical SaaS app:** might use `[role='X']` or `text=Submit`
- **Legacy app:** might require XPath as a last resort

The `avoid` list helps the LLM steer clear of brittle selectors.

### `test_patterns`
Reinforces the project's structural conventions. The LLM uses this section to know where to put new files. Keep the directory paths and naming patterns aligned with what `config.yaml`'s `app_under_test.reference_files` points to.

## Tips for writing a good inventory

1. **Verbose is better than terse.** This file gets sent to the LLM as context — extra detail rarely hurts and often helps disambiguation. The 5–10KB JSON file is well under any token budget concern.

2. **Document what's missing.** If a page object doesn't exist yet, say so. The LLM is much better at "create this from scratch" than at "guess whether this exists."

3. **Use semantic element names.** `submit_button` > `btn_primary` > `[type=submit]`. The element name is the LLM's mental hook.

4. **Include error message text verbatim.** Not paraphrased. The exact string is what tests will assert against.

5. **Update when the app changes.** This file is a contract between you and the LLM. Stale selectors → broken generated tests. Keep it in sync with the real app.

## Validation

There is no JSON schema validator on this file — it's parsed as raw text and embedded in the prompt. The first time you'll catch errors is when generated tests fail. To smoke-test your inventory:

1. Write a single Jira test case that covers a known-working flow
2. Run `agent2_coder.py --story <KEY> --dry-run`
3. Inspect the generated code for selector accuracy
4. If selectors look wrong, the inventory is the most likely culprit

## Examples

The canonical reference is [`app_inventory/saucedemo.json`](../app_inventory/saucedemo.json). Use it as a template when authoring inventory for a new app.
