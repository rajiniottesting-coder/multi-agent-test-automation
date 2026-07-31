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

Creating a system user REQUIRES linking an existing employee: the Employee
Name field is an autocomplete — type a single common letter (e.g. "a") and
select the FIRST suggestion. Never assume a specific employee name exists;
employee records on this environment change constantly. This is the only
acceptable dependency on data the test does not own.

## Search results and empty state

The results summary text shows "(N) Records Found" when matches exist and
"No Records Found" when none do. Zero-result assertions must read this
text — never count table rows.

## Confirmations

Save and Delete both show a transient success toast that disappears after a
few seconds — assert the toast BEFORE performing any further navigation.

Deleting a user row first opens a confirmation dialog ("Yes, Delete") which
must be accepted; the dialog renders only after the row's trash icon is
clicked. The trash icon is only unambiguous after the list has been searched
down to the single owned record.

Cancelling that dialog ("No, Cancel") is a NEGATIVE path: nothing is saved, so
NO toast appears. Do not read the toast with the waiting getter to prove its
absence — that waits for something that will never come and fails on timeout
instead of asserting. Use the non-waiting probe (`has_toast()`) and assert it
is False, then re-search to prove the record is still there.

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