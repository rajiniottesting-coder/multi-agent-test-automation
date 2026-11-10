@contact
Feature: Contact Us form without file upload
  As a visitor
  I want to send a message through the Contact Us form
  So that I can get in touch without needing to attach a file

  Background:
    Given I am on the home page

  @smoke @contact
  # JIRA: SCRUM-372 (hash: e1e051d8) owner: SCRUM-371
  Scenario: Contact Us form has no upload field and submits without an attachment
    When I open the Contact Us page from the navigation
    Then the file upload field should not be shown on the Contact Us form
    And the name, email, subject and message fields should be shown on the Contact Us form
    And the Submit button should be shown on the Contact Us form
    When I fill in the contact form with name "Demo Reviewer" email "demo.subscriber@example.com" subject "Product Enquiry" and message "I would like to know more about your Blue Top product."
    And I submit the contact form
    Then I should see the contact success message
    When I click the Home button on the Contact Us page
    Then I should be returned to the home page
