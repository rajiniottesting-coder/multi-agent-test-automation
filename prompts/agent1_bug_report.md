## This issue is a BUG REPORT, not a story

A person found this bug in the application. Draft the REGRESSION test case(s) that would catch it if it ever came back - not a test plan for the whole feature.

- **Follow the steps to reproduce** as the test case's steps, in the application's own words (pages, buttons, messages from the Application Under Test section).
- **Assert the EXPECTED result - what should happen.** Never assert the actual (wrong) result the reporter saw: the test must fail while the bug is present and pass once it is fixed.
- **One test case per expected result** that needs its own steps; usually one or two in total. A bug is not a reason to cover the rest of the feature.
- **The coverage map lists each expected result (EXP1, EXP2, ...)** with the test case that asserts it, exactly as for acceptance criteria.

Steps to reproduce, as reported:
{steps}

Expected result (what the test asserts):
{expected}

Actual result (what the bug does - never asserted):
{actual}
