# Map a story's acceptance criteria to the test cases it already has

You are a meticulous QA test analyst. A user story already has its test cases,
written earlier - by an earlier version of this pipeline or by a person. Say
which of them verify each acceptance criterion. Do NOT write, change, merge or
invent test cases: you only map what exists.

## Application
{app_name} ({app_base_url})

## The story
{story_text}

## Its acceptance criteria
{criteria_block}

## Its test cases (key - title, then their steps as written)
{test_cases_block}

## Your answer
One `coverage` entry for EVERY criterion listed above, in order:

- `criterion`: its number exactly as listed (AC1, AC2, ...).
- `covered_by`: the KEY of each test case above whose steps verify the
  criterion - a step that does what the criterion describes and an expected
  result that checks its outcome. A test case that only visits the same page,
  or does the action without checking the outcome, does NOT verify it.
  Leave `covered_by` EMPTY when no test case verifies the criterion: an honest
  gap is the right answer, and a person will add a test case for it.
- `how_verified`: one line. When covered: the step that proves it, in the test
  case's own words. When empty: what is not checked by any test case.

A criterion marked as something REMOVED, RESTRICTED or LIMITED is verified only
by a step whose expected result states the absence, the refusal or the
rejection - cite a test case for it only if it has such a step.
