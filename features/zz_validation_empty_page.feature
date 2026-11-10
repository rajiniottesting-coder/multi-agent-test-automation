Feature: Throw-away validation check (never merged)

  Scenario: A throw-away scenario that acts before opening any page
    When I click the Test Cases link in the top menu straight away
    Then the throw-away Test Cases page is shown
