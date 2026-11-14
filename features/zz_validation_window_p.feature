Feature: Throw-away validation check on main (validation window P, removed at its end)

  # JIRA: SCRUM-420 (hash: 0d0a0e01) owner: SCRUM-330
  Scenario: A throw-away failure the triage raises a defect for
    Given I am on the home page
    Then the throw-away window P check passes once it is switched on
