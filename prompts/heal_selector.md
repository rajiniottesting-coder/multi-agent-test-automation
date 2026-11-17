# Is one of these live elements the element whose selector stopped matching?

An automated test failed because an inventory selector now matches nothing on
the live page. The page itself loaded; the elements below are on it now, and no
inventory selector matches them. Say which of them, if any, is the SAME element
the inventory key stands for - its selector changed, the element did not.

## The inventory key
- page: `{page}` ({url})
- key: `{key}`
- selector that stopped matching: `{old_selector}`
- note in the inventory: {note}

## What the failing test does with it
{steps}

## Elements on the live page that no inventory selector matches (name: selector)
{candidates}

## Your answer
- `element`: the listed name of the one element that is the same element as the
  key - the same kind of control or text, with the purpose the key's name, note
  and the test's steps describe. Exactly as listed.
- Leave `element` EMPTY when none clearly is, or when two could be. A different
  element with a similar look is NOT the same element: an empty answer raises
  the failure to a person as a defect, which is right when the element is gone.
- `why`: one sentence - what the listed element shares with the key, or why none
  matches.
