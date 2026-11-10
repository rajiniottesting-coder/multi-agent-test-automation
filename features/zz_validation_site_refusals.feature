Feature: Throw-away validation checks of site refusals (never merged)

  Scenario: A page load the site refuses once is retried and loads
    Given the throw-away site refuses the next page load once
    Then the throw-away Test Cases page loads

  Scenario: A check the site refuses on its first attempt passes when re-run
    Given the throw-away site refuses every page load on the first attempt only
    Then the throw-away Test Cases page loads
