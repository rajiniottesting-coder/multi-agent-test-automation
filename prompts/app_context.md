# Application Context

The application under test is **SauceDemo**, a free demo e-commerce site for automation practice.

## Known test users

| Username | Password | Notes |
|---|---|---|
| `standard_user` | `secret_sauce` | Normal user, all flows work |
| `locked_out_user` | `secret_sauce` | Receives lockout error on login |
| `problem_user` | `secret_sauce` | UI bugs intentionally present |
| `performance_glitch_user` | `secret_sauce` | Slow page loads |

## Page flow

- Login form lives at the root path (`/`)
- After successful login, users land on the inventory page (`/inventory.html`)
- Cart is at `/cart.html`
- Checkout flow: `/checkout-step-one.html` → `/checkout-step-two.html` → `/checkout-complete.html`

## Known error messages (use these exactly in expected results)

- Invalid credentials: `Epic sadface: Username and password do not match any user in this service`
- Locked-out user: `Epic sadface: Sorry, this user has been locked out.`
- Empty username: `Epic sadface: Username is required`
- Empty password: `Epic sadface: Password is required`

## Testing notes

- Prefer concrete test data over abstract descriptions
- Use the standard user for happy-path scenarios
- Use locked_out_user / problem_user for specific negative scenarios where they're relevant
