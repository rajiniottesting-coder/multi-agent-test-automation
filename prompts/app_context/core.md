# Application Context — Core

The application under test is **SauceDemo** (https://www.saucedemo.com), a free
demo e-commerce site for automation practice.

_Always injected. Cross-cutting knowledge: test users, page-flow map, global
conventions, testing notes. Module-specific rules live in the per-module files
(login.md, inventory.md, cart.md, checkout.md), injected by Jira Component._

## Known test users

| Username | Password | Notes |
|---|---|---|
| `standard_user` | `secret_sauce` | Normal user, all flows work |
| `locked_out_user` | `secret_sauce` | Receives lockout error on login |
| `problem_user` | `secret_sauce` | UI bugs intentionally present (broken images, wrong field behaviour) |
| `performance_glitch_user` | `secret_sauce` | Slow page loads — useful for timing-sensitive scenarios |

All users share the password `secret_sauce` — SauceDemo's public demo credentials.

## Page flow (end to end)

- Login form lives at the root path (`/`)
- After successful login, users land on the inventory/products page (`/inventory.html`)
- Clicking a product opens its detail page (`/inventory-item.html?id=<n>`)
- Cart is at `/cart.html`
- Checkout: `/checkout-step-one.html` → `/checkout-step-two.html` → `/checkout-complete.html`
- The hamburger menu offers: All Items, About, Logout, Reset App State

## Global conventions

- The cart badge (top-right) shows the current item count; absent when the cart is empty
- Login errors appear in a banner at the top of the login form, prefixed with `Epic sadface:`
- `problem_user` and `performance_glitch_user` are the levers for negative / timing scenarios

## Testing notes

- Prefer concrete test data over abstract descriptions
- Use `standard_user` for happy-path scenarios
- Use `locked_out_user` / `problem_user` for specific negative scenarios where relevant
- "Reset App State" (menu) clears the cart between scenarios when needed