# Account lifecycle

## Registration is NOT automatable here — do not write a test case for it

The inventory describes the FIRST signup form only: a name field, an email
field and a submit button, all on the sign-in page. The second form — title,
password, date of birth, address, country, state, city, zipcode, mobile — is
not in the inventory, so no page object can reach any of its fields, and the
account is never actually created.

Anything downstream of "register a new account" is therefore unreachable too:
creating an account, confirming it was created, signing in as it, or deleting
it. `_starting_state.fresh_identity_fixtures` is EMPTY, and that is the whole
statement.

So do NOT write test cases like these:

```
Register a new user and verify the account is created
Register, add a product, and verify the collection is empty for the new user
Delete the account and verify the confirmation
```

A run that tried spent four repair attempts inventing methods for a page that
does not exist — `complete_registration()`, `is_account_created()`,
`is_account_deleted()` — and the story was abandoned. Nothing downstream can
supply them, and rewording the step does not help.

**Use the shared `registered` role instead**, and remember what that means:
its cart and address book survive logout and survive the run, so a scenario
reusing it inherits whatever a previous run left. Assert RELATIVELY — that the
thing this test added is present, or is gone — which is true whatever the
account started with.

If a test case genuinely needs a fresh identity, it cannot be automated
against this application as it stands. Say so in `notes` rather than writing a
scenario nothing can implement. (To change that, the second signup form's
elements have to be added to the inventory first, and `unique_username`
re-listed under `fresh_identity_fixtures`.)

## The second form — described for reference, NOT reachable

After the signup form, the app asks for title, password, date of birth, name,
address, country, state, city, zipcode and mobile number. Country is a real
`<select>`, so `select_option()` would work on it. Submitting shows "ACCOUNT
CREATED!" and a Continue button that lands the user logged in.

None of those fields is in the inventory, so none of this is reachable from
generated code. It is recorded here so that whoever adds them later knows what
the form contains — not as a flow to write a scenario against.

## Deleting the account — same position

"Delete Account" in the top navigation removes it and shows "ACCOUNT DELETED!".

This only matters for an account a test created, and a test cannot create one
here. So there is nothing to delete and no cleanup step to write.

If registration is ever enabled — by adding the second form's elements to the
inventory — the delete becomes mandatory rather than optional: this site has no
admin cleanup, and abandoned accounts accumulate forever.