Feature: Throw-away validation checks (validation window T, removed at its end)

  # JIRA: SCRUM-444 (hash: 55a4fb9b) owner: SCRUM-442
  Scenario: Window T check that waits for its deployment
    Given I am on the home page
    Then the window T check waits for its deployment

  # JIRA: SCRUM-445 (hash: 55a4fb9b) owner: SCRUM-443
  Scenario: Window T check that starts failing
    Given I am on the home page
    Then the window T check that starts failing holds
