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

## Points that matter when writing test cases

- **Validation appears AS YOU TYPE**, under the field. A test case that submits
  the form and then checks for the message describes the wrong interaction.
- **Employee Name is an autocomplete, not a text box.** Typing a full name
  without clicking a suggestion leaves the field invalid, and the form will not
  save. A test case must say "select from the suggestions".
- **User Role and Status are custom dropdowns, not native selects.** Say
  "choose X from the User Role dropdown"; the interaction is click-then-click.
- **DO NOT write test cases that actually save a user.** This is a shared public
  demo: a saved user persists, and the next run fails with "Already exists".
  Validation-only cases that never click Save are safe. If a case genuinely
  must save, it has to generate a unique username and delete the user afterwards
  — say so explicitly in the steps.

## Grouping guidance

The five password rules are ONE test case exercised with several inputs, not
five test cases. They share a single behaviour ("the password policy is
enforced") and differ only by data.

"Username too short", "username already taken" and "required field empty" are
DIFFERENT behaviours with different messages, so they earn separate cases.