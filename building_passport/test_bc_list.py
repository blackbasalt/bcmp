"""The list of BCs — what an employee of the management company sees over HTTP.

There is one seam: the HTTP boundary. The tests walk named addresses with the test
client on behalf of a user with a known membership and check what is observable — which
business centres are on the screen and which status code comes back. Markup, classes and
headings are not checked, so that a rebuild below the level of the URL does not rewrite
the test set.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from building_passport.models import BuildingPassport, Space
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db


def make_building(org, name):
    return Space.objects.create(org=org, type="building", code=name.lower(), name=name)


@pytest.fixture
def member(django_user_model, downtown):
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


def bc_list(client):
    response = client.get(reverse("building_passport:bc_list"))
    return response, response.content.decode()


def test_a_member_sees_their_own_portfolio_and_not_another_clients(client, member, downtown, central):
    """Client isolation on the screen is exactly what the checkpoint was introduced for."""
    make_building(downtown, "Manhattan")
    make_building(central, "Central Tower")
    client.force_login(member)

    response, page = bc_list(client)

    assert response.status_code == 200
    assert "Manhattan" in page
    assert "Central Tower" not in page


def test_a_superuser_sees_every_organisation(client, django_user_model, downtown, central):
    """A developer reproduces a client's problem without granting themselves a membership."""
    portfolio = ["Manhattan", "Boston", "Dubai", "Geneva", "Tokyo"]
    for name in portfolio:
        make_building(downtown, name)
    make_building(central, "Central Tower")
    client.force_login(django_user_model.objects.create_superuser("developer"))

    response, page = bc_list(client)

    assert response.status_code == 200
    assert [name for name in portfolio + ["Central Tower"] if name not in page] == []


def test_a_user_without_membership_gets_an_empty_list_and_an_explanation(
    client, django_user_model, downtown
):
    """A newcomer needs neither a 403 nor others' data, but to be told whom to ask."""
    make_building(downtown, "Manhattan")
    client.force_login(django_user_model.objects.create_user("newcomer"))

    response, page = bc_list(client)

    assert response.status_code == 200
    assert "Manhattan" not in page
    assert "администратор" in page


def test_the_list_holds_business_centres_only(client, member, downtown):
    """Navigation is flat: a site does not appear in the list."""
    make_building(downtown, "Manhattan")
    Space.objects.create(org=downtown, type="site", code="s1", name="Площадка Zurich")
    client.force_login(member)

    _, page = bc_list(client)

    assert "Manhattan" in page
    assert "Площадка Zurich" not in page


def test_a_card_shows_what_tells_the_buildings_apart(client, member, downtown):
    """Name, address, class, year built and total area — right on the card."""
    building = make_building(downtown, "Manhattan")
    BuildingPassport.objects.create(
        space=building,
        address="пр. Ракымжан Кошкарбаев, зд 1/2",
        building_class="B+",
        year_built=2017,
        total_area=Decimal("2484.10"),
    )
    client.force_login(member)

    _, page = bc_list(client)

    assert "Manhattan" in page
    assert "пр. Ракымжан Кошкарбаев, зд 1/2" in page
    assert "B+" in page
    assert "2017" in page
    assert "2\u00a0484,10\u00a0м²" in page  # as in the passport, with non-breaking spaces


def test_a_missing_passport_value_reads_as_no_data_rather_than_as_a_blank(
    client, member, downtown
):
    """Blank space on a card can be read as a zero; "— нет данных" cannot."""
    building = make_building(downtown, "Tokyo")
    BuildingPassport.objects.create(
        space=building, address="пр. Ракымжан Кошкарбаев, зд 1а", building_class="A"
    )
    client.force_login(member)

    _, page = bc_list(client)

    assert page.count("— нет данных") == 2  # the year built and the total area


def test_a_building_whose_spaces_are_not_loaded_carries_a_badge(client, member, downtown):
    """Four BCs out of five have no spaces yet — a normal state, not an error."""
    loaded = make_building(downtown, "Manhattan")
    Space.objects.create(
        org=downtown, type="floor", code="man-1", name="Этаж 1", parent=loaded, building=loaded
    )
    make_building(downtown, "Tokyo")
    client.force_login(member)

    _, page = bc_list(client)

    assert page.count("Помещения не загружены") == 1


def test_a_card_opens_the_passport_of_its_building(client, member, downtown):
    """Opening a BC is a click on its card, not a hunt through a menu."""
    building = make_building(downtown, "Manhattan")
    client.force_login(member)

    _, page = bc_list(client)
    opened = client.get(reverse("building_passport:bc_detail", args=[building.pk]))

    assert reverse("building_passport:bc_detail", args=[building.pk]) in page
    assert opened.status_code == 200


def test_the_project_is_a_label_and_the_site_does_not_appear(client, member, downtown):
    """Navigation is flat: the project is a label, and the site is not shown at all."""
    project = Space.objects.create(org=downtown, type="project", code="dt", name="Downtown")
    site = Space.objects.create(
        org=downtown, type="site", code="s1", name="Площадка Manhattan", parent=project
    )
    Space.objects.create(
        org=downtown, type="building", code="man", name="Manhattan", parent=site
    )
    client.force_login(member)

    _, page = bc_list(client)

    assert "Downtown" in page
    assert "Площадка Manhattan" not in page


def test_the_page_carries_no_leftover_template_comments(client, member, downtown):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on the screen."""
    make_building(downtown, "Manhattan")
    client.force_login(member)

    _, page = bc_list(client)

    assert "{#" not in page


def test_another_clients_row_does_not_clear_the_badge(client, member, downtown, central):
    """Only what the user can see themselves clears the badge (ADR 0001)."""
    building = make_building(downtown, "Manhattan")
    Space.objects.create(
        org=central, type="room", code="x-1", name="Чужое помещение", parent=building
    )
    client.force_login(member)

    _, page = bc_list(client)

    assert page.count("Помещения не загружены") == 1
