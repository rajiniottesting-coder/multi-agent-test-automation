Feature: Throw-away validation check on main (validation window J, removed at its end)

  Scenario: A throw-away failure the tracker is asked to record
    Given I am on the home page
    Then the throw-away window J check fails
