# Login module

The login screen at `/web/index.php/auth/login`.

## Behaviour

| Action | Result |
|---|---|
| Valid credentials | Redirect to `/web/index.php/dashboard/index` |
| Wrong password | Banner: **Invalid credentials** |
| Unknown username | Banner: **Invalid credentials** (same message — the app does not reveal which field was wrong) |
| Empty username and/or password | Per-field message: **Required** |

## Points that matter when writing test cases

- **The error message does not distinguish username from password.** A test
  case asserting "the error says the password is wrong" would be wrong; the
  app deliberately says only "Invalid credentials".
- **Empty-field validation is per field, not a banner.** Leaving both fields
  empty produces TWO "Required" messages, one under each field.
- **The demo prints its own credentials on the login screen.** That is a
  property of the demo, not something a test should read.
- There is a "Forgot your password?" link. It navigates away from the login
  form, so any test that follows it must navigate back.

## Grouping guidance

"Wrong password", "unknown username" and "both wrong" all produce the SAME
outcome — the Invalid credentials banner. They are ONE test case with several
steps, not three test cases.

Empty-field validation is a DIFFERENT behaviour (a different message, shown in
a different place), so it earns its own test case.
