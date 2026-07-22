# Module: Inventory

_Injected for stories tagged with the "Inventory" Jira Component (products page,
sorting, product detail)._

## Behaviour
- Lists 6 products, each with name, description, price, image, "Add to cart" button
- Adding toggles the button to "Remove" and increments the cart badge
- The sort dropdown is a NATIVE `<select>` with four options:
  Name (A to Z) [default], Name (Z to A), Price (low to high), Price (high to low)
- Clicking a product name/image opens its detail page with "Back to products"

## Behavioural traps
- The sort control is a real `<select>` — select an option, do not click a custom dropdown
- `problem_user` sees broken images and some non-functional "Add to cart" buttons
- Product order changes with the sort; assertions on "first product" must account for the active sort

## Coverage hints
- Positive: add a product (button toggles, badge increments); sort by each option
- Negative: with `problem_user`, some add-to-cart buttons misbehave
- Edge: sort by price and verify order; add all six products