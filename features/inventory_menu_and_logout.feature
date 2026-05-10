Feature: Inventory Menu and Logout
  As a logged-in user on the inventory page
  I want to interact with the burger menu and log out
  So that I can manage my session and navigate the application

  Background:
    Given I am on the SauceDemo login page
    When I log in with username "standard_user" and password "secret_sauce"
    And I should be redirected to the inventory page
    And I should see the page title "Products"

  @smoke @inventory_menu
  Scenario: Verify burger menu and Logout option are present on inventory page
    Then I should see the burger menu icon
    When I open the burger menu
    Then I should see the 'Logout' link in the burger menu

  @smoke @logout
  Scenario: Verify successful logout from inventory page
    When I open the burger menu
    And I click the 'Logout' link
    Then I should be redirected to the login page
    And I should see the username and password input fields

  @negative @logout
  Scenario: Verify logout clears session and prevents direct access to inventory page
    When I open the burger menu
    And I click the 'Logout' link
    And I attempt to navigate directly to the inventory page
    Then I should be redirected to the login page
    And I should see the error message "Epic sadface: Username is required"
