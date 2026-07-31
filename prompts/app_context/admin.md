# Admin module

`Admin > User Management > Users` — where system user accounts are managed.

Two screens are covered by the inventory:

| Screen | URL | Purpose |
|---|---|---|
| Users list | `/web/index.php/admin/viewSystemUsers` | search, filter, add, delete |
| Add User | `/web/index.php/admin/saveSystemUser` | create an account |

## Users list

Filters: Username, User Role, Employee Name, Status. Search applies all of
them together (AND). Reset clears them.

Results show as "(N) Records Found" above a table.

## Add User — fields and rules

| Field | Type | Rule |
|---|---|---|
| User Role | dropdown (Admin / ESS) | required |
| Employee Name | autocomplete | required; must be picked from the suggestions |
| Status | dropdown (Enabled / Disabled) | required |
| Username | text | required; minimum 5 characters; must be unique |
| Password | password | see the policy below |
| Confirm Password | password | must match Password |

### Password policy — the messages are exact

| Password | Message shown |
|---|---|
| fewer than 7 characters | Should have at least 7 characters |
| no digit | Your password must contain minimum 1 number |
| no lower-case letter | Your password must contain minimum 1 lower-case letter |
| contains a space | Your password should not contain spaces |
| valid | (no message) |

A mismatch between Password and Confirm Password shows **Passwords do not
match**. An empty required field shows **Required**.

## Add User — employee link (shared-demo dependency)

Creating a system user REQUIRES linking an existing employee, and the Employee
Name field is an autocomplete. Two facts about it, both learned the hard way:

**Query length is not the problem — the placeholder is.** A single letter DOES
fire the request (verified: `GET /api/v2/pim/employees?nameOrId=a`) and does
return suggestions; it just returns a long, slow, arbitrary list. Prefer 2-3
characters for a shorter and more predictable one. What matters far more is
that the prefix matches something: "adm" returns "No Records Found", because
Admin is a user ROLE, not an employee name.

**It renders `Searching....` first.** That placeholder is a real row in the
suggestion list, and it appears IMMEDIATELY. Any code that waits for "the
first suggestion" is satisfied by it, clicks it, selects nothing, and leaves
the field `Invalid` — after which Save is refused client-side with no request
sent and no toast, so the test dies several steps later on a missing
confirmation. WAIT FOR `Searching....` TO DISAPPEAR before reading the list.

Do not hand-roll that sequence. `BasePage.select_autocomplete_suggestion()`
does the whole thing in one call — type, wait for the loading row to go, click
the first real suggestion, return its text:

    self.select_autocomplete_suggestion(
        self.sel("employee_name_input"),
        self.sel("autocomplete_option"),
        "pet",
        placeholder="Searching",
        empty_text="No Records Found",
    )

Every hand-rolled version so far has selected the placeholder — via `nth=0`,
via "the first suggestion", via a `networkidle` heuristic. Use the helper. Do
not hard-code a full employee name — records on this environment
change constantly, and a name that exists today may not tomorrow. Take
whichever real suggestion the prefix returns.

This is the only acceptable dependency on data the test does not own. The
helper already fails with the prefix and every row that rendered, and reports
`No Records Found` as the application's empty state rather than a timing
problem — so a bad prefix is distinguishable from a broken wait.

A prefix known to work on 31 Jul 2026 is `pet`, returning `Peter Mac Anderson`.
Verify by hand before relying on it; employee records change here.

## Search results and empty state

The results summary text shows "(N) Records Found" when matches exist and
"No Records Found" when none do. Zero-result assertions must read this
text — never count table rows.

**Type into the search filters, do not fill them.** `fill()` sets the value and
the box visibly shows it, but this app's search inputs do not bind their model
from it: clicking Search then re-requests the unfiltered list, and an assertion
of "(1) Records Found" reads whatever the full list happens to be. That failure
is especially misleading because the screenshot shows the text sitting in the
box. `type_text()` sends real keystrokes and the model binds.

The list re-renders ASYNCHRONOUSLY after Search is clicked. Reading the
summary immediately returns the PREVIOUS value — the unfiltered total — so an
assertion of "(1) Records Found" sees "(34) Records Found" and fails while the
app is working correctly. It passes or fails depending on which wins the race,
which is what a flaky test looks like. Wait for the summary to contain the
expected text before asserting on it, rather than reading it and comparing.

## Confirmations

Save and Delete both show a transient success toast that disappears after a
few seconds — assert the toast BEFORE performing any further navigation.

Deleting a user row first opens a confirmation dialog ("Yes, Delete") which
must be accepted; the dialog renders only after the row's trash icon is
clicked. The trash icon is only unambiguous after the list has been searched
down to the single owned record.

Before clicking a row's trash icon, prove the list holds exactly ONE row - the
one this test created. The trash-icon family selector matches every row, so
clicking it unnarrowed is both a strict-mode violation and, on a public demo,
a good way to delete a record belonging to somebody else. Search by the unique
username first, assert the count, then use the first-row icon key.

Cancelling that dialog ("No, Cancel") is a NEGATIVE path: nothing is saved, so
NO toast appears. Do not read the toast with the waiting getter to prove its
absence — that waits for something that will never come and fails on timeout
instead of asserting. Use the non-waiting probe (`has_toast()`) and assert it
is False, then re-search to prove the record is still there.

## The Add User form will refuse to submit silently

Every field is validated client-side. If one is invalid, clicking Save sends NO
request at all: the page stays on the form, red messages appear under the bad
fields, and no toast is ever raised. A test that asserts on the toast then fails
several steps away from the real cause. Employee Name is the usual culprit -
typing into it is not selecting from it, and an unselected name reads `Invalid`.

## Dropdowns on the Add User form

User Role and Status are custom ARIA dropdowns, not `<select>` elements.
Open-then-click-an-option is the right interaction, but the option selector in
the inventory matches EVERY option at once, so clicking or waiting on it raises
a strict-mode violation. Use the BasePage helper that picks one option by its
text. The Employee Name field is an autocomplete and needs more care than the
dropdowns. While its request is in flight it renders a suggestion row reading
`Searching....`, which is a real element in the family: waiting for the first
suggestion to appear is satisfied by that placeholder, and clicking it selects
nothing while leaving the field `Invalid`. Type enough characters to be
unambiguous - a single letter returns a slow, crowded list - and then choose the
suggestion BY ITS TEXT, so the wait cannot be satisfied by the placeholder.

Asserting the save worked means asserting the toast APPEARED, which needs the
waiting reader. The non-waiting probe is for proving a toast did NOT appear.

## Reading a result row

A result row is a card whose text is every column concatenated — username,
user role, employee name, status and the action labels. Comparing that text
with `==` against a username can never match. Assert the username with the
cell-scoped selector (`row_username_cell`), or assert containment against the
row text. Row COUNT is still off limits on this shared demo: prove existence
and absence through `records_found` and the username the test itself created.

## Points that matter when writing test cases

- **Validation appears AS YOU TYPE**, under the field. A test case that submits
  the form and then checks for the message describes the wrong interaction.
- **Employee Name is an autocomplete, not a text box** — see "Add User —
  employee link" above for the required interaction.
- **User Role and Status are custom dropdowns, not native selects.** Say
  "choose X from the User Role dropdown"; the interaction is click-then-click.
- **Saving a user is allowed ONLY with owned data.** This is a shared public
  demo. A test case that saves must (a) use a run-unique username, and
  (b) delete that same user before the scenario ends. Fixed literal usernames
  must never be saved — they persist and break the next run with "Already
  exists". Validation-only cases that never click Save carry no such
  obligation.
- **Assert only on data this test created.** Never assert total record
  counts, never assert on pre-existing users or employees. The only
  permitted dependency on foreign data is the employee autocomplete above.

## Grouping guidance

The five password rules are ONE test case exercised with several inputs, not
five test cases. They share a single behaviour ("the password policy is
enforced") and differ only by data.

"Username too short", "username already taken" and "required field empty" are
DIFFERENT behaviours with different messages, so they earn separate cases.

A create -> search -> delete lifecycle is ONE test case: the delete is the
cleanup half of the create, not a separate behaviour. Splitting it leaves an
orphaned user on the shared demo if the second case never runs.