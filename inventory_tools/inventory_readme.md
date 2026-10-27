# Inventory toolkit

Point it at a web application, crawl it, and get a JSON file describing every
element worth automating — with a selector for each that has been **measured
against the live page**, not guessed from the DOM.

Standalone. Nothing here names an application; the only file you edit is
`config/config.yaml`.

---

## Setup

```powershell
pip install -r requirements.txt
playwright install chromium
```

Edit **`config/config.yaml`** — three lines matter:

```yaml
app_under_test:
  name: "Your Application"
  base_url: "https://your-app.example"     # no trailing slash
  inventory_file: "app_inventory/app.json"
```

Credentials go in the environment, never on the command line, where they end up
in shell history and CI logs:

```powershell
$env:INVENTORY_USER = "someone@example.com"
$env:INVENTORY_PASS = "..."
```

---

## The sequence

```
  1  generate_inventory   crawl -> one draft per auth state
  2  promote_draft        merge drafts, strip third-party embeds
  3  YOU                  curate: resolve the review blocks, add meaning
  4  verify_locators      measure every selector against the live page
```

Step 3 takes the most time and is the only one that cannot be automated. A
crawler records what a page **contains**; only a person knows what it **means**.

---

# 1 · generate_inventory

| Flag | Default | |
|---|---|---|
| `--urls` | — | comma-separated paths, joined onto `base_url` |
| `--crawl` | off | follow same-origin links instead of a fixed list |
| `--max-pages` | `20` | stop after this many pages |
| `--max-depth` | `2` | how many link-hops from the start |
| `--test-attrs` | from config | attributes to treat as first-class hooks |
| `--login-url` | — | path to the sign-in form |
| `--username-selector` `--password-selector` `--submit-selector` | auto | override when the form is unusual |
| `--username` / `--password` | env | prefer `INVENTORY_USER` / `INVENTORY_PASS` |
| `--no-login` | off | skip sign-in entirely |
| `--headed` | off | **watch the crawl happen** |
| `--output` | `app_inventory/generated.draft.json` | where the draft lands |

`--urls` and `--crawl` combine: the URLs become starting points, and `--crawl`
follows links from each.

## Combinations worth knowing

**A named list** — what to use once you know the app.

```powershell
python -m scripts.generate_inventory --no-login `
  --urls "/,/search,/item/1" --output app_inventory/public.draft.json
```

**Explore an unfamiliar app.**

```powershell
python -m scripts.generate_inventory --no-login --crawl `
  --max-pages 15 --max-depth 2 --output app_inventory/survey.draft.json
```

**Shallow and wide** — the main sections, without wandering into pagination.

```powershell
python -m scripts.generate_inventory --no-login --crawl `
  --max-depth 1 --max-pages 40 --output app_inventory/top-level.draft.json
```

**Narrow and deep** — follow one area a long way down.

```powershell
python -m scripts.generate_inventory --crawl --urls "/admin" `
  --max-depth 4 --max-pages 10 --login-url /login `
  --output app_inventory/admin.draft.json
```

**Watch it work.** The most useful flag when something is wrong: you see the
sign-in happen, the pages load, and any redirect or ad interstitial.

```powershell
python -m scripts.generate_inventory --headed --login-url /login `
  --urls "/dashboard" --output app_inventory/debug.draft.json
```

## Choosing max-pages and max-depth

`--max-depth 1` is the site's main navigation. `2` reaches most of a small app.
`3` and beyond usually finds pagination and detail pages that are all the same
shape — many pages that add nothing. Start at `--max-depth 1 --max-pages 10`
and widen only if pages you expected are missing.

## Crawl one authentication state at a time

A single crawl cannot be both signed in and signed out, and the two see
different pages.

```powershell
# signed out - including the sign-in page, which you cannot be signed in to see
python -m scripts.generate_inventory --no-login `
  --urls "/,/login" --output app_inventory/public.draft.json

# signed in
python -m scripts.generate_inventory `
  --login-url /login `
  --username-selector "input[name='username']" `
  --password-selector "input[name='password']" `
  --submit-selector "button[type='submit']" `
  --urls "/dashboard,/account,/cart" `
  --output app_inventory/auth.draft.json
```

If credentials are supplied and sign-in does **not** succeed, the crawl aborts
rather than reporting. Every page would be the login screen, and an inventory
built from that is worse than none: it looks complete and describes one page
over and over.

---

# 2 · promote_draft

```powershell
python -m scripts.promote_draft `
  app_inventory/public.draft.json app_inventory/auth.draft.json `
  -o app_inventory/app.json
```

Takes any number of drafts. Removes third-party embeds. Keeps everything
belonging to your application, **including elements it considers fragile** —
those are republished under `_selectors_to_improve` so you can see and fix
them, rather than discovering later that they were silently dropped.

| Flag | |
|---|---|
| `--dry-run` | report what would change; write nothing |
| `--drop-fragile` | delete fragile elements outright. Rarely wanted |

---

# 3 · The JSON, section by section

## A curated page

`<KEY-A>` and the rest are PLACEHOLDERS - substitute your application's own
words. They are deliberately meaningless: an example that used plausible names
would be indistinguishable from a real key, and a reader could not tell which
parts of the shape are required and which were invented for illustration.


```json
{
  "pages": {
    "<PAGE>": {
      "url": "/<path>",
      "components": ["<COMPONENT>"],
      "readiness": "<KEY-A>",
      "page_object_file": "pages/<name>_page.py",
      "page_object_class": "<Name>Page",
      "elements": {
        "<KEY-A>": "input[placeholder='...']",
        "<KEY-B>": ".<repeating-class>",
        "<KEY-C>": ".<repeating-class> .<cell-class>:nth-child(3)",
        "<KEY-D>": "role=button[name='...']",
        "<KEY-E>": "text=...",
        "<KEY-F>": "text=..."
      },
      "multi_match": ["<KEY-B>", "<KEY-C>", "<KEY-D>"],
      "conditional": ["<KEY-F>"],
      "elements_notes": {
        "<KEY-B>": "One per row. Read with get_count() or
          get_all_texts(); reach ONE with click_in_row(), never by index.",
        "<KEY-F>": "Rendered ONLY when the search matches nothing -
          the mirror of <KEY-B>. Exactly one of the two is present.",
        "_starting_state": "This table is shared: other users add and delete
          records while a run is in progress. Assert relatively - that the
          record this test created is present - never an absolute count."
      },
      "errors": {
        "<KEY-G>": "the exact text the app shows"
      }
    }
  }
}
```

## The fields you write

| Field | What it is for |
|---|---|
| `url` | Path only, joined onto `base_url`. Use `{id}` for a template, plus `url_sample` with a real one |
| `components` | Which stories route to this page. A story tagged `HR` receives it; others do not, which keeps prompts small |
| **`readiness`** | The ONE element proving the page loaded **in every state it can be in**. See below — this is the field most often got wrong |
| `elements` | The working set: `key -> selector`. The key is nearly all the signal a generator gets, so it must say what the thing IS |
| `multi_match` | Keys whose selector matches several elements. A declaration, not a fault — `verify_locators` stops reporting them |
| `conditional` | Keys that do not exist on page load: a modal, an error, an empty-state banner |
| `removed` | Keys of elements a change story removed, kept only while a test asserts they are gone. Written by Agent 0's context update; missing reads as expected, present again as drift; the nightly inventory update deletes the key when no test names it |
| `elements_notes` | The highest-value field in the file, and the one a crawler can never produce. Behaviour, traps, starting state |
| `errors` | Validation messages the app shows, so a negative test asserts real text |

### readiness — the one to get right

A readiness probe has to hold in **every** state the page can be in. A heading
that a search replaces, or a banner that only shows when a list is empty, is
true in one state and false in another — a probe built on one reports "not
loaded" for a page that loaded perfectly well.

Pick something structural that survives all of them: a search box, a table
container, a page-level heading that does not change.

### elements_notes and the underscore prefix

Inside `elements_notes` every other key is an element **name**, so a key
beginning with `_` means "a note about the PAGE, not one element":

```json
"_starting_state": "...", "_url": "...", "_naming": "..."
```

**Keep those.** The prefix means something different at page and top level,
where it marks a review block to act on and delete.

---

# The review blocks

Every one follows the same contract: **flag, do not invent, do not silently
drop.** Each names work to do. Do the work, then delete the block.

| Block | What it means | What to do |
|---|---|---|
| `_unresolved_selectors` | **Measured** on the live page and matched ZERO elements. Wrong as written | Fix or delete. Nothing else in the file is more certainly broken |
| `_ambiguous_selectors` | One selector was produced for MORE THAN ONE element. Playwright is strict, so this raises at run time | Give each a distinct selector, or declare it `multi_match` if it really is a family |
| `_selectors_to_improve` | Resolve today, but only as a **structural path** — they describe where an element sat during this crawl, not what it is | Find a real handle: a class, a role, its text. `verify_locators --selector` is the fast loop |
| `_unstable_selectors` | No durable handle existed, only a fragile css fallback | Ask for a `data-test` attribute in the app. Failing that, prefer text or role over a path |
| `_fragile_selectors` | The crawl-time form of the row above | Same remedy |
| `_unnameable_elements` | The key carries no purpose — `element_alt`, `path4_elements`, `button_button`. They RESOLVE, which is what makes them a trap: they pass every check and tell a generator nothing | Name the ones a test needs and move them back into `elements`; delete the rest |
| `_collapsed_families` | Several keys were folded into one family. Members are listed | Check the collapse was right. If it was not, restore the members from this block |
| `_repeated_widgets_needing_a_handle` | One repeated widget with NO selector matching all its members — the varying part is the element's name, not its position | Find the shared class, add ONE key, declare it `multi_match`, delete the members |
| `_families_without_a_shared_handle` | The older form of the row above | Same remedy |
| `_third_party_elements` | Inside an ad or recommendation embed. Their text rotates per impression | Delete. `promote_draft` removes these for you |
| `_interaction_required` | Controls that reveal content a DOM snapshot cannot see — a crawler never clicks | Add the revealed elements by hand, and declare them `conditional` |
| `_inventory_conventions` | The five-step checklist, written into every draft | Work through it, then delete |

### Delete outright, no action needed

`implementation_status`, `title_seen`, and any `AUTO-DRAFT` suffix on
`page_object_file`.

---

# 4 · verify_locators

Opens a real browser and boxes every match — **green** exactly one, **amber**
several, **red** none. Every match is boxed and numbered, so the picture agrees
with the count.

| Flag | Default | |
|---|---|---|
| `--inventory` | from config | verify a different file — **use this for a draft** |
| `--page` | all | one page key only |
| `--selector` | — | check ONE selector without touching the inventory |
| `--url` | — | the path for `--selector` |
| `--only-problems` | off | skip the ones that resolve cleanly |
| `--pause` | `0.6` | seconds to hold each highlight |
| `--headless` | off | no window — for CI |
| `--no-login` | off | public site, or the sign-in page itself |
| `--login-url` and the three selector overrides | | as the crawler |

## Checking one specific locator

The fastest loop when a selector is wrong — nothing is read from or written to
the inventory:

```powershell
python -m scripts.verify_locators --selector "<a class you found in devtools>" `
  --url /employees --login-url /login `
  --username-selector "input[name='username']" `
  --password-selector "input[name='password']" `
  --submit-selector "button[type='submit']"
```

Try replacements before committing one:

```powershell
--selector "text=Add to cart"
--selector "role=button[name='Sign in']"
--selector "input[placeholder='Search']"
```
## Checking one fullpage
python -m scripts.verify_locators --pause 3 `                  
--login-url /web/index.php/auth/login `
--username-selector "input[name='username']" `
--password-selector "input[name='password']" `
--submit-selector "button[type='submit']" `   
--page web_index_php_pim_view_employee_list --only-problems

## Verifying a draft rather than the curated file

```powershell
python -m scripts.verify_locators --inventory app_inventory/pim.draft.json --only-problems
```

Without `--inventory` it reads whatever `config.yaml` points at, which is
usually not the draft you just produced.

## The verdicts

| | |
|---|---|
| `OK` | one match |
| `STALE` | zero matches — the selector no longer resolves |
| `AMBIG` | several matches, and the key is **not** declared `multi_match` |
| `FAMILY` | several matches, and it **is** declared — expected |
| `COND` | zero matches, and the key is declared `conditional` — expected |
| `GONE` | zero matches, and the key is declared `removed` — expected |
| `BACK` | one or more matches, and the key is declared `removed` — the removed element is on the page again |
| `REDIRECTED` | the page sent us elsewhere; reported once instead of fifty times |

`FAMILY`, `COND` and `GONE` are why writing those declarations down matters:
they turn fifty false alarms into silence.

---

# 5 · check_inventory_staleness

The same measurement, built for CI. Reports; never edits.

```powershell
python -m scripts.check_inventory_staleness --fail-on-drift
python -m scripts.check_inventory_staleness --json reports/drift.json
```

It never regenerates. A regenerated draft carries none of your curated notes,
families or conditionals, so a tool that "fixed" drift by regenerating would
delete exactly the knowledge that makes the inventory worth having.

The pipeline acts on its report selectively instead: the nightly Agent 0 drift
job runs it with `--compare --json` and `scripts.propose_inventory_update`
opens one pull request - a stale selector replaced when the crawl finds the
same-named element, a stale key no code names removed, uncovered elements
added, a page where most selectors are stale left alone. Notes, families and
conditionals stay. You review and merge it (core/inventory_update.py).

---

## Working with a repeated widget

A table, a product grid and a list of cards are **one widget**, not N elements.
The crawler folds siblings into a family where it can find a handle. Once you
have `rows` plus a cell family, a page object reaches one member by what it
SAYS, never by index:

```python
def remove_by_name(self, name: str) -> None:
    self.click_in_row(self.sel("<KEY-B>"), name,
                      self.sel("<KEY-D>"))

def count(self) -> int:
    return self.get_count(self.sel("<KEY-B>"))
```

Indexing across two families only works if they run in true lockstep, one
member each per row — and pages break that routinely. A listing that renders
each row's controls twice, once in the row and once in a hover overlay, gives
one family twice the members of its neighbour.

---

## When it goes wrong

**Every selector reports STALE.** Check `base_url` for a trailing slash, and
that the crawl reached the page. A sign-in wall or a bot check returns a page
that loads fine and contains none of what you expected. Re-run with `--headed`.

**Nothing improved after a fix.** The crawler runs at GENERATION time. Fixing
it changes nothing about a file already written — re-crawl, then verify with
`--inventory` pointed at the new draft.

**A public site fails at login.** Pass `--no-login`. Also needed for the
sign-in page itself.

**Selectors look like `body > div > div > div > p`.** The page offers no test
hooks, no ids and no stable classes. Ask for test attributes if you can;
failing that, prefer text or a role over a path.

**Selectors contain generated ids** like `oxd-input-1234` or `ember-4021`. The
crawler skips framework-generated ids deliberately — such an id changes on the
next build.

**A crawl finds far more pages than expected.** Lower `--max-depth`.

**A site with heavy bot protection** will serve CAPTCHAs and rate limits within
a few pages, and A/B-tested markup means a selector verified today may be
absent tomorrow for a reason that is not staleness. Worth reading the site's
terms first.

---

## What is not here

The wider framework — agents, validators, generated tests — is a separate
concern. This toolkit produces the inventory those consume, and stands on its
own for anyone wanting a measured, curated map of an application's elements.