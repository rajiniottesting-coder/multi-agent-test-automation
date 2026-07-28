# PIM module

`PIM > Employee List` — the employee directory.

URL: `/web/index.php/pim/viewEmployeeList`

## Search filters

| Filter | Type |
|---|---|
| Employee Name | autocomplete |
| Employee Id | text |
| Employment Status | dropdown |
| Include | dropdown (Current Employees Only / Current and Past / Past Only) |
| Supervisor Name | autocomplete |
| Job Title | dropdown |
| Sub Unit | dropdown |

All active filters combine with AND. **Search** applies them; **Reset** clears
them and restores the full list.

Results show as "(N) Records Found" above a table with columns: Id, First (&
Middle) Name, Last Name, Job Title, Employment Status, Sub Unit, Supervisor.

## Behaviour worth testing

| Action | Result |
|---|---|
| Search with a valid Employee Id | Table shows only matching rows |
| Search with an unmatched value | "No Records Found" |
| Combine two filters | Rows satisfy BOTH |
| Reset | Filters cleared, full list returned |
| Add | Navigates to the Add Employee form |

## Points that matter when writing test cases

- **This is a SHARED demo.** Employees are added and deleted by other people
  while your tests run. Assert that results are FILTERED — that every visible
  row matches the criterion — never on an exact count, and never that a
  specific employee exists.
- **Employee Name and Supervisor Name are autocompletes.** A value must be
  selected from the suggestions; typed-but-unselected text is rejected with
  "Invalid".
- **Every *Status / Title / Sub Unit filter is a custom dropdown**, not a native
  select. The interaction is click-to-open, then click an option.
- **Employee Id is a safer filter than Employee Name** for a shared demo,
  because it is exact rather than fuzzy — prefer it when a test case needs a
  deterministic search.

## Grouping guidance

Searching by different single filters is ONE test case exercised with several
inputs — the behaviour is "a filter narrows the results".

Combining filters is a SEPARATE behaviour (AND logic) and earns its own case.
Reset is a third.