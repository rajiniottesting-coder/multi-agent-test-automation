@home
Feature: Automation Exercise newsletter subscription
  As a visitor
  I want to subscribe to the newsletter from the home page
  So that I receive updates without needing an account

  Background:
    Given I am on the home page

  @smoke @home
  # JIRA: SCRUM-223 (hash: 8e04a248) owner: SCRUM-202
  Scenario: Visitor subscribes to the newsletter with a valid email address
    When I subscribe to the newsletter with email "demo.subscriber@example.com"
    Then I should see the subscription success message "You have been successfully subscribed!"
    And I should remain on the home page
