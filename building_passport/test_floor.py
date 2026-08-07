"""Экран этажа и путь к нему от Карточки БЦ — то, что сотрудник УК видит по HTTP.

Шов тот же, что у списка и карточки: граница HTTP. Тесты открывают этаж тестовым
клиентом от имени пользователя с известным членством и проверяют наблюдаемое — какие
помещения на экране, что с чем вложено и какой код ответа. Классы и вёрстка не
проверяются; единственная опора в разметке — атрибут `data-space` на узле дерева,
и он часть договора экрана, а не оформления: по нему план и дерево будут находить
друг друга.
"""

from html.parser import HTMLParser

import pytest
from django.urls import reverse

from building_passport.models import Space
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db

# Теги, которые закрывать не нужно: без них стек разбора съезжает на первом же `<meta>`.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}


class SpaceNesting(HTMLParser):
    """Кто внутри кого в дереве: для каждого узла — коды узлов над ним.

    Вложенность — единственное свойство дерева, которого не видно в тексте
    страницы: плоский список и дерево печатают одни и те же названия. Поэтому
    разбор идёт по `data-space`, а не по разметке вокруг него.
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


@pytest.fixture
def member(django_user_model, downtown):
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


@pytest.fixture
def manhattan(downtown):
    return Space.objects.create(org=downtown, type="building", code="man", name="Manhattan")


@pytest.fixture
def first_floor(manhattan):
    """Первый этаж Manhattan с вложенностью: «каб101» стоит под «каб101вход»."""
    floor = make_floor(manhattan, 1)
    entrance = make_room(floor, "man-f1-a", "каб101вход")
    make_room(entrance, "man-f1-a1", "каб101")
    make_room(floor, "man-f1-b", "ИТП")
    return floor


def make_floor(building, number):
    return Space.objects.create(
        org=building.org,
        type="floor",
        parent=building,
        building=building,
        code=f"{building.code}-f{number}",
        name=f"{number} Этаж",
        floor_number=number,
    )


def make_room(parent, code, name):
    return Space.objects.create(
        org=parent.org,
        type="room",
        parent=parent,
        building=parent.building,
        code=code,
        name=name,
    )


def floor_url(floor):
    return reverse("building_passport:floor", args=[floor.building_id, floor.pk])


def open_floor(client, floor):
    response = client.get(floor_url(floor))
    return response, response.content.decode()


@pytest.fixture
def floor_page(client, member, first_floor):
    client.force_login(member)
    _, page = open_floor(client, first_floor)
    return page


# Экран этажа


def test_a_member_opens_a_floor_of_their_own_building(client, member, first_floor):
    """Экран открывается и отрисовывается: ошибка шаблона обнаруживается здесь."""
    client.force_login(member)

    response, _ = open_floor(client, first_floor)

    assert response.status_code == 200


def test_a_floor_of_another_organisation_is_missing_rather_than_forbidden(
    client, member, central
):
    """403 подтвердил бы, что у другого клиента есть такое здание и такой этаж."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    client.force_login(member)

    response, _ = open_floor(client, make_floor(theirs, 1))

    assert response.status_code == 404


def test_a_floor_is_not_reachable_through_another_building(client, member, downtown, manhattan):
    """Адрес называет и здание, и этаж; несовпадение — не экран, а отсутствие."""
    boston = Space.objects.create(org=downtown, type="building", code="bos", name="Boston")
    floor = make_floor(boston, 7)
    client.force_login(member)

    response = client.get(reverse("building_passport:floor", args=[manhattan.pk, floor.pk]))

    assert response.status_code == 404


def test_a_space_that_is_not_a_floor_has_no_floor_screen(client, member, first_floor):
    """Помещение — не этаж: показывать по его адресу дерево этажа нечего."""
    room = Space.objects.get(code="man-f1-a")
    client.force_login(member)

    response = client.get(
        reverse("building_passport:floor", args=[first_floor.building_id, room.pk])
    )

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_login(client, first_floor):
    """До входа о зданиях клиентов не видно ничего, включая их этажи."""
    response = client.get(floor_url(first_floor))

    assert response.status_code == 302
    assert reverse("login") in response.url


# Дерево помещений


def test_the_tree_shows_every_space_under_the_floor_down_to_the_leaves(floor_page):
    """Дерево — единственный способ добраться до помещений без контура.

    Сверяются узлы, а не названия: «каб101» содержится в «каб101вход», и проверка
    по тексту прошла бы, даже если лист до экрана не доехал.
    """
    assert set(nesting(floor_page)) == {"man-f1-a", "man-f1-a1", "man-f1-b"}
    assert "каб101вход" in floor_page
    assert "ИТП" in floor_page


def test_a_nested_space_is_shown_nested_rather_than_flat(floor_page):
    """Плоский список теряет ровно то, ради чего дерево и заводится."""
    assert "man-f1-a" in nesting(floor_page)["man-f1-a1"]


def test_a_space_of_another_floor_is_not_in_this_floor_tree(client, member, first_floor):
    """Дерево этажа начинается с этажа: соседний этаж в него не подмешивается."""
    second = make_floor(first_floor.building, 2)
    make_room(second, "man-f2-a", "каб201")
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert "каб201" not in page


def test_the_tree_holds_no_space_of_another_organisation(client, member, central, first_floor):
    """Чужая строка под тем же этажом не должна доехать до экрана.

    Такой строки в исправных данных нет; проверяется, что дерево собирается через
    чокпоинт, а не обходит его собственным запросом.
    """
    Space.objects.create(
        org=central, type="room", parent=first_floor, building=first_floor.building,
        code="ctr-x", name="Чужое помещение",
    )
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert "Чужое помещение" not in page


# Разметка экрана и пустые состояния


def test_the_floor_keeps_a_place_for_the_card_of_a_space(floor_page):
    """Три области стоят с самого начала: правый край ждёт своего тикета пустым."""
    assert "Помещение не выбрано" in floor_page


def test_a_floor_without_a_plan_says_the_plan_is_not_loaded_yet(floor_page):
    """Отсутствие плана читается как «ещё не загружен», а не как поломка экрана."""
    assert "Поэтажный план для этого этажа не загружен" in floor_page


# Переходы с экрана этажа


def test_the_switcher_reaches_the_other_floors_of_the_building(client, member, first_floor):
    """Между этажами ходят с самого этажа, а не через возврат на Карточку БЦ."""
    second = make_floor(first_floor.building, 2)
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert floor_url(second) in page
    assert "2 Этаж" in page


def test_the_switcher_does_not_reach_a_floor_of_another_building(
    client, member, downtown, first_floor
):
    """Переключатель — этажи этого здания; чужие этажи в нём не значатся."""
    boston = Space.objects.create(org=downtown, type="building", code="bos", name="Boston")
    make_floor(boston, 7)
    client.force_login(member)

    _, page = open_floor(client, first_floor)

    assert "7 Этаж" not in page


def test_every_floor_leads_back_to_the_card_of_its_building(floor_page, manhattan):
    """С любого этажа возвращаются к паспорту, а не кнопкой «назад» в браузере."""
    assert reverse("building_passport:bc_detail", args=[manhattan.pk]) in floor_page


def test_the_screen_carries_no_way_to_change_anything(floor_page):
    """Дерево помещений read-only: запись остаётся в админке Django."""
    assert "Редактировать" not in floor_page
    assert "Удалить" not in floor_page
    assert "Добавить" not in floor_page


def test_the_page_carries_no_leftover_template_comments(floor_page):
    """Многострочный `{# … #}` Django комментарием не считает и печатает на экране."""
    assert "{#" not in floor_page
