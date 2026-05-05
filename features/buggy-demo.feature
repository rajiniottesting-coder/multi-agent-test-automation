Feature: Buggy Demo deliberately broken to test Agent 3

  Scenario: Login fails with empty credentials
    Given I am on the SauceDemo login page
    When I log in with username "" and password ""
    Then I should see an error