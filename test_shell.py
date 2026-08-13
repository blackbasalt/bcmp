"""Меню оболочки — общий договор всех экранов, а не собственность одного раздела.

Стоит в корне, рядом с оболочкой, которую проверяет: подсветка пункта — это условие,
где раздел один отвечает за другой, и проверять её из тестов одного из разделов
значило бы, что второй раздел о своей же подсветке узнаёт из чужого набора.

Шов тот же, что и везде, — граница HTTP: открывается экран, и в его разметке
читаются пункты меню. Опора — `data-section` на пункте и `aria-current` на открытом:
цвет подсветки тестами не проверяется, он и меняется чаще всего.
"""

import re

import pytest
from django.urls import reverse

from parties.models import OrgMembership

pytestmark = pytest.mark.django_db

#: Пункт меню целиком — вместе с атрибутами, которыми он себя называет.
ITEM = re.compile(r'<a[^>]*data-section="(?P<section>[^"]+)"[^>]*>')


@pytest.fixture
def member(django_user_model, downtown):
    """Сотрудник УК: меню одинаково для всех, кто вошёл, — прав оно не спрашивает."""
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


def sidebar(client, url):
    """Пункты меню на открытом экране: раздел → сам пункт разметкой."""
    page = client.get(url).content.decode()
    return {item["section"]: item.group() for item in ITEM.finditer(page)}


def test_both_sections_are_offered_without_going_through_a_building(client, member):
    """Документы — первый экран проекта, до которого не открывают здание."""
    client.force_login(member)

    items = sidebar(client, reverse("building_passport:bc_list"))

    assert reverse("building_passport:bc_list") in items["building_passport"]
    assert reverse("documents:document_list") in items["documents"]


def test_the_documents_item_is_highlighted_inside_the_section(client, member):
    """Пункт подсвечен на всех экранах своего раздела, а не только на первом."""
    client.force_login(member)

    items = sidebar(client, reverse("documents:document_list"))

    assert 'aria-current="page"' in items["documents"]
    assert "aria-current" not in items["building_passport"]


def test_the_buildings_item_stays_highlighted_inside_a_building(client, member, manhattan):
    """Второй раздел не должен ломать первый: внутри здания подсвечены здания."""
    client.force_login(member)

    items = sidebar(client, reverse("building_passport:bc_detail", args=[manhattan.pk]))

    assert 'aria-current="page"' in items["building_passport"]
    assert "aria-current" not in items["documents"]


def test_the_buildings_item_stays_highlighted_inside_a_floor(client, member, first_floor):
    """Экран этажа — тот же раздел: подсветка держится за раздел, а не за экран."""
    client.force_login(member)

    items = sidebar(
        client,
        reverse("building_passport:floor", args=[first_floor.building_id, first_floor.pk]),
    )

    assert 'aria-current="page"' in items["building_passport"]
