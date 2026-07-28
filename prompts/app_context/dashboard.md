# Dashboard module

The landing page after a successful login: `/web/index.php/dashboard/index`.

## What is on it

- A breadcrumb header reading **Dashboard**
- The left-hand module menu (present on every authenticated page)
- The top-right user dropdown, holding About, Support, Change Password, Logout
- Widget panels: Time at Work, My Actions, Quick Launch, Buzz Latest Posts,
  Employees on Leave Today, Employee Distribution

## Behaviour worth testing

| Action | Result |
|---|---|
| Successful login | Dashboard loads, breadcrumb reads "Dashboard" |
| Click a left-menu module | Navigates to that module; breadcrumb changes |
| Click the user dropdown | Menu opens with Logout among the options |
| Logout | Returns to the login form |
| Navigate back after logout | Login form again — the session is NOT restored |

## Points that matter when writing test cases

- **The breadcrumb is the cheapest proof that login succeeded.** Prefer it over
  a URL assertion, because the SPA changes the URL before rendering.
- **The user dropdown must be OPENED before Logout exists.** A test case that
  says "click Logout" without opening the menu describes something impossible.
- **Widget CONTENT is live data on a shared demo.** "Employees on Leave Today"
  changes constantly. Assert that a widget is PRESENT, never on its numbers.

## Grouping guidance

Menu navigation is ONE test case with several steps, not one per module. The
behaviour under test is "the menu navigates", not "the Admin link works" and
"the PIM link works" as separate concerns.