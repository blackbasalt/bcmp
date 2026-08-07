"""Поля паспорта здания должны вмещать реальный бизнес-центр.

Очистка заглушек (`-1`, `1900`, пустая этажность) — разовая миграция по пяти паспортам,
она проверяется осмотром данных. Здесь проверяется то, что переживёт миграцию: ширина
полей площадей и текстовая этажность.
"""

from decimal import Decimal

import pytest

from building_passport.models import BuildingPassport, Space

pytestmark = pytest.mark.django_db


@pytest.fixture
def building():
    return Space.objects.create(type="building", code="БЦ-1")


def test_a_business_centre_larger_than_10000_m2_saves(building):
    """`max_digits=6` обрезал площадь на 9 999,99 м² — реальный БЦ в неё не помещается."""
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
    """«4+тех.этаж» — то, что записано в Ф-2; целое число такую этажность не хранит."""
    passport = BuildingPassport.objects.create(space=building, number_of_floors="4+тех.этаж")

    passport.refresh_from_db()

    assert passport.number_of_floors == "4+тех.этаж"
