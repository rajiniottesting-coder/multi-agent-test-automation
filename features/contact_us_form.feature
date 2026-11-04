@contact
Feature: Automation Exercise Contact Us form
  As a visitor
  I want to send a message through the Contact Us form
  So that I can get in touch with the store

  Background:
    Given I am on the Contact Us page

  @smoke @contact
  # JIRA: SCRUM-288 (hash: 51f395a9) owner: SCRUM-284
  Scenario: Visitor submits the form with all fields filled and returns home
    When I fill in the contact form with name "Demo Reviewer", email "demo.subscriber@example.com", subject "Product Enquiry" and message "I would like to know more about your Blue Top product."
    And I submit the contact form
    Then I should see the contact success message
    When I click the Home button
    Then I should be returned to the home page
