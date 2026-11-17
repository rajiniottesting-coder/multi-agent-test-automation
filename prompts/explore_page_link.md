# Which link opens the page this story needs

A user story was refused for automation: its test cases need a page the
application inventory does not have. The application links to several pages the
inventory does not list. Pick the ONE link that opens the page the story and its
test cases are about - or none.

## The story
{story_text}

## Its test cases
{test_cases}

## The page the generated code asked for
{wanted}

## Why the story was refused
{reasons}

## Links to pages the inventory does not list (path - link text - pages it is on)
{links}

## Your answer
- `path`: the path of the one listed link that opens the page the test cases act
  on, exactly as listed. Choose it only when the link's text or path names what
  the story names (the page's title, its subject, the menu entry a step clicks).
- Leave `path` EMPTY when no listed link clearly opens that page, or when several
  could and nothing in the story tells them apart. An empty answer is correct
  and costs nothing; a wrong page is proposed to a person for review.
- `why`: one sentence - the words the link and the story share, or why none fits.
