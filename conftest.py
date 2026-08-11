"""Организации, здание и договоры, над которыми ставятся тесты.

Здание одно на весь набор: этаж и его помещения нужны и экрану этажа, и плану, и
двух определений одного и того же Manhattan быть не должно. Там, где тесту нужно
несколько штук — этажи, помещения, договоры, — фикстура отдаёт фабрику, а не готовый
объект. Аренда живёт здесь по той же причине: договор проверяется и моделью, и двумя
своими экранами, и один и тот же «Офис 101» не должен заводиться в каждом наборе
заново.
"""

from datetime import date

import pytest

from building_passport.models import Space
from leases.models import Lease, LeaseSubject
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


@pytest.fixture
def make_leasable(make_space):
    """Помещение, которое может сдаваться: арендопригодность — свойство помещения.

    Отдельная фабрика, а не флаг у `make_space`: предметом договора бывает только
    арендопригодное, и в тестах аренды это не одна из настроек помещения, а условие,
    без которого договор не заводится вовсе.
    """

    def _make_leasable(parent, code, name):
        space = make_space(parent, code, name)
        space.is_leasable = True
        space.save(update_fields=["is_leasable"])
        return space

    return _make_leasable


@pytest.fixture
def tenant(db):
    """Сторона, которую арендатором делает договор и только он (ADR 0008)."""
    return Party.objects.create(
        kind=Party.Kind.COMPANY, name="Ромашка ТОО", bin_iin="180540035879"
    )


@pytest.fixture
def office(first_floor, make_leasable):
    return make_leasable(first_floor, "man-f1-101", "Офис 101")


@pytest.fixture
def boston(downtown, make_floor):
    """Второй БЦ той же организации: договор не привязан к зданию вовсе."""
    building = Space.objects.create(
        org=downtown, type="building", code="bos", name="Boston"
    )
    return make_floor(building, 1)


@pytest.fixture
def warehouse(boston, make_leasable):
    return make_leasable(boston, "bos-f1-01", "Склад")


@pytest.fixture
def their_office(central, make_floor, make_leasable):
    """Арендопригодное помещение другого клиента платформы — и предмет, и утечка.

    Одно на весь набор: им проверяется и отказ предмета (`test_lease`), и то, что
    чужой договор не доезжает до экрана (`test_lease_screens`), — а Central Tower,
    заведённая дважды, однажды разъехалась бы сама с собой.
    """
    building = Space.objects.create(
        org=central, type="building", code="ctr", name="Central Tower"
    )
    return make_leasable(make_floor(building, 1), "ctr-f1-01", "Кабинет")


@pytest.fixture
def make_lease(db):
    """Договор аренды. Открытый конец — умолчание: он же означает «по сей день»."""

    def _make_lease(org, tenant, valid_from=date(2025, 1, 1), valid_to=None, **fields):
        return Lease.objects.create(
            org=org, tenant=tenant, valid_from=valid_from, valid_to=valid_to, **fields
        )

    return _make_lease


@pytest.fixture
def make_subject(db):
    """Предмет договора: помещение со своей ставкой и своей договорной площадью."""

    def _make_subject(lease, space, **fields):
        return LeaseSubject.objects.create(lease=lease, space=space, **fields)

    return _make_subject
