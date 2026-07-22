# Module: Checkout

_Injected for stories tagged with the "Checkout" Jira Component._

## Behaviour
- Step One (`/checkout-step-one.html`): First Name, Last Name, Postal Code, then CONTINUE
- Step Two (`/checkout-step-two.html`): order summary with item total, tax, total; FINISH
- Complete (`/checkout-complete.html`): "Thank you for your order!"

## Known error messages (use these EXACTLY in expected results)
- Missing first name: `Error: First Name is required`
- Missing last name: `Error: Last Name is required`
- Missing postal code: `Error: Postal Code is required`

## Behavioural traps
- Step One validates in order — first name error before last name before postal code
- Step Two totals are computed (item total + tax); assert on the displayed total, not a hard-coded value

## Coverage hints
- Positive: full checkout with valid info reaches "Thank you for your order!"
- Negative: submit Step One with each field missing in turn
- Edge: checkout with multiple items; verify total = item total + tax