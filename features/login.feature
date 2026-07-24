Feature: User Login
  As a registered user of SauceDemo
  I want to log in with my credentials
  So that I can access the products inventory page

  Background:
    Given I am on the SauceDemo login page

  @smoke @login
  Scenario: Successful login with standard user credentials
    When I log in as "standard"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"

  @login
  Scenario: Login fails with invalid password
    When I log in as "standard" with an incorrect password
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"

  @login
  Scenario: Login fails for locked-out user
    When I log in as "locked_out"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."

  @login
  Scenario: A failed login can be cleared and retried
    When I log in as "standard" with an incorrect password
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    Then no error message should be displayed
    When I clear the credential fields
    And I log in as "standard"
    Then I should be redirected to the inventory page
