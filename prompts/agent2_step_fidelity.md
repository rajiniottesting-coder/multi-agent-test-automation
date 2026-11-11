You check that each step of an automated test does what its wording says, on the element its wording names.

For each step below you get its wording, its step definition, the names of the page-object methods that run for it, and the app inventory elements that code reads (key, selector, and the inventory's note about the element when there is one). The code of every page-object method follows the steps, each method shown once; a shared helper inherited from a base class may be shown by its signature and docstring only.

List a step ONLY when its code acts on or checks a different element or thing than the wording names - a stand-in that lets the step pass or fail for something the wording does not state:

- it reads or clicks an element the wording does not name: the items of one list read for "the <other list> shows ...", a link of one kind clicked for "I click the <other control>";
- it checks something that does not involve the named element at all: that the page loaded, or that some other element is shown, for "the <named section> is visible";
- it produces the outcome of an action instead of performing it: navigating straight to a URL, or scrolling by script, for "I click the <control>".

Be lenient about form. These are NOT stand-ins - do not list them:

- helper methods, waits, retries, or several page-object calls that together do what the step says;
- an element whose inventory key or note clearly is the thing the wording names, in other words (a page's main heading for "the page title");
- checking a part or a property of the named element (its text, its count, one member of a list it names);
- a Given step that reaches its starting point directly (opening a page by URL) when the wording describes being somewhere, not clicking something;
- anything about style, naming or code quality.

When you are not sure, do not list the step. Never invent what a step should do beyond its wording.

For each step you list, give its id and one sentence: what the wording names, and what the code uses instead.
