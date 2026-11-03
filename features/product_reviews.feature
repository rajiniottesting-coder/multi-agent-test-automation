@reviews
Feature: Product reviews
  As a shopper
  I want to write a review on a product's details page
  So that I can share feedback without needing to sign in

  Background:
    Given I am on the products listing page

  @smoke @reviews
  # JIRA: SCRUM-287 (hash: d805190e) owner: SCRUM-283
  Scenario: Write Your Review form is shown on a product's details page without signing in
    Then the products listing should show "Blue Top"
    And the login prompt should not be shown on the products page
    When I open the product details page for "Blue Top"
    Then the Write Your Review form should be shown on the product details page

  @negative @validation @reviews
  # JIRA: SCRUM-286 (hash: 3537c24e) owner: SCRUM-283
  Scenario: Review form rejects submission when a required field is left empty
    When I open the product details page for "Blue Top"
    Then the Write Your Review form should be shown on the product details page
    When I submit a review with name "Demo Reviewer" email "reviewer@example.com" and review text ""
    Then the review thank-you message should not be shown
    When I submit a review with name "" email "reviewer@example.com" and review text "Great quality and fast shipping!"
    Then the review thank-you message should not be shown
    When I submit a review with name "Demo Reviewer" email "" and review text "Great quality and fast shipping!"
    Then the review thank-you message should not be shown

  @smoke @reviews
  # JIRA: SCRUM-285 (hash: 9bde83dd) owner: SCRUM-283
  Scenario: Submit a complete review on a product's details page shows thank-you message
    Then the products listing should show "Blue Top"
    When I open the product details page for "Blue Top"
    Then the Write Your Review form should be shown on the product details page
    When I submit a review with name "Demo Reviewer" email "reviewer@example.com" and review text "Great quality and fast shipping!"
    Then I should see the review confirmation message "Thank you for your review."
