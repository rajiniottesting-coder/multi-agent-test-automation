# Application under test — OrangeHRM

OrangeHRM open-source demo, an HR management system.

- URL: https://opensource-demo.orangehrmlive.com
- The login form is at `/web/index.php/auth/login`; `/` redirects there.
- After a successful login the user lands on `/web/index.php/dashboard/index`.

## Known test roles

Test cases refer to users by ROLE. Credentials are never stored here, in the
app inventory, or in any generated file — they are resolved at runtime from
environment variables (GitHub Secrets in CI).

| Role | Behaviour |
|---|---|
| `admin` | Full administrator. Reaches every module. |

When a test case needs a valid login, name the ROLE (e.g. "log in as the admin
user"). Do NOT write usernames or passwords into test-case steps.

Invalid data is different and SHOULD be explicit: empty values, whitespace-only
values and deliberately-wrong passwords are test data, not credentials, so
write them literally in the test case.

## Page flow (end to end)

    login  →  dashboard  →  left-hand menu (Admin, PIM, Leave, Time,
                            Recruitment, My Info, Performance, Directory)

## Global rules

- The app is an Angular SPA. Navigation happens client-side, so a URL change
  is not always a full page load — assert on a visible element, not just the
  URL.
- The left-hand menu and the top bar are present on every page after login.
- Sessions expire. A test that idles will be bounced back to the login form.
- This is a SHARED public demo: other people are using it at the same time.
  Never write a test that depends on a specific record existing, on a count
  being stable, or on data it did not create itself.
