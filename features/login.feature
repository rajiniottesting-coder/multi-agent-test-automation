Feature: User Login
  As a registered user of SauceDemo
  I want to log in with my credentials
  So that I can access the products inventory page

  Background:
    Given I am on the SauceDemo login page

  @smoke @login
  Scenario: Successful login with standard user credentials
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"

  @login
  Scenario: Login fails with invalid password
    When I log in with username "standard_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"

  @login
  Scenario: Login fails for locked-out user
    When I log in with username "locked_out_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."