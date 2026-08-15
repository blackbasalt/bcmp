"""The space card in the right-hand rail of the floor screen — what is visible over HTTP.

The seam is the same as for the other screens: the HTTP boundary. The rail arrives at an
address of its own and is read as a response — which facts about the space it carries,
where the links up and down the tree lead, and what comes back for another client's
space.

The two-way highlighting of the tree and the plan lives on the browser side and cannot
be observed over HTTP. What is checked is what feeds it and what is useless without it:
every tree node and every contour has a card address, and a space with no contour is
marked — that is the screen's contract, not its styling.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from building_passport.models import Space
from dictionary.models import DictSpaceSubtype

pytestmark = pytest.mark.django_db


def card_url(space):
    return reverse("building_passport:space_card", args=[space.pk])


def open_card(client, space):
    response = client.get(card_url(space))
    return response, response.content.decode()


@pytest.fixture
def entrance(first_floor):
    """"каб101вход" with everything the card shows: subtype and area."""
    space = Space.objects.get(code="man-f1-a")
    space.subtype = DictSpaceSubtype.objects.create(
        type="room", name="Офис", short_name="Офис"
    )
    space.area_m2 = Decimal("6.55")
    space.save()
    return space


@pytest.fixture
def card(client, member, entrance):
    client.force_login(member)
    _, page = open_card(client, entrance)
    return page


# Facts about the space


def test_the_card_shows_what_bcmp_holds_about_the_space(card):
    """The card answers "what kind of space is this" without opening the admin."""
    assert "man-f1-a" in card  # the code
    assert "каб101вход" in card  # the name
    assert "Офис" in card  # the subtype
    assert "Помещение" in card  # the type of the space
    assert "6,55\u00a0м²" in card  # the area, with non-breaking spaces


def test_a_space_without_an_area_says_so_rather_than_leaving_a_blank(
    client, member, first_floor
):
    """Blank space reads as a zero and a dash does not: the same notation as in the passport."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-b"))

    assert "— нет данных" in page


# Its place in the tree


def test_the_card_leads_to_the_space_this_one_is_part_of(client, member, first_floor):
    """The hierarchy is walked without leaving the floor: the link up re-fills the rail."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a1"))

    assert "каб101вход" in page
    assert card_url(Space.objects.get(code="man-f1-a")) in page


def test_the_card_leads_to_the_spaces_inside_this_one(client, member, first_floor):
    """The link downwards is the rail too: descending the tree does not lead away from the plan."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a"))

    # The address is compared, not the name: "каб101" is contained in "каб101вход", and
    # a check by text would pass on the card's own heading.
    assert card_url(Space.objects.get(code="man-f1-a1")) in page


def test_a_space_directly_under_the_floor_names_the_floor_it_lies_on(
    client, member, first_floor
):
    """The floor is named but opens no card: it is not a tree node but the screen itself."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a"))

    assert "1 Этаж" in page
    assert card_url(first_floor) not in page


def test_the_card_names_no_space_of_another_organisation_below(
    client, member, central, first_floor
):
    """The links downwards are selected through the same checkpoint as the tree and the contours.

    There is no such row in healthy data; what is checked is that the rail is assembled
    through the checkpoint rather than by a query on `parent`.
    """
    Space.objects.create(
        org=central, type="room", parent=Space.objects.get(code="man-f1-a"),
        building=first_floor.building, code="ctr-x", name="Чужое помещение",
    )
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a"))

    assert "Чужое помещение" not in page


def test_the_card_names_no_space_of_another_organisation_above(
    client, member, downtown, central, first_floor
):
    """Up the tree it is the same checkpoint: a foreign name does not slip through "Выше".

    Walking `parent` directly would be a second place deciding whose data to show — and
    abolishing that second place is what ADR 0001 was written for.
    """
    theirs = Space.objects.create(
        org=central, type="room", parent=first_floor,
        building=first_floor.building, code="ctr-x", name="Чужое помещение",
    )
    ours = Space.objects.create(
        org=downtown, type="room", parent=theirs,
        building=first_floor.building, code="man-f1-c", name="Наше помещение",
    )
    client.force_login(member)

    _, page = open_card(client, ours)

    assert "Чужое помещение" not in page


# What the rail does not carry


def test_the_card_promises_no_documents_and_no_systems(card):
    """A section promising data of which there is not a single row is worse than no section."""
    assert "Документы" not in card
    assert "Системы" not in card


def test_the_card_carries_no_way_to_change_anything(card):
    """The rail is read-only, like the tree: writing stays in the Django admin."""
    assert "Редактировать" not in card
    assert "Удалить" not in card
    assert "Добавить" not in card


# Access


def test_a_space_of_another_organisation_is_missing_rather_than_forbidden(
    client, member, central, make_floor, make_space
):
    """The rail is as much a read path as a screen: a 403 would confirm the space exists."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    room = make_space(make_floor(theirs, 1), "ctr-f1-a", "Чужое помещение")
    client.force_login(member)

    response, _ = open_card(client, room)

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_login(client, first_floor):
    """Before signing in, nothing about clients' spaces is visible, the card included."""
    response, _ = open_card(client, Space.objects.get(code="man-f1-a"))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_a_superuser_reaches_the_card_of_any_organisation(
    client, django_user_model, central, make_floor, make_space
):
    """A developer reproduces a client's problem without granting themselves a membership."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    room = make_space(make_floor(theirs, 1), "ctr-f1-a", "Кабинет")
    client.force_login(django_user_model.objects.create_superuser("developer"))

    response, _ = open_card(client, room)

    assert response.status_code == 200
