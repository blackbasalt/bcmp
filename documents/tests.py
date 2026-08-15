"""The addresses of the "Документы" section: its own namespace under `/documents/`.

A separate namespace is needed not for tidiness in the code but for the menu: an item is
highlighted by the section the reader is standing in, and the only way to tell two sections
apart is that their names differ.
"""

from django.urls import reverse


def test_the_section_reverses_under_its_own_namespace():
    """The address name and the project's include agree — otherwise the template crashes on
    `url`."""
    assert reverse("documents:document_list") == "/documents/"
