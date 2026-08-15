"""The shell menu — the shared contract of every screen, not the property of one section.

It sits at the root, next to the shell it checks: the highlighting of an item is a
condition where one section answers for another, and checking it from the tests of one of
the sections would mean the other section learns about its own highlighting from someone
else's suite.

The seam is the same as everywhere — the HTTP boundary: a screen is opened, and the menu
items are read out of its markup. The footholds are `data-section` on an item and
`aria-current` on the open one: the colour of the highlight is not checked by the tests,
and it is the thing that changes most often.
"""

import re

import pytest
from django.urls import reverse

from parties.models import OrgMembership

pytestmark = pytest.mark.django_db

#: A menu item as a whole — together with the attributes by which it names itself.
ITEM = re.compile(r'<a[^>]*data-section="(?P<section>[^"]+)"[^>]*>')


@pytest.fixture
def member(django_user_model, downtown):
    """A management-company employee: the menu is the same for everyone signed in — it asks
    about no permissions."""
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


def sidebar(client, url):
    """The menu items on an open screen: section → the item itself, as markup."""
    page = client.get(url).content.decode()
    return {item["section"]: item.group() for item in ITEM.finditer(page)}


def test_both_sections_are_offered_without_going_through_a_building(client, member):
    """Documents is the first screen in the project reached without opening a building."""
    client.force_login(member)

    items = sidebar(client, reverse("building_passport:bc_list"))

    assert reverse("building_passport:bc_list") in items["building_passport"]
    assert reverse("documents:document_list") in items["documents"]


def test_the_documents_item_is_highlighted_inside_the_section(client, member):
    """The item is highlighted on every screen of its section, not only on the first one."""
    client.force_login(member)

    items = sidebar(client, reverse("documents:document_list"))

    assert 'aria-current="page"' in items["documents"]
    assert "aria-current" not in items["building_passport"]


def test_the_buildings_item_stays_highlighted_inside_a_building(client, member, manhattan):
    """The second section must not break the first: inside a building, buildings are highlighted."""
    client.force_login(member)

    items = sidebar(client, reverse("building_passport:bc_detail", args=[manhattan.pk]))

    assert 'aria-current="page"' in items["building_passport"]
    assert "aria-current" not in items["documents"]


def test_the_buildings_item_stays_highlighted_inside_a_floor(client, member, first_floor):
    """The floor screen is the same section: the highlight holds on to the section, not the screen."""
    client.force_login(member)

    items = sidebar(
        client,
        reverse("building_passport:floor", args=[first_floor.building_id, first_floor.pk]),
    )

    assert 'aria-current="page"' in items["building_passport"]
