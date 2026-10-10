"""Element names from Latin-script text with accents (generality audit, G3).

Names used to be cut at every accented letter: 'Größe wählen' became
'gr_e_w_hlen'. They are now folded to ASCII first. Selectors are not affected:
only names are built from folded text.
"""
import pytest

from inventory_tools import introspect
from inventory_tools.introspect import _slug_to_name, fold_to_ascii


@pytest.mark.parametrize("text, name", [
    ("Größe wählen", "grosse_wahlen"),          # German, incl. ß
    ("Crème brûlée", "creme_brulee"),           # French
    ("Zażółć gęślą jaźń", "zazolc_gesla_jazn"),  # Polish, incl. ł
    ("Ærøskøbing", "aeroskobing"),              # Danish æ / ø
    ("Añadir al carrito", "anadir_al_carrito"),  # Spanish
])
def test_latin_text_keeps_its_words(text, name):
    assert _slug_to_name(text) == name


@pytest.mark.parametrize("text, name", [
    ("firstName", "first_name"),
    ("add-to-cart-backpack", "add_to_cart_backpack"),
    ("Sign in", "sign_in"),
])
def test_ascii_naming_is_unchanged(text, name):
    assert _slug_to_name(text) == name


def test_non_latin_scripts_behave_as_before():
    """No Latin form: dropped, so other naming sources take over (unchanged)."""
    assert _slug_to_name("Купить") == ""


def test_fold_is_safe_on_empty_and_none():
    assert fold_to_ascii("") == "" and fold_to_ascii(None) == ""


def test_the_selector_keeps_the_original_text():
    d = [{"tag": "a", "attrs": {"href": "/basket"}, "text": "Größe wählen",
          "renderedText": "Größe wählen", "label": "", "visible": True,
          "thirdParty": False, "hasIconChild": False, "cssPath": ""}]
    out = introspect.uncovered_elements("https://x.example/p", "T", d)
    assert list(out) == ["grosse_wahlen_link"]
    assert "basket" in out["grosse_wahlen_link"]
