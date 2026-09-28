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
