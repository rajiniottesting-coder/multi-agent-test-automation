Feature: Throw-away validation check on main (reverted in the next cycle)

  Scenario: A throw-away failure nothing traces
    Given I am on the home page
    Then the throw-away check on main fails
