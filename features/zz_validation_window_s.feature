Feature: Throw-away validation check (validation window S, removed at its end)

  # JIRA: SCRUM-441 (hash: 000b5ab1) owner: SCRUM-440
  Scenario: Window S check that fails until the change is deployed
    Given I am on the home page
    Then the window S check waits for its deployment
