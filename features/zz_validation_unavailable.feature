Feature: Throw-away validation check (never merged)

  Scenario: A throw-away check of the Test Cases page heading
    Given I open the Test Cases page for the throw-away check
    Then the Test Cases page heading reads "Contact Us Form"
