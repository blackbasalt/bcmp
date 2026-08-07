"""Организации и здание, над которыми ставятся тесты.

Здание одно на весь набор: этаж и его помещения нужны и экрану этажа, и плану, и
двух определений одного и того же Manhattan быть не должно. Там, где тесту нужно
несколько штук — этажи, помещения, — фикстура отдаёт фабрику, а не готовый объект.
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
    """Организация существующих пяти БЦ."""
    return make_org("DownTown Management ТОО", "180540035878")


@pytest.fixture
def central(make_org):
    """Второй клиент — его данные не должны попадать к первому."""
    return make_org("Central City Properties ТОО", "201140031473")


@pytest.fixture
def member(django_user_model, downtown):
    """Сотрудник УК с членством в одной организации — обычный читатель экранов."""
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


@pytest.fixture
def manhattan(downtown):
    """Единственный БЦ с нутром — на нём и проверяется всё, что внутри здания."""
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
    """Помещение под другим пространством. Тип задаётся: контур несёт не только `room`."""

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
    """Первый этаж Manhattan с вложенностью: «каб101» стоит под «каб101вход»."""
    floor = make_floor(manhattan, 1)
    entrance = make_space(floor, "man-f1-a", "каб101вход")
    make_space(entrance, "man-f1-a1", "каб101")
    make_space(floor, "man-f1-b", "ИТП")
    return floor
