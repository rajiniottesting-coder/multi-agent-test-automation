# Signup / Login page

One page at `/login` carries TWO independent forms, side by side:

- **"Login to your account"** — email + password, for an existing account
- **"New User Signup!"** — name + email, the first step of registration

Both forms have an email field. A selector written loosely enough to match
"the email input" will match BOTH, which Playwright rejects as a strict-mode
violation. Every field on this page must be addressed through its own form's
inventory key — never a generic one.

## Signing up is two steps

Submitting the signup form does not create the account. It navigates to a
fuller form (`/signup`) asking for title, password, date of birth, address and
contact details. The account exists only after that second form is submitted,
and the app then shows an "ACCOUNT CREATED!" page.

A scenario that says "register a new user" therefore spans two pages — and the
second one is NOT in the inventory, so generated code cannot reach any of its
fields and the account is never created.

**Do not write a test case that registers.** Nothing downstream of it can be
implemented: not creating the account, not confirming it, not signing in as it,
not deleting it. Use the shared `registered` role and assert relatively. See
`account.md` for what to do when a test case seems to need a fresh identity.

## Failure messages

- Wrong credentials → "Your email or password is incorrect!"
- Signing up with an address that already exists → "Email Address already
  exist!"

Both render as text on the same page — there is no redirect, and no toast.
Assert on the message text.

## Logging out

The "Logout" link in the top navigation returns to `/login`. It is only present
while logged in, so its presence or absence is a reliable readiness signal for
"am I authenticated".