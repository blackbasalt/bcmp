"""The organisations and the building the tests are staged on.

There is one building for the whole suite: the floor and its spaces are needed both by the
floor screen and by the plan, and there must not be two definitions of one and the same
Manhattan. Where a test needs several of something — floors, spaces — the fixture hands
out a factory rather than a ready-made object.
"""

import pytest

from building_passport.models import Space
from parties.models import Org, OrgMembership, Party


@pytest.fixture
def make_org(db):
    def _make_org(name, bin_iin):
        party = Party.objects.create(kind=Party.Kind.COMPANY, name=name, bin_iin=bin_iin)
        return Org.objects.create(party=party)

    return _make_org


@pytest.fixture
def downtown(make_org):
    """The organisation of the five existing BCs."""
    return make_org("DownTown Management ТОО", "180540035878")


@pytest.fixture
def central(make_org):
    """The second client — its data must not reach the first one."""
    return make_org("Central City Properties ТОО", "201140031473")


@pytest.fixture
def member(django_user_model, downtown):
    """A management-company employee with a membership in one organisation — the ordinary
    reader of the screens."""
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


@pytest.fixture
def both_clients(django_user_model, downtown, central):
    """An employee handling two clients at once — the reader the «Организация» column exists
    for.

    It lives here rather than beside either полка: both the полка документов and the полка
    помещений label their rows on the same condition, and a second definition of the same
    manager would let the two screens be checked against different readers.
    """
    user = django_user_model.objects.create_user("manager")
    OrgMembership.objects.create(user=user, org=downtown)
    OrgMembership.objects.create(user=user, org=central)
    return user


@pytest.fixture
def administrator(django_user_model, downtown):
    """An organisation administrator: the same employee, with the right to maintain data.

    It lives here rather than beside the plan upload for the same reason `manhattan` does:
    the write right is asked about on more than one screen — the floor and the documents
    section — and a second definition of the same employee would drift from the first.
    """
    user = django_user_model.objects.create_user("director")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    return user


@pytest.fixture
def admin_client(client, django_user_model):
    """A platform administrator, signed in to the Django admin.

    It lives here for the same reason `administrator` does: what is entered in the admin
    until a screen carries the form is entered on more than one model — плана, аренда —
    and a second definition of the same superuser would drift from the first.
    """
    client.force_login(django_user_model.objects.create_superuser("developer"))
    return client


@pytest.fixture
def make_building(db):
    """A BC of an organisation. The second client's buildings are made here too: isolation
    is checked with a building of theirs on more than one screen, and it is the same
    building each time."""

    def _make_building(org, code, name=None):
        return Space.objects.create(org=org, type="building", code=code, name=name or code)

    return _make_building


@pytest.fixture
def manhattan(downtown, make_building):
    """The only BC with any innards — everything inside a building is checked on it."""
    return make_building(downtown, "man", "Manhattan")


@pytest.fixture
def make_floor(db):
    def _make_floor(building, number):
        return Space.objects.create(
            org=building.org,
            type="floor",
            parent=building,
            building=building,
            code=f"{building.code}-f{number}",
            name=f"{number} Этаж",
            floor_number=number,
        )

    return _make_floor


@pytest.fixture
def make_space(db):
    """A space under another space. The type is given: a contour carries more than `room`.

    Everything else about a помещение — the площадь, the two flags вид is read off, the
    назначение — is passed through as it is written on the model. The полка помещений puts
    a condition on each of them, and a fixture that took them one by one would grow a
    keyword per condition; what does not need staging keeps the model's own default, which
    is what a помещение loaded from a паспорт looks like anyway.

    The floor a помещение lies on is inherited unless it is given: a вложенное помещение is
    on its parent's floor, so no test should have to repeat the number — but the полка has a
    condition on that number, and a test about a помещение whose номер этажа matches no этаж
    has to be able to stage one.
    """

    def _make_space(parent, code, name, type="room", **fields):
        # Inherited rather than fixed: a space staged on a floor it does not lie on is a
        # building that cannot exist, but a test that means to stage exactly that — a
        # помещение whose номер этажа matches no этаж — must still be able to say so.
        fields.setdefault("floor_number", parent.floor_number)
        return Space.objects.create(
            org=parent.org,
            type=type,
            parent=parent,
            building=parent.building,
            code=code,
            name=name,
            **fields,
        )

    return _make_space


@pytest.fixture
def first_floor(manhattan, make_floor, make_space):
    """Manhattan's first floor with nesting: «каб101» sits under «каб101вход»."""
    floor = make_floor(manhattan, 1)
    entrance = make_space(floor, "man-f1-a", "каб101вход")
    make_space(entrance, "man-f1-a1", "каб101")
    make_space(floor, "man-f1-b", "ИТП")
    return floor
