# Module: Login

_Injected for stories tagged with the "Login" Jira Component._

## Behaviour
- Username + password fields and a LOGIN button
- Successful login redirects to `/inventory.html`
- Errors render in a banner at the top; the banner has a clickable X to dismiss it

## Known error messages (use these EXACTLY in expected results)
- Invalid credentials: `Epic sadface: Username and password do not match any user in this service`
- Locked-out user: `Epic sadface: Sorry, this user has been locked out.`
- Empty username: `Epic sadface: Username is required`
- Empty password: `Epic sadface: Password is required`

## Coverage hints
- Positive: valid `standard` role login lands on the inventory page
- Negative: locked-out user, wrong password, empty username, empty password
- Edge: whitespace-only fields; both fields empty (username error takes precedence)