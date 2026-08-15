"""The fields of a building passport must fit a real business centre.

Clearing the placeholders (`-1`, `1900`, an empty floor count) is a one-off migration
over five passports and is verified by inspecting the data. What is tested here is what
outlives that migration: the width of the area fields and the textual floor count.
"""

from decimal import Decimal

import pytest

from building_passport.models import BuildingPassport, Space

pytestmark = pytest.mark.django_db


@pytest.fixture
def building():
    return Space.objects.create(type="building", code="БЦ-1")


def test_a_business_centre_larger_than_10000_m2_saves(building):
    """`max_digits=6` cut the area off at 9,999.99 m² — a real BC does not fit into that."""
    passport = BuildingPassport.objects.create(
        space=building,
        total_area=Decimal("25480.75"),
        building_footprint=Decimal("12345.67"),
        non_residential_area=Decimal("25480.75"),
    )

    passport.refresh_from_db()

    assert passport.total_area == Decimal("25480.75")
    assert passport.building_footprint == Decimal("12345.67")
    assert passport.non_residential_area == Decimal("25480.75")


def test_number_of_floors_keeps_the_form_written_in_the_building_passport(building):
    """"4+тех.этаж" is what the Ф-2 form records; an integer cannot hold such a floor count."""
    passport = BuildingPassport.objects.create(space=building, number_of_floors="4+тех.этаж")

    passport.refresh_from_db()

    assert passport.number_of_floors == "4+тех.этаж"
