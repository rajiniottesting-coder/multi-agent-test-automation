# Home page

The landing page at `/`. The inventory describes the site logo and the
newsletter subscription block; the subscription is the one behaviour here worth
a test case.

## Newsletter subscription

The footer has a `Subscription` heading, an email field and an icon-only submit
button - an arrow with no text. Entering an email address and submitting shows
**"You have been successfully subscribed!"** in place: no navigation, no toast.

- No sign-in is needed.
- The email address is test data, not a credential: write it literally in the
  test case, for example `demo.subscriber@example.com`.
- Nothing here records what happens with an empty or malformed address, or when
  the same address subscribes twice. Do not write a negative or a
  repeat-subscription test case for them - it would assert behaviour nobody has
  measured, and pass or fail for reasons unrelated to the story.

## Contact Us form

Reached by clicking 'Contact us' in the top navigation. The page shows a form with Name, Email, Subject and Message fields and a Submit button, and is available without signing in.

- Fill in name, email, subject and message and submit to see a success message confirming the details were submitted.
- Email is required: submitting with the Email field empty does not submit the form - no success message appears and the visitor stays on the Contact Us page with the form still shown. (Name, Subject and Message filled, Email empty is the rejected case.)
- Name, email, subject and message are test data, not credentials: write them literally, for example name `Demo Reviewer`, email `demo.subscriber@example.com`, subject `Product Enquiry`, message `I would like to know more about your Blue Top product.`

## Test Cases button

The home page has a "Test Cases" button. Clicking it navigates away from the home page to the Test Cases page (headed "Test Cases"), which lists the test cases. No login is required. See `test_cases.md`.
