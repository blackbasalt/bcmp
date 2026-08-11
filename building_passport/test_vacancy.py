"""Вакансия на экране этажа: «свободно 12 из 44 помещений, 387 из 1529 м²».

Шов тот же, что у остальных экранов, — граница HTTP: тесты открывают этаж тестовым
клиентом от имени сотрудника с известным членством и читают то, что экран сказал.
Опора в разметке — атрибут `data-vacancy` на строке счёта и числа при нём:
`data-free` с `data-leasable` в помещениях, `data-free-m2` с `data-leasable-m2` в
метрах и `data-leases` — сколько договоров счёт под собой имеет. Это договор экрана,
а не оформление: по ним видно, что именно посчитано, а сам `data-vacancy` называет
день, на который счёт стоит.

Площади здесь заводятся на помещениях, а не на предметах договоров, и это не деталь
набора: счёт идёт по обмеру паспорта, а не по договорной площади (ADR 0006), и
подменить одно другим тест должен ловить.
"""

from decimal import Decimal

import pytest

from building_passport.models import Space

# Экран этажа открывается и читается тем же, чем и в наборе плана: второй разбор тех
# же атрибутов однажды разошёлся бы с первым в мелочи вроде пустых тегов, а второй
# `floor_url` — в имени маршрута.
from .test_floor_plan import day, floor_screen, marked, stated

pytestmark = pytest.mark.django_db


def counted_on(page):
    """Строка счёта свободного — одна на экран, поэтому и берётся одна."""
    found = marked(page, "data-vacancy")
    assert len(found) == 1
    return found[0]


@pytest.fixture
def make_office(make_leasable):
    """Арендопригодное помещение с обмеренной площадью.

    Площадь ставится тут же, а не отдельным шагом в каждом тесте: без неё счёт в
    метрах проверять нечем, а «арендопригодное без площади» — отдельный случай,
    который и заводится отдельно.
    """

    def _make_office(parent, code, name, area):
        space = make_leasable(parent, code, name)
        space.area_m2 = Decimal(area)
        space.save(update_fields=["area_m2"])
        return space

    return _make_office


@pytest.fixture
def offices(first_floor, make_office):
    """Три арендопригодных помещения на 200 м²: 100, 60 и 40.

    Рядом с ними — то, что этаж уже несёт от `first_floor`: «каб101вход», «каб101»
    и ИТП. Ни одно из них не арендопригодно, и в счёт не попадает ни числом, ни
    метром.
    """
    return (
        make_office(first_floor, "man-f1-101", "Офис 101", "100.00"),
        make_office(first_floor, "man-f1-102", "Офис 102", "60.00"),
        make_office(first_floor, "man-f1-103", "Офис 103", "40.00"),
    )


# Счёт свободного


def test_a_floor_with_no_leases_reports_every_leasable_space_free_and_names_no_lease(
    client, member, first_floor, offices
):
    """Пустая база не должна выглядеть обмеренным и полностью свободным зданием.

    «Свободно 3 из 3» само по себе читается как измеренный факт, поэтому рядом
    стоит то, на чём этот счёт держится: договоров нет ни одного.
    """
    page = floor_screen(client, member, first_floor)

    counted = counted_on(page)
    assert counted["data-free"] == "3"
    assert counted["data-leasable"] == "3"
    assert counted["data-free-m2"] == "200.00"
    assert counted["data-leasable-m2"] == "200.00"
    assert counted["data-leases"] == "0"
    assert "Ни один договор в этот день не действует" in stated(page)


def test_a_lease_in_force_takes_its_space_out_of_the_free_count_in_spaces_and_in_metres(
    client, member, first_floor, offices, downtown, tenant, make_lease, make_subject
):
    """Сданное помещение перестаёт быть свободным разом и в помещениях, и в метрах."""
    make_subject(make_lease(downtown, tenant, day(-30)), offices[0])

    page = floor_screen(client, member, first_floor)

    counted = counted_on(page)
    assert counted["data-free"] == "2"
    assert counted["data-leasable"] == "3"
    assert counted["data-free-m2"] == "100.00"
    assert counted["data-leasable-m2"] == "200.00"
    assert counted["data-leases"] == "1"
    assert "Свободно 2 из 3 помещений, 100,00 из 200,00 м²" in stated(page)


def test_a_lease_that_ended_yesterday_leaves_its_space_free(
    client, member, first_floor, offices, downtown, tenant, make_lease, make_subject
):
    """Договор, кончившийся вчера, сегодня уже ничего не занимает.

    Сказать при этом «договоров не заведено ни одного» экран не вправе: договор
    заведён, у него просто кончился срок. Отсутствие данных и кончившийся срок —
    разные вещи, и путать их в строке, которая как раз и защищает от чтения пустой
    базы как обмеренного здания, нельзя.
    """
    make_subject(make_lease(downtown, tenant, day(-365), day(-1)), offices[0])

    page = floor_screen(client, member, first_floor)

    counted = counted_on(page)
    assert counted["data-free"] == "3"
    assert counted["data-free-m2"] == "200.00"
    assert counted["data-leases"] == "0"
    assert "не заведено" not in stated(page)


def test_a_lease_starting_tomorrow_does_not_take_its_space_today(
    client, member, first_floor, offices, downtown, tenant, make_lease, make_subject
):
    """Заведённый заранее договор занимает помещение со своего дня, а не с заведения."""
    make_subject(make_lease(downtown, tenant, day(1)), offices[0])

    counted = counted_on(floor_screen(client, member, first_floor))

    assert counted["data-free"] == "3"
    assert counted["data-leases"] == "0"


def test_the_metres_come_from_the_passport_and_not_from_the_contract_area(
    client, member, first_floor, offices, downtown, tenant, make_lease, make_subject
):
    """Договорная площадь — условие соглашения, а не обмер здания (ADR 0006).

    Она больше обмера на долю МОП по коэффициенту, и попади она в счёт, свободные
    метры этажа поехали бы от коэффициента в чужом договоре.
    """
    make_subject(
        make_lease(downtown, tenant, day(-30)), offices[0], area_m2=Decimal("135.00")
    )

    counted = counted_on(floor_screen(client, member, first_floor))

    assert counted["data-leasable-m2"] == "200.00"
    assert counted["data-free-m2"] == "100.00"


def test_nested_leasable_spaces_are_counted_independently(
    client, member, first_floor, make_office, downtown, tenant, make_lease, make_subject
):
    """Вложенное арендопригодное сдаётся отдельно, поэтому и считается отдельно (#25).

    Метры при этом не задваиваются: у объединяющего родителя площадь своя — его
    собственная часть этажа, — и складывать её с площадью вложенного правильно.
    """
    parent = make_office(first_floor, "man-f1-201", "Блок 201", "80.00")
    child = make_office(parent, "man-f1-201a", "Кабинет 201а", "20.00")
    make_subject(make_lease(downtown, tenant, day(-30)), child)

    counted = counted_on(floor_screen(client, member, first_floor))

    assert counted["data-leasable"] == "2"
    assert counted["data-leasable-m2"] == "100.00"
    assert counted["data-free"] == "1"
    assert counted["data-free-m2"] == "80.00"


def test_what_is_not_leasable_stays_outside_the_count(
    client, member, first_floor, offices, make_space
):
    """МОП и техническое арендатору не сдаются: свободными они не бывают.

    Площадь у них при этом есть, и попади они в знаменатель, «свободно» этажа
    считалось бы от площади, которую сдавать некому.
    """
    corridor = make_space(first_floor, "man-f1-c", "Коридор")
    Space.objects.filter(pk=corridor.pk).update(is_common=True, area_m2=Decimal("300.00"))

    counted = counted_on(floor_screen(client, member, first_floor))

    assert counted["data-leasable"] == "3"
    assert counted["data-leasable-m2"] == "200.00"


def test_a_floor_without_leasable_spaces_says_so_instead_of_counting_zero_out_of_zero(
    client, member, first_floor
):
    """«Свободно 0 из 0» — не ответ, а вопрос к данным, и экран задаёт его словами."""
    page = floor_screen(client, member, first_floor)

    assert counted_on(page)["data-leasable"] == "0"
    assert "Арендопригодных помещений на этаже не заведено" in stated(page)


def test_a_leasable_space_without_an_area_is_counted_and_named_as_unmeasured(
    client, member, first_floor, offices, make_leasable
):
    """Метры, посчитанные не по всем, не должны выглядеть посчитанными по всем.

    В помещениях необмеренное считается как всякое другое — арендопригодность от
    площади не зависит, — а вот в метрах оно молча ушло бы в ноль, и «200 из 200»
    читалось бы обмером этажа.
    """
    make_leasable(first_floor, "man-f1-104", "Офис 104")

    page = floor_screen(client, member, first_floor)

    counted = counted_on(page)
    assert counted["data-leasable"] == "4"
    assert counted["data-leasable-m2"] == "200.00"
    assert "Площадь заведена не у всех" in stated(page)


# На скольких договорах счёт стоит


def test_a_lease_naming_two_spaces_of_the_floor_stands_under_the_count_once(
    client, member, first_floor, offices, downtown, tenant, make_lease, make_subject
):
    """Договор называет несколько помещений и остаётся одним договором."""
    lease = make_lease(downtown, tenant, day(-30))
    make_subject(lease, offices[0])
    make_subject(lease, offices[1])

    counted = counted_on(floor_screen(client, member, first_floor))

    assert counted["data-free"] == "1"
    assert counted["data-leases"] == "1"


def test_the_count_stands_on_the_leases_of_this_floor_and_no_others(
    client,
    member,
    first_floor,
    offices,
    warehouse,
    downtown,
    tenant,
    make_lease,
    make_subject,
):
    """Договор на склад в соседнем БЦ о вакансии этого этажа не говорит ничего."""
    make_subject(make_lease(downtown, tenant, day(-30)), warehouse)

    counted = counted_on(floor_screen(client, member, first_floor))

    assert counted["data-free"] == "3"
    assert counted["data-leases"] == "0"


# День, на который счёт посчитан


def test_the_count_is_computed_as_of_the_day_in_the_address(
    client, member, first_floor, offices, downtown, tenant, make_lease, make_subject
):
    """«Что освобождается к январю» — вопрос к экрану, а не к списку договоров.

    Помещение, чей договор кончается в декабре, в январе свободно, и увидеть это
    надо счётом, а не вычитанием сроков глазами.
    """
    make_subject(make_lease(downtown, tenant, day(-365), day(30)), offices[0])

    today = counted_on(floor_screen(client, member, first_floor))
    later = counted_on(
        floor_screen(client, member, first_floor, date=day(60).isoformat())
    )

    assert today["data-free"] == "2"
    assert today["data-leases"] == "1"
    assert later["data-free"] == "3"
    assert later["data-free-m2"] == "200.00"
    assert later["data-leases"] == "0"


def test_the_count_names_the_day_it_stands_on_and_defaults_to_today(
    client, member, first_floor, offices
):
    """День назван самим счётом: «свободно 44 из 44» без дня — половина ответа."""
    today = counted_on(floor_screen(client, member, first_floor))
    chosen = counted_on(
        floor_screen(client, member, first_floor, date=day(60).isoformat())
    )

    assert today["data-vacancy"] == day(0).isoformat()
    assert chosen["data-vacancy"] == day(60).isoformat()
    assert f"{day(60):%d.%m.%Y}" in stated(
        floor_screen(client, member, first_floor, date=day(60).isoformat())
    )


def test_the_chosen_day_is_named_even_where_there_is_nothing_to_count(
    client, member, first_floor
):
    """Этаж без арендопригодных считать не из чего, а день назвать всё равно надо.

    Иначе экран, спрошенный про январь, молчит о январе — и читается сегодняшним;
    рядом с этим молчанием стоит предупреждение о выходе за период плана, которое
    январь называет, и экран начинает спорить сам с собой.
    """
    page = floor_screen(client, member, first_floor, date=day(60).isoformat())

    assert marked(page, "data-as-of")
    assert f"{day(60):%d.%m.%Y}" in stated(page)


def test_a_date_the_address_cannot_state_leaves_the_count_on_today(
    client, member, first_floor, offices
):
    """Адрес правят руками: опечатка в дате считает сегодня, а не роняет экран."""
    counted = counted_on(floor_screen(client, member, first_floor, date="вчера"))

    assert counted["data-vacancy"] == day(0).isoformat()


def test_the_floor_counts_its_vacancy_with_no_plan_on_the_screen(
    client, member, first_floor, offices
):
    """Вакансия — свойство этажа, а не чертежа: считается она и там, где плана нет.

    Полнота плана без чертежа не считается вовсе, и счёт свободного, встав рядом с
    ней, унаследовал бы это молчание: этаж, чей план не загружен, перестал бы
    отвечать на первый вопрос, который управляющей компании задают.
    """
    page = floor_screen(client, member, first_floor)

    assert "Поэтажный план" in page
    assert counted_on(page)["data-free"] == "3"
