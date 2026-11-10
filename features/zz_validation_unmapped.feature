Feature: Throw-away validation check on main (reverted in the next cycle)

  # JIRA: SCRUM-345 (hash: 00000000) owner: SCRUM-344
  Scenario: A throw-away failure nothing traces
    Given I am on the home page
    Then the throw-away check on main fails

  # JIRA: SCRUM-345 (hash: 00000000) owner: SCRUM-344
  Scenario: A second throw-away failure on main
    Given I am on the home page
    Then the second throw-away check on main fails

  # JIRA: SCRUM-345 (hash: 00000000) owner: SCRUM-344
  Scenario: A throw-away check on main that passes only on the retry
    Given I am on the home page
    Then the throw-away check on main passes only on its second attempt
