Feature: Throw-away validation check on main (reverted in the next cycle)

  # JIRA: SCRUM-345 (hash: 00000000) owner: SCRUM-344
  Scenario: A throw-away failure nothing traces
    Given I am on the home page
    Then the throw-away check on main fails
