"""The floor screen and the way to it from the BC card — what an employee sees over HTTP.

The seam is the same as for the list and the card: the HTTP boundary. The tests open a
floor with the test client on behalf of a user with a known membership and check what is
observable — which spaces are on the screen, what is nested in what and which status
code comes back. Classes and layout are not checked; the footholds in the markup are the
`data-space` attribute on a tree node and `data-select` on whatever selects a space.
Both are part of the screen's contract rather than of its styling: the first shows the
nesting, the second is how the tree and the plan find each other.
"""

import re
from html.parser import HTMLParser

import pytest
from django.urls import reverse

from building_passport.models import Space

pytestmark = pytest.mark.django_db

# Tags that need no closing: without them the parse stack slips at the very first `<meta>`.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}


class SpaceNesting(HTMLParser):
    """Who is inside whom in the tree: for every node, the codes of the nodes above it.

    Nesting is the one property of the tree that is invisible in the text of the page: a
    flat list and a tree print the very same names. That is why the parse goes by
    `data-space` rather than by the markup around it.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open_spaces: list[str | None] = []
        self.ancestors: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            return
        code = dict(attrs).get("data-space")
        if code is not None:
            self.ancestors[code] = [c for c in self.open_spaces if c is not None]
        self.open_spaces.append(code)

    def handle_endtag(self, tag):
        if tag not in VOID_TAGS and self.open_spaces:
            self.open_spaces.pop()


def nesting(page):
    parser = SpaceNesting()
    parser.feed(page)
    return parser.ancestors


class Selecting(HTMLParser):
    """What selects a space on the screen: space code → the attributes of that element.

    On a floor with no plan the only way to select is from the tree, so each code occurs
    once.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "data-select" in attributes:
            self.found[attributes["data-select"]] = attributes


def selecting(page):
    parser = Selecting()
    parser.feed(page)
    return parser.found


def rail_content(page):
    """What lies in the right-hand rail: `#space-card` is the target the card is put into.

    Also a contract of the screen: this is the address in the markup the card arrives at.
    """
    return re.search(r'id="space-card"[^>]*>(.*?)</div>', page, re.DOTALL).group(1).strip()


def floor_url(floor):
    return reverse("building_passport:floor", args=[floor.building_id, floor.pk])


def card_url(space):
    return reverse("building_passport:space_card", args=[space.pk])


def open_floor(client, floor):
    response = client.get(floor_url(floor))
    return response, response.content.decode()


@pytest.fixture
def floor_page(client, member, first_floor):
    client.force_login(member)
    _, page = open_floor(client, first_floor)
    return page


# The floor screen


def test_a_member_opens_a_floor_of_their_own_building(client, member, first_floor):
    """The screen opens and renders: a template error is caught here."""
    client.force_login(member)

    response, _ = open_floor(client, first_floor)

    assert response.status_code == 200


def test_a_floor_of_another_organisation_is_missing_rather_than_forbidden(
    client, member, central, make_floor
):
    """A 403 would confirm that another client has such a building and such a floor."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    client.force_login(member)

    response, _ = open_floor(client, make_floor(theirs, 1))

    assert response.status_code == 404


def test_a_floor_is_not_reachable_through_another_building(
    client, member, downtown, manhattan, make_floor
):
    """The address names both building and floor; a mismatch is an absence, not a screen."""
    boston = Space.objects.create(org=downtown, type="building", code="bos", name="Boston")
    floor = make_floor(boston, 7)
    client.force_login(member)

    response = client.get(reverse("building_passport:floor", args=[manhattan.pk, floor.pk]))

    assert response.status_code == 404


def test_a_space_that_is_not_a_floor_has_no_floor_screen(client, member, first_floor):
    """A space is not a floor: there is no floor tree to show at its address."""
    room = Space.objects.get(code="man-f1-a")
    client.force_login(member)

    response = client.get(
        reverse("building_passport:floor", args=[first_floor.building_id, room.pk])
    )

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_login(client, first_floor):
    """Before signing in, nothing about clients' buildings is visible, their floors included."""
    response = client.get(floor_url(first_floor))

    assert response.status_code == 302
    assert reverse("login") in response.url


# The tree of spaces


def test_the_tree_shows_every_space_under_the_floor_down_to_the_leaves(floor_page):
    """The tree is the only way to reach spaces that have no contour.

    Nodes are compared, not names: "каб101" is contained in "каб101вход", and a check by
    text would pass even if the leaf never reached the screen.
    """
    assert set(nesting(floor_page)) == {"man-f1-a", "man-f1-a1", "man-f1-b"}
    assert "каб101вход" in floor_page
    assert "ИТП" in floor_page


def test_a_nested_space_is_shown_nested_rather_than_flat(floor_page):
    """A flat list loses exactly what a tree exists for."""
    assert "man-f1-a" in nesting(floor_page)["man-f1-a1"]


def test_a_space_of_another_floor_is_not_in_this_floor_tree(
    client, member, first_floor, make_floor, make_space
):
    """A floor's tree starts at the floor: a neighbouring floor is not mixed into it."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert "каб201" not in page


def test_the_tree_holds_no_space_of_another_organisation(client, member, central, first_floor):
    """Another client's row under the same floor must not reach the screen.

    There is no such row in healthy data; what is checked is that the tree is assembled
    through the checkpoint rather than going around it with a query of its own.
    """
    Space.objects.create(
        org=central, type="room", parent=first_floor, building=first_floor.building,
        code="ctr-x", name="Чужое помещение",
    )
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert "Чужое помещение" not in page


# The tree as a way to select a space


def test_every_space_in_the_tree_opens_its_card(floor_page):
    """The tree is the only path to spaces without a contour: there is nowhere to click them.

    Card addresses are compared, not the presence of a node: a node that opens nothing
    would leave such spaces exactly where they were — out of reach.
    """
    opens = {code: tag["hx-get"] for code, tag in selecting(floor_page).items()}

    assert opens == {
        space.code: card_url(space)
        for space in Space.objects.filter(code__in=["man-f1-a", "man-f1-a1", "man-f1-b"])
    }


# The layout of the screen and its empty states


def test_the_screen_opens_with_nothing_in_the_rail(floor_page):
    """Until a space is selected there is nothing in the rail, and the plan holds the width.

    Whether the rail is open or closed is a property of the browser side; what is
    observable over HTTP is that nobody asked for a card: the target it is put into is
    empty.
    """
    assert rail_content(floor_page) == ""


def test_a_floor_without_a_plan_says_there_is_no_plan_in_force(floor_page):
    """The absence of a plan reads as a state of the data, not as a broken screen."""
    assert "нет действующего поэтажного плана" in floor_page


# Moving on from the floor screen


def test_the_switcher_reaches_the_other_floors_of_the_building(
    client, member, first_floor, make_floor
):
    """One moves between floors from a floor itself, not by going back to the BC card."""
    second = make_floor(first_floor.building, 2)
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert floor_url(second) in page
    assert "2 Этаж" in page


def test_the_switcher_does_not_reach_a_floor_of_another_building(
    client, member, downtown, first_floor, make_floor
):
    """The switcher holds this building's floors; other buildings' floors are not in it."""
    boston = Space.objects.create(org=downtown, type="building", code="bos", name="Boston")
    make_floor(boston, 7)
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert "7 Этаж" not in page


def test_every_floor_leads_back_to_the_card_of_its_building(floor_page, manhattan):
    """From any floor one returns to the passport, not through the browser's back button."""
    assert reverse("building_passport:bc_detail", args=[manhattan.pk]) in floor_page


def test_the_screen_carries_no_way_to_change_anything(floor_page):
    """The tree of spaces is read-only: writing stays in the Django admin."""
    assert "Редактировать" not in floor_page
    assert "Удалить" not in floor_page
    assert "Добавить" not in floor_page


def test_the_page_carries_no_leftover_template_comments(floor_page):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on the screen."""
    assert "{#" not in floor_page
