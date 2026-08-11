"""Карточка БЦ — паспорт здания так, как его читает сотрудник УК.

Шов тот же, что и у списка: граница HTTP. Тест открывает БЦ тестовым клиентом от
имени пользователя с известным членством и проверяет наблюдаемое — что на экране
и какой код ответа. Разметка и классы не проверяются: перестройка вёрстки ниже
уровня URL не должна переписывать набор тестов.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from building_passport.models import BuildingPassport, Space
from parties.models import OrgMembership, Party

pytestmark = pytest.mark.django_db

SECTIONS = ["Идентификация", "Характеристики", "Конструктив и безопасность", "Стороны"]


@pytest.fixture
def member(django_user_model, downtown):
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


@pytest.fixture
def manhattan(downtown):
    return Space.objects.create(org=downtown, type="building", code="man", name="Manhattan")


@pytest.fixture
def filled_page(client, member, manhattan):
    """Экран паспорта, в котором заполнено всё: на нём видны все четыре раздела."""
    fill_passport(manhattan)
    client.force_login(member)
    _, page = open_bc(client, manhattan)
    return page


def make_party(name):
    return Party.objects.create(kind=Party.Kind.COMPANY, name=name)


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


def fill_passport(building, **overrides):
    """Заполненный паспорт: в нём есть значение в каждом из четырёх разделов."""
    fields = {
        "address": "пр. Ракымжан Кошкарбаев, зд 1/2",
        "cadastral_no": "21:319:031:1234",
        "inventory_number": "0123456",
        "intended_purpose": "Административное здание",
        "total_area": Decimal("25480.75"),
        "building_footprint": Decimal("2484.10"),
        "non_residential_area": Decimal("25480.75"),
        "number_of_floors": "4+тех.этаж",
        "building_volume": Decimal("98765.40"),
        "year_built": 2017,
        "building_class": "B+",
        "wall_material": "Монолитный железобетон",
        "structural_scheme": "монолит",
        "fire_resistance_degree": "II",
        "functional_fire_class": "Ф4.3",
        "structural_fire_class": "С0",
        "seismic_points": 7,
        "energy_class": "B",
        "owner_party": make_party("DownTown Invest ТОО"),
        "operator_party": make_party("DownTown Management ТОО"),
        "designer_party": make_party("Проектная мастерская Астана ТОО"),
        "builder_party": make_party("BI Construction ТОО"),
    }
    fields.update(overrides)
    return BuildingPassport.objects.create(space=building, **fields)


def open_bc(client, building, **address):
    """Карточка БЦ. `address` — параметры адреса, вроде `date`, которым считают счёт."""
    response = client.get(
        reverse("building_passport:bc_detail", args=[building.pk]), address
    )
    return response, response.content.decode()


def test_a_member_opens_a_building_of_their_own_organisation(client, member, manhattan):
    """Экран открывается и отрисовывается: ошибка шаблона обнаруживается здесь."""
    fill_passport(manhattan)
    client.force_login(member)

    response, _ = open_bc(client, manhattan)

    assert response.status_code == 200


def test_a_building_of_another_organisation_is_missing_rather_than_forbidden(
    client, member, central
):
    """403 подтвердил бы, что такой БЦ есть у другого клиента."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    client.force_login(member)

    response, _ = open_bc(client, theirs)

    assert response.status_code == 404


def test_a_filled_passport_is_read_in_four_sections(filled_page):
    """Поле находится по разделу, а не вычитывается со всего экрана."""
    assert [section for section in SECTIONS if section not in filled_page] == []


def test_identification_matches_the_building_against_an_external_registry(filled_page):
    """Адрес, кадастровый и инвентарный номера, назначение — рядом, а не по разделам."""
    assert "пр. Ракымжан Кошкарбаев, зд 1/2" in filled_page
    assert "21:319:031:1234" in filled_page
    assert "0123456" in filled_page
    assert "Административное здание" in filled_page


def test_characteristics_answer_what_a_tenant_or_valuer_asks_most_often(filled_page):
    """Площади, объём, год постройки и класс — то, что спрашивают чаще всего."""
    assert "25\u00a0480,75\u00a0м²" in filled_page  # общая площадь, неразрывными пробелами
    assert "2\u00a0484,10\u00a0м²" in filled_page  # площадь застройки
    assert "98\u00a0765,40\u00a0м³" in filled_page  # строительный объём
    assert "2017" in filled_page
    assert "B+" in filled_page


def test_construction_and_safety_hold_what_a_norm_is_checked_against(filled_page):
    """Инженер УК сверяет здание с нормой, не поднимая бумажный паспорт."""
    assert "Монолитный железобетон" in filled_page
    assert "монолит" in filled_page
    assert "Ф4.3" in filled_page
    assert "С0" in filled_page
    assert "Степень огнестойкости" in filled_page
    assert "Расчётная сейсмичность" in filled_page
    assert "Энергокласс" in filled_page


def test_the_parties_are_named_so_the_user_knows_whom_to_call(filled_page):
    """Идентификатор стороны звонить некому — на экране имя."""
    assert "DownTown Invest ТОО" in filled_page
    assert "DownTown Management ТОО" in filled_page
    assert "Проектная мастерская Астана ТОО" in filled_page
    assert "BI Construction ТОО" in filled_page


def test_the_number_of_floors_is_shown_exactly_as_it_was_recorded(client, member, manhattan):
    """«4+тех.этаж» — то, что записано в Ф-2; разбирать эту запись в число нечем."""
    fill_passport(manhattan, number_of_floors="4+тех.этаж")
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert "4+тех.этаж" in page


def test_an_empty_field_of_a_shown_section_reads_as_no_data(client, member, manhattan):
    """Экран заодно показывает, что ещё осталось собрать, — но только прочерком."""
    fill_passport(manhattan, inventory_number=None, intended_purpose="")
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert "Идентификация" in page
    assert page.count("— нет данных") == 2  # инвентарный номер и назначение


def test_a_section_without_a_single_value_does_not_appear(client, member, manhattan):
    """Иначе редкий паспорт превращается в стену прочерков."""
    BuildingPassport.objects.create(
        space=manhattan, address="пр. Ракымжан Кошкарбаев, зд 1/2", year_built=2017
    )
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert "Идентификация" in page
    assert "Характеристики" in page
    assert "Конструктив и безопасность" not in page
    assert "Стороны" not in page


def test_a_building_without_a_passport_opens_instead_of_failing(client, member, manhattan):
    """Паспорт ещё не завели — это состояние данных, а не ошибка экрана."""
    client.force_login(member)

    response, page = open_bc(client, manhattan)

    assert response.status_code == 200
    assert "Manhattan" in page
    assert [section for section in SECTIONS if section in page] == []


def test_an_entirely_empty_passport_is_not_reported_as_a_missing_one(
    client, member, manhattan
):
    """Строка паспорта есть, значений нет: экран не должен утверждать, что паспорта нет."""
    BuildingPassport.objects.create(space=manhattan)
    client.force_login(member)

    response, page = open_bc(client, manhattan)

    assert response.status_code == 200
    assert "не заведён" not in page
    assert [section for section in SECTIONS if section in page] == []


def test_a_commercial_passport_is_not_padded_with_residential_lines(
    client, member, manhattan
):
    """Столбцы жилья в базе есть, на экране коммерческого БЦ им делать нечего."""
    fill_passport(
        manhattan, living_area=Decimal("1234.00"), apartments_number=12, total_rooms=48
    )
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert "Жилая площадь" not in page
    assert "квартир" not in page
    assert "комнат" not in page


def test_the_card_lists_the_floors_of_the_building(client, member, manhattan):
    """Внутрь здания входят с его паспорта, а не через отдельное меню."""
    make_floor(manhattan, 1)
    make_floor(manhattan, 2)
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert "Этажи" in page
    assert "1 Этаж" in page
    assert "2 Этаж" in page


def test_a_floor_opens_from_the_card_in_one_click(client, member, manhattan):
    """До этажа — один переход: на карточке стоит адрес самого этажа."""
    floor = make_floor(manhattan, 1)
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert reverse("building_passport:floor", args=[manhattan.pk, floor.pk]) in page


def test_a_building_without_floors_keeps_its_existing_treatment(client, member, manhattan):
    """У четырёх БЦ без нутра этажей нет — и раздела «Этажи» на карточке тоже."""
    client.force_login(member)

    response, page = open_bc(client, manhattan)

    assert response.status_code == 200
    assert "Этажи" not in page


def test_the_card_does_not_list_the_floors_of_another_building(
    client, member, downtown, manhattan
):
    """Этажи соседнего здания на этой карточке — чужая навигация, а не выбор."""
    boston = Space.objects.create(org=downtown, type="building", code="bos", name="Boston")
    make_floor(boston, 7)
    make_floor(manhattan, 1)
    client.force_login(member)

    _, page = open_bc(client, manhattan)

    assert "7 Этаж" not in page


def test_every_passport_leads_back_to_the_list_of_buildings(filled_page):
    """Между зданиями ходят через список, а не через кнопку «назад» в браузере."""
    assert reverse("building_passport:bc_list") in filled_page


def test_the_screen_carries_no_way_to_change_anything(filled_page):
    """Первый этап — только чтение; запись остаётся в админке Django."""
    assert "Редактировать" not in filled_page
    assert "Удалить" not in filled_page
    assert "Добавить" not in filled_page


def test_the_page_carries_no_leftover_template_comments(filled_page):
    """Многострочный `{# … #}` Django комментарием не считает и печатает на экране."""
    assert "{#" not in filled_page
