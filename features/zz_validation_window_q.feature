Feature: Throw-away validation checks on main (validation window Q, removed at its end)

  # JIRA: SCRUM-427 (hash: c52bd1bc) owner: SCRUM-426
  Scenario: Window Q passing check one
    Given I am on the home page
    Then the window Q check passes

  # JIRA: SCRUM-428 (hash: 4d859b3e) owner: SCRUM-426
  Scenario: Window Q passing check two
    Given I am on the home page
    Then the window Q check passes

  @smoke
  # JIRA: SCRUM-429 (hash: 1e593083) owner: SCRUM-426
  Scenario: Window Q smoke check that fails
    Given I am on the home page
    Then the window Q smoke check passes once it is switched on

  # JIRA: SCRUM-430 (hash: b822af81) owner: SCRUM-426
  Scenario: Window Q check a person's Bug covers
    Given I am on the home page
    Then the window Q covered check passes once it is switched on

  # JIRA: SCRUM-431 (hash: abf128da) owner: SCRUM-426
  Scenario: Window Q re-test check
    Given I am on the home page
    Then the window Q check passes
