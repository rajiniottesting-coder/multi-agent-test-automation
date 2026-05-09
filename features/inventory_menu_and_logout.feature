Feature: Inventory Menu and Logout Functionality
  As a logged-in user on the SauceDemo inventory page
  I want to interact with the burger menu and log out
  So that I can manage my session and navigate the application

  Background:
    Given I am on the SauceDemo login page
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"

  @smoke @inventory_menu @logout
  Scenario: Verify burger menu and Logout option are present on inventory page
    Then the burger menu icon should be visible
    When I click the burger menu icon
    Then the navigation menu should be open
    And the "Logout" link should be visible in the navigation menu

  @smoke @logout
  Scenario: Verify successful logout from inventory page
    When I click the burger menu icon
    And I click the "Logout" link
    Then I should be redirected to the login page
    And the login form fields should be visible

  @negative @logout @session
  Scenario: Verify logout clears session and prevents direct access to inventory page
    When I click the burger menu icon
    And I click the "Logout" link
    Then I should be redirected to the login page
    When I attempt to navigate directly to the inventory page
    Then I should be redirected to the login page
    And I should see the error message "Epic sadface: Username is required"
