@contact
Feature: Automation Exercise Contact Us validation
  As a visitor
  I want the Contact Us form to reject incomplete submissions
  So that required fields are enforced

  Background:
    Given I am on the Contact Us page

  @negative @validation @contact
  # JIRA: SCRUM-310 (hash: 75e66d75) owner: SCRUM-291
  Scenario: Contact Us form rejects submission when the Subject is empty
    When I fill in the contact form with name "Demo Reviewer", email "demo.subscriber@example.com", subject "" and message "I would like to know more about your Blue Top product."
    And I submit the contact form
    Then no contact success message should be shown on the Contact Us page
    And I should remain on the Contact Us page
