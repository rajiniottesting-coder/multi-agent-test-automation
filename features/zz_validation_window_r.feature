Feature: Throw-away validation checks (validation window R, removed at its end)

  # JIRA: SCRUM-437 (hash: 2dd43c60) owner: SCRUM-436
  Scenario: Window R check that finds an application bug
    Given I am on the home page
    Then the window R check finds the application bug

  # JIRA: SCRUM-438 (hash: 829c93f2) owner: SCRUM-436
  Scenario: Window R check that passes
    Given I am on the home page
    Then the window R check passes
