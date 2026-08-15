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
def manhattan(downtown):
    """The only BC with any innards — everything inside a building is checked on it."""
    return Space.objects.create(org=downtown, type="building", code="man", name="Manhattan")


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
    """A space under another space. The type is given: a contour carries more than `room`."""

    def _make_space(parent, code, name, type="room"):
        return Space.objects.create(
            org=parent.org,
            type=type,
            parent=parent,
            building=parent.building,
            code=code,
            name=name,
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
