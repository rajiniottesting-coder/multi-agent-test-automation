# Account lifecycle

## Registering inside a test

Registration is the cleanest source of test-owned data on this site: the test
creates the account, so nothing about it can be changed by anyone else.

Use a run-unique email address. The `unique_username` fixture pattern in
`tests/step_defs/conftest.py` exists for exactly this — derive the address from
it, e.g. `qa_<run-id>@example.com`, so two runs never collide on "Email Address
already exist!".

## The second form

After the signup form, the app asks for title, password, date of birth, name,
address, country, state, city, zipcode and mobile number. Country is a real
`<select>` — an ordinary dropdown, not a custom widget — so `select_option()`
works on it.

Submitting shows "ACCOUNT CREATED!" and a Continue button that lands the user
logged in.

## Deleting the account

"Delete Account" in the top navigation removes it and shows "ACCOUNT DELETED!".

A test that registers an account SHOULD delete it at the end. This site has no
admin cleanup, and abandoned accounts accumulate forever — the same litter
problem that makes shared demos unreliable, caused this time by us. Treat the
delete as part of the scenario, not an optional extra.
