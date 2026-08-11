"""Карточка помещения в правой панели экрана этажа — то, что видно по HTTP.

Шов тот же, что у остальных экранов: граница HTTP. Панель приезжает своим адресом
и читается как ответ — какие факты о помещении на ней, куда ведут связи вверх и вниз
по дереву, что приходит на чужое помещение.

Двусторонняя подсветка дерева и плана живёт на стороне браузера, и по HTTP её не
наблюдать. Проверяется то, чем она кормится и что без неё бесполезно: у каждого узла
дерева и у каждого контура есть адрес карточки, а помещение без контура помечено, —
это договор экрана, а не оформление.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from building_passport.models import Space
from dictionary.models import DictSpaceSubtype

# Раздел «Аренда» читается тем же разбором атрибутов, что и счёт свободного на экране
# этажа: второй разбор той же разметки однажды разошёлся бы с первым.
from .test_floor_plan import marked

pytestmark = pytest.mark.django_db


def card_url(space):
    return reverse("building_passport:space_card", args=[space.pk])


def lease_url(lease):
    return reverse("leases:lease_detail", args=[lease.pk])


def lease_on(page):
    """Раздел «Аренда» — один на карточку, поэтому и берётся один.

    Его нет вовсе у помещения, которое не сдаётся: `None` здесь означает не «нет
    договора», а «вопроса об аренде этому помещению не задают».
    """
    found = marked(page, "data-lease")
    assert len(found) <= 1
    return found[0] if found else None


def open_card(client, space):
    response = client.get(card_url(space))
    return response, response.content.decode()


@pytest.fixture
def entrance(first_floor):
    """«каб101вход» со всем, что показывает карточка: подтип и площадь."""
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


# Факты о помещении


def test_the_card_shows_what_bcmp_holds_about_the_space(card):
    """Карточка отвечает на вопрос «что это за помещение», не открывая админку."""
    assert "man-f1-a" in card  # код
    assert "каб101вход" in card  # наименование
    assert "Офис" in card  # подтип
    assert "Помещение" in card  # тип помещения
    assert "6,55\u00a0м²" in card  # площадь, неразрывными пробелами


def test_a_space_without_an_area_says_so_rather_than_leaving_a_blank(
    client, member, first_floor
):
    """Пустое место читается как ноль, а прочерк — нет: та же запись, что и в паспорте."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-b"))

    assert "— нет данных" in page


# Место в дереве


def test_the_card_leads_to_the_space_this_one_is_part_of(client, member, first_floor):
    """По иерархии ходят, не выходя с этажа: связь вверх переставляет ту же панель."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a1"))

    assert "каб101вход" in page
    assert card_url(Space.objects.get(code="man-f1-a")) in page


def test_the_card_leads_to_the_spaces_inside_this_one(client, member, first_floor):
    """Связь вниз — тоже панель: спуск по дереву не уводит с плана."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a"))

    # Сверяется адрес, а не название: «каб101» содержится в «каб101вход», и проверка
    # по тексту прошла бы на заголовке самой карточки.
    assert card_url(Space.objects.get(code="man-f1-a1")) in page


def test_a_space_directly_under_the_floor_names_the_floor_it_lies_on(
    client, member, first_floor
):
    """Этаж называется, но карточкой не открывается: он не узел дерева, а сам экран."""
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-a"))

    assert "1 Этаж" in page
    assert card_url(first_floor) not in page


def test_the_card_names_no_space_of_another_organisation_below(
    client, member, central, first_floor
):
    """Связи вниз отбираются тем же чокпоинтом, что дерево и контуры.

    Такой строки в исправных данных нет; проверяется, что панель собирается через
    чокпоинт, а не запросом по `parent`.
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
    """Вверх по дереву — тот же чокпоинт: чужое имя не проедет и строкой «Выше».

    Пройти по `parent` напрямую было бы вторым местом, где решается, чьи данные
    показывать, — а второе место ADR 0001 и заводился отменить.
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


# Аренда


@pytest.fixture
def free_office(office):
    """«Офис 101» без единого договора — арендопригодный и пустой.

    Подтип и площадь заведены нарочно: прочерков на карточке должно быть ровно
    столько, сколько на ней пустых мест, и незаполненные поля паспорта не должны
    выдавать себя за отсутствующий договор.
    """
    office.subtype = DictSpaceSubtype.objects.create(
        type="room", name="Офис", short_name="Офис"
    )
    office.area_m2 = Decimal("52.30")
    office.save()
    return office


def test_the_card_names_who_rents_the_space_and_leads_to_the_lease(
    client, member, downtown, tenant, free_office, make_lease, make_subject
):
    """От точки на плане — к контрагенту: сотрудник УК видит, кто сидит в помещении.

    Ставка стоит на предмете, а не на договоре: договор на офис и склад не обязан
    идти по одной ставке, и карточка называет ту, что записана про это помещение.
    """
    lease = make_lease(downtown, tenant, date(2025, 1, 1), number="12-А")
    make_subject(lease, free_office, rate=Decimal("450000.00"))
    client.force_login(member)

    _, page = open_card(client, free_office)

    assert lease_on(page)["data-lease"] == "leased"
    assert "Ромашка ТОО" in page  # арендатор
    assert "01.01.2025 — по сей день" in page  # срок
    assert "450 000,00" in page  # ставка, неразрывными пробелами
    assert lease_url(lease) in page


def test_a_space_with_no_lease_reads_as_no_data_rather_than_an_empty_tenant_row(
    client, member, free_office
):
    """Отсутствие должно читаться отсутствием — то же правило, что и в паспорте (#5).

    Пустая строка «Арендатор» читалась бы как незаполненное поле, а прочерк говорит,
    что договора на это помещение нет вовсе. Прочерк на карточке при этом ровно один:
    подтип и площадь у «Офиса 101» заведены.
    """
    client.force_login(member)

    _, page = open_card(client, free_office)

    assert lease_on(page)["data-lease"] == "vacant"
    assert "Арендатор" not in page
    assert page.count("— нет данных") == 1


def test_a_lease_without_a_rate_reads_as_no_data(
    client, member, downtown, tenant, free_office, make_lease, make_subject
):
    """Ставку заводят не сразу, и пустая клетка прочиталась бы как «бесплатно».

    Арендатор и срок при этом названы: прочерков ровно столько, сколько незаведённых
    фактов, а не столько, сколько строк в разделе.
    """
    make_subject(make_lease(downtown, tenant), free_office)
    client.force_login(member)

    _, page = open_card(client, free_office)

    assert "Ромашка ТОО" in page
    assert page.count("— нет данных") == 1  # ставка


def test_a_lease_that_ended_before_today_leaves_the_space_free(
    client, member, downtown, tenant, free_office, make_lease, make_subject
):
    """Карточка читается на сегодня: съехавший арендатор в ней больше не сидит.

    Договор из истории здания не пропадает — он остаётся на своих экранах, — но
    помещение сегодня свободно, и панель говорит именно это.
    """
    yesterday = timezone.localdate() - timedelta(days=1)
    lease = make_lease(downtown, tenant, yesterday - timedelta(days=365), yesterday)
    make_subject(lease, free_office, rate=Decimal("450000.00"))
    client.force_login(member)

    _, page = open_card(client, free_office)

    assert lease_on(page)["data-lease"] == "vacant"
    assert "Ромашка ТОО" not in page


def test_a_space_that_is_not_leasable_is_not_asked_about_leases(client, member, first_floor):
    """У МОП и технического помещения арендатора не бывает: раздела нет вовсе.

    Прочерк здесь означал бы, что договор на ИТП забыли завести, — а его не бывает.
    """
    client.force_login(member)

    _, page = open_card(client, Space.objects.get(code="man-f1-b"))

    assert lease_on(page) is None
    assert "Аренда" not in page


# Чего в панели нет


def test_the_card_promises_no_documents_and_no_systems(card):
    """Раздел, обещающий данные, которых нет ни строки, хуже своего отсутствия."""
    assert "Документы" not in card
    assert "Системы" not in card


def test_the_card_carries_no_way_to_change_anything(card):
    """Панель read-only, как и дерево: запись остаётся в админке Django."""
    assert "Редактировать" not in card
    assert "Удалить" not in card
    assert "Добавить" not in card


# Доступ


def test_a_space_of_another_organisation_is_missing_rather_than_forbidden(
    client, member, central, make_floor, make_space
):
    """Панель — такой же путь чтения, как экран: 403 подтвердил бы, что помещение есть."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    room = make_space(make_floor(theirs, 1), "ctr-f1-a", "Чужое помещение")
    client.force_login(member)

    response, _ = open_card(client, room)

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_login(client, first_floor):
    """До входа о помещениях клиентов не видно ничего, включая карточку."""
    response, _ = open_card(client, Space.objects.get(code="man-f1-a"))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_a_superuser_reaches_the_card_of_any_organisation(
    client, django_user_model, central, make_floor, make_space
):
    """Разработчик воспроизводит проблему клиента, не выписывая себе членство."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    room = make_space(make_floor(theirs, 1), "ctr-f1-a", "Кабинет")
    client.force_login(django_user_model.objects.create_superuser("developer"))

    response, _ = open_card(client, room)

    assert response.status_code == 200
