# Agent 2 - what to do about each review comment

A person reviewed a pull request that Agent 2 opened for the story below. For
EACH numbered comment, decide one action. You do not write code here; a later
step changes the files you name, with the comment as its instruction.

## The rule that decides most comments

The approved test cases are the specification. The code in this pull request
implements them.

- **fix** - the comment is about HOW the code works: a selector, a wait, a
  page-object method, a step's wording or body, duplication, naming, a missing
  assertion that the test case already states, an error the comment points
  at. Name every editable file that must change.
- **decline** - the comment asks the tests to check something the approved
  test cases do not state (a new check, a different expected result, another
  scenario), or it can only be met by changing a file that is not editable.
  Changing what is verified without changing the test case would make the
  code disagree with what was approved. Say so in the reason, and say what
  the reviewer can do instead: update the test case in the tracker, then
  regenerate.
- **no_change** - a question, praise, or a remark that needs no code change.
  Answer it briefly in the reason.

A comment anchored to a file is about that file, but the fix may need another
editable file too (a step definition that calls a page-object method that must
change). Name only files from the editable list, exactly as written there.

## The story

{story_text}

## The approved test cases

{test_cases_text}

## Editable files in this pull request

{editable_files}

## Files in this pull request that are NOT editable here

{protected_files}

## The review comments

{comments}
