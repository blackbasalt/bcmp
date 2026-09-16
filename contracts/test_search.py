"""Отбор на полке договоров — шесть условий одним вопросом, по HTTP.

Шов тот же, что и у всего раздела: граница HTTP адреса `/contracts/`. Спрашивают у полки
адресом, а проверяется то, какие договоры вернулись, что о них написано и что после этого
стоит в полосе, в которую вопрос набирали.

Опора в разметке — `data-contract` на строке таблицы: отбор — это всего лишь другой набор
строк, и читается он так же, как читается вся полка. Сама полоса несёт `data-search` —
можно ли полку сузить вообще, утверждение отдельное от того, что отвечает любой отдельный
отбор.

Изоляция проверяется здесь заново, а не оставлена тестам раздела, и это нарочно: отбор —
единственное на экране, что берёт значение у читателя и кладёт его в запрос, поэтому
«отбором нельзя дотянуться до чужого» приходится утверждать о самих условиях (ADR 0006).
"""

from datetime import timedelta

import pytest
from django.urls import reverse

from building_passport.models import Space
from documents.models import ContractTerms, Document
from parties.models import Party

from .test_shelf import contracts_on, count_line, stated

pytestmark = pytest.mark.django_db


def asked(client, **conditions):
    """Полка с заданным ей вопросом — условия едут в адресе."""
    response = client.get(reverse("contracts:contract_list"), conditions)
    return response, response.content.decode()


def sunday_of_this_week(today):
    """Воскресенье текущей недели, найденное шагом по дню.

    Нарочно другой дорогой, чем считает `bcmp.windows`: помощник, повторяющий ту же
    арифметику, соглашался бы с проверяемым кодом, что бы тот ни делал.
    """
    day = today
    while day.isoweekday() != 7:
        day += timedelta(days=1)
    return day


def last_day_of_this_month(today):
    """Последнее число текущего месяца, найденное шагом до смены месяца."""
    day = today
    while (day + timedelta(days=1)).month == day.month:
        day += timedelta(days=1)
    return day


@pytest.fixture
def portfolio(downtown, alpha, petrov, make_contract, today):
    """Договоры всех видов, о которых спрашивают шесть условий, — одним набором.

    Одним набором, а не по фикстуре на условие: условия задают вместе, и набор на каждое
    оставил бы проверку их сложения строить портфель второй раз и чуть иначе.
    """
    return {
        # Расходный, с концом срока и контрагентом — обычная строка полки.
        "lifts": make_contract(
            downtown,
            "Договор на обслуживание лифтов",
            doc_no="ЭКС-2026/04",
            kind=ContractTerms.Kind.OPERATION,
            counterparty=alpha,
            valid_until=today + timedelta(days=200),
        ),
        # Доходный: через него отвечает и род, и БЦ — БЦ через свои аренды.
        "rent": make_contract(
            downtown,
            "Договор аренды помещений",
            doc_no="АР-2026/11",
            kind=ContractTerms.Kind.LEASE,
            counterparty=alpha,
            valid_until=today + timedelta(days=200),
        ),
        # Бессрочный: из срокового условия выпадает, и это ответ, а не пробел (ADR 0031).
        "paper": make_contract(
            downtown,
            "Договор поставки бумаги",
            doc_no="ПОСТ-7",
            kind=ContractTerms.Kind.SUPPLY,
            counterparty=petrov,
            is_perpetual=True,
        ),
        # Скан из пачки: ни вида, ни срока, ни контрагента (ADR 0035).
        "bare": make_contract(downtown, "Скан договора из пачки"),
    }


@pytest.fixture
def let_room(first_floor, portfolio, alpha, make_lease):
    """Помещение Manhattan, сданное по договору аренды, — путь договора к своему БЦ.

    Договор аренды достаёт до БЦ через свои аренды и их помещения, и другого пути ему не
    нужно (ADR 0033).
    """
    room = Space.objects.get(code="man-f1-a")
    make_lease(room, alpha, contract=portfolio["rent"])
    return room


# Поиск


def test_a_contract_is_found_by_its_title(client, member, portfolio):
    """Вопрос, с которым приходят: «где договор на лифты», и название помнят, а номер нет."""
    client.force_login(member)

    _, page = asked(client, q="лифт")

    assert contracts_on(page) == [str(portfolio["lifts"].pk)]


def test_a_contract_is_found_by_its_number(client, member, portfolio):
    """Номер — то, что держат в руках, читая его со счёта: он ищется тем же полем."""
    client.force_login(member)

    _, page = asked(client, q="АР-2026")

    assert contracts_on(page) == [str(portfolio["rent"].pk)]


def test_the_number_is_found_whatever_the_case_it_was_typed_in(client, member, portfolio):
    """«ар-2026» и «АР-2026» — одна строка: на SQLite `LIKE` сворачивает регистр только для
    ASCII, и `icontains` нашёл бы латиницу, не найдя кириллицы (ADR 0014)."""
    client.force_login(member)

    _, page = asked(client, q="ар-2026")

    assert contracts_on(page) == [str(portfolio["rent"].pk)]


def test_the_title_is_found_whatever_the_case_it_was_typed_in(client, member, portfolio):
    """То же и о названии, и кириллица складывается наравне с латиницей (ADR 0014)."""
    client.force_login(member)

    _, page = asked(client, q="ЛИФТ")

    assert contracts_on(page) == [str(portfolio["lifts"].pk)]


def test_the_search_reaches_no_further_than_the_title_and_the_number(
    client, member, portfolio
):
    """Слово, набранное ради одной бумаги, не должно отвечать всеми, у кого тот же
    контрагент: у контрагента есть своё условие, и спрашивают его, когда его имеют в виду."""
    client.force_login(member)

    _, page = asked(client, q="Альфа")

    assert contracts_on(page) == []


# Вид


def test_the_kind_narrows_the_shelf(client, member, portfolio):
    """«Все наши договоры эксплуатации» — одно нажатие."""
    client.force_login(member)

    _, page = asked(client, kind=ContractTerms.Kind.OPERATION)

    assert contracts_on(page) == [str(portfolio["lifts"].pk)]


def test_a_kind_that_is_not_a_kind_empties_the_shelf_and_says_why(client, member, portfolio):
    """Нечитаемое условие сужает полку до нуля, а не отбрасывается (ADR 0014), — и экран
    называет причину: иначе список стоял бы на «Любой вид» над пустотой."""
    client.force_login(member)

    _, page = asked(client, kind="капремонт")

    assert contracts_on(page) == []
    assert "В адресе указан вид, которого нет в списке." in stated(page)


# Род


def test_the_genus_tells_income_from_expense(client, member, portfolio):
    """Доходные и расходные врозь, не перечисляя виды по одному."""
    client.force_login(member)

    _, page = asked(client, genus="income")

    assert contracts_on(page) == [str(portfolio["rent"].pk)]


def test_the_expense_genus_gathers_every_kind_that_stands_on_that_side(
    client, member, portfolio
):
    """Три вида одной стороны отвечают вместе: род на то и заведён, чтобы не набирать их
    по одному."""
    client.force_login(member)

    _, page = asked(client, genus="expense")

    assert contracts_on(page) == [str(portfolio["lifts"].pk), str(portfolio["paper"].pk)]


def test_a_contract_with_no_kind_stands_on_neither_side(client, member, portfolio):
    """У договора без вида рода нет, и это не ошибка: «всё, что не доходное» записало бы
    скан из пачки в расходные — тот самый угаданный род, от которого правило отказывается."""
    client.force_login(member)

    _, income = asked(client, genus="income")
    _, expense = asked(client, genus="expense")

    assert str(portfolio["bare"].pk) not in contracts_on(income)
    assert str(portfolio["bare"].pk) not in contracts_on(expense)


def test_the_genus_follows_the_kind_and_is_stored_beside_it_nowhere(
    client, member, portfolio
):
    """Род нигде не хранится: правленный вид меняет сторону сам, и второй правды о ней,
    которую пришлось бы править следом, не существует."""
    terms = portfolio["lifts"].attached_terms()
    terms.kind = ContractTerms.Kind.EXTRA_SERVICES
    terms.save()
    client.force_login(member)

    _, page = asked(client, genus="income")

    assert str(portfolio["lifts"].pk) in contracts_on(page)


def test_a_genus_that_is_not_a_genus_empties_the_shelf_and_says_why(client, member, portfolio):
    """Родов два и ровно два, и третий, взявшийся из адреса, — не отбор, а опечатка."""
    client.force_login(member)

    _, page = asked(client, genus="opex")

    assert contracts_on(page) == []
    assert "В адресе указан род, которого нет в списке." in stated(page)


# Контрагент


def test_the_counterparty_narrows_the_shelf(client, member, portfolio, alpha):
    """«Что у нас с ТОО «Альфа»» отвечено с полки, а не обходом строк глазами."""
    client.force_login(member)

    _, page = asked(client, counterparty=str(alpha.pk))

    assert contracts_on(page) == [str(portfolio["rent"].pk), str(portfolio["lifts"].pk)]


def test_the_list_of_counterparties_holds_only_those_the_reader_has_contracts_with(
    client, member, portfolio, alpha, petrov, central, make_contract
):
    """Список — контрагенты своих договоров: Сторона, с которой у читателя не подписано
    ничего, отвечала бы «ничего не нашлось» по построению, а чужая назвала бы, с кем
    работает другой клиент (ADR 0006)."""
    stranger = make_contract(central, "Чужой договор", kind=ContractTerms.Kind.SUPPLY)
    terms = stranger.attached_terms()
    terms.counterparty = petrov
    terms.save()
    portfolio["paper"].attached_terms().delete()
    client.force_login(member)

    _, page = asked(client)

    assert "ТОО «Альфа»" in page
    assert "ИП Петров" not in page


def test_a_counterparty_the_reader_has_no_contracts_with_empties_the_shelf_and_says_why(
    client, member, portfolio, central, make_contract
):
    """Чужой контрагент, названный в адресе, отвечает тем же, чем несуществующий: сказать
    их врозь значило бы сказать, с кем работает другой клиент (ADR 0006)."""
    theirs = Party.objects.create(
        kind=Party.Kind.COMPANY, name="ТОО «Чужой подрядчик»", bin_iin="990140000001"
    )
    stranger = make_contract(central, "Чужой договор", kind=ContractTerms.Kind.SUPPLY)
    terms = stranger.attached_terms()
    terms.counterparty = theirs
    terms.save()
    client.force_login(member)

    _, page = asked(client, counterparty=str(theirs.pk))

    assert contracts_on(page) == []
    assert "В адресе указан контрагент, которого нет в списке." in stated(page)
    assert "Чужой подрядчик" not in page


# Кончается


def test_the_condition_narrows_the_shelf_to_this_week(
    client, member, downtown, portfolio, make_contract, today
):
    """Реестр сроков и есть полка, отвечающая на вопрос, — те же строки, тот же счёт и тот
    же адрес, который можно отправить коллеге.

    Поставлено на самой границе — воскресенье и понедельник за ним, — потому что это и
    значит слово: «на этой неделе» — календарная неделя, а не семь дней скользящим окном.
    """
    edge = sunday_of_this_week(today)
    ending = make_contract(downtown, "Договор охраны", valid_until=edge)
    make_contract(downtown, "Договор уборки", valid_until=edge + timedelta(days=1))
    client.force_login(member)

    _, page = asked(client, ending="week")

    assert contracts_on(page) == [str(ending.pk)]


def test_the_condition_narrows_the_shelf_to_this_month(
    client, member, downtown, portfolio, make_contract, today
):
    """Второе из трёх: перезаключают заранее, и «на этой неделе» отвечает слишком поздно
    для всего, что надо согласовать."""
    edge = last_day_of_this_month(today)
    ending = make_contract(downtown, "Договор охраны", valid_until=edge)
    make_contract(downtown, "Договор уборки", valid_until=edge + timedelta(days=1))
    client.force_login(member)

    _, page = asked(client, ending="month")

    assert contracts_on(page) == [str(ending.pk)]


def test_the_condition_narrows_the_shelf_to_the_next_ninety_days(
    client, member, downtown, portfolio, make_contract, today
):
    """Самое дальнее из трёх, и единственное скользящее: девяносто дней вперёд одинаковы,
    откуда ни считай, а «этот квартал» тридцать первого марта не значит ничего."""
    ending = make_contract(downtown, "Договор охраны", valid_until=today + timedelta(days=90))
    make_contract(downtown, "Договор уборки", valid_until=today + timedelta(days=91))
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert contracts_on(page) == [str(ending.pk)]


def test_a_term_that_has_already_run_out_does_not_answer_the_condition(
    client, member, downtown, portfolio, make_contract, today
):
    """«Кончается» спрашивают о том, что ещё предстоит: обязательство, истёкшее в
    понедельник, в среду уже кончилось, а не кончается."""
    make_contract(downtown, "Договор охраны", valid_until=today - timedelta(days=1))
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert contracts_on(page) == []


def test_a_perpetual_contract_falls_out_of_the_term_condition(client, member, portfolio):
    """Конца срока у него нет по самому соглашению, и взвесить его вопросом «когда
    кончается» не выйдет (ADR 0031)."""
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert str(portfolio["paper"].pk) not in contracts_on(page)


def test_a_contract_with_no_term_falls_out_of_the_term_condition(client, member, portfolio):
    """И скан из пачки тоже: «не нашлось» тут значило бы «таких нет», тогда как правда —
    «мы не знаем» (ADR 0031)."""
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert str(portfolio["bare"].pk) not in contracts_on(page)


def test_what_the_term_condition_could_not_weigh_is_a_number_on_the_count_line(
    client, member, portfolio
):
    """Выпавшие названы числом, а не молчанием: отбор не заявляет, будто взвесил то, чего
    не смог прочесть (ADR 0031)."""
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert "бессрочных договоров 1" in count_line(page)
    assert "срок не заведён у 1" in count_line(page)


def test_the_unrecorded_term_is_named_once_on_a_line_that_names_it_twice_over(
    client, member, portfolio
):
    """«срок не заведён» стоит на строке счёта в двух ролях — находкой по показанному и
    счётом отложенного в сторону, — и одновременно их не бывает: под сроковым условием у
    каждой показанной строки дата заведена, и находке считать нечего. Слово одно на оба
    случая нарочно, и это утверждение о том, что читатель не увидит его дважды с разными
    числами."""
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert count_line(page).count("срок не заведён") == 1


def test_nothing_is_said_about_weighing_when_the_term_was_not_asked_about(
    client, member, portfolio
):
    """Полка, у которой о сроке не спрашивали, ничего и не откладывала в сторону."""
    client.force_login(member)

    _, page = asked(client)

    assert "не взвешено" not in count_line(page)


def test_the_term_condition_takes_no_free_number_of_days(client, member, portfolio):
    """Свободное число дней пригласило бы ввести 0 и 3650: значений три, и всё, что не
    одно из трёх, сужает полку до пустой и названо словами (ADR 0014)."""
    client.force_login(member)

    _, page = asked(client, ending="120")

    assert contracts_on(page) == []
    assert "«кончается» знает три значения" in stated(page)


# БЦ


def test_the_building_narrows_through_the_leases_of_a_lease_contract(
    client, member, portfolio, let_room, manhattan
):
    """Договор аренды достаёт до БЦ через свои аренды и их помещения, и другого пути ему
    не нужно (ADR 0033)."""
    client.force_login(member)

    _, page = asked(client, building=str(manhattan.pk))

    assert contracts_on(page) == [str(portfolio["rent"].pk)]


def test_an_expense_contract_falls_out_of_the_building_condition(
    client, member, portfolio, let_room, manhattan
):
    """Расходный договор здания не называет вовсе (ADR 0033): клининг, купленный на все
    пять БЦ, разложенный по зданиям превратился бы в пять выдуманных договоров."""
    client.force_login(member)

    _, page = asked(client, building=str(manhattan.pk))

    assert str(portfolio["lifts"].pk) not in contracts_on(page)
    assert str(portfolio["paper"].pk) not in contracts_on(page)


def test_the_shelf_says_the_building_narrows_it_to_lease_contracts(
    client, member, portfolio, let_room, manhattan
):
    """Отсутствие расходных — ответ, а не поломка, и сказано это прямо: молча полка
    выглядела бы потерявшей четыре вида из пяти."""
    client.force_login(member)

    _, page = asked(client)

    assert 'Сужает полку до договоров вида «Аренда помещений»' in stated(page)


def test_a_lease_contract_with_several_leases_in_one_building_is_one_row(
    client, member, portfolio, let_room, first_floor, alpha, make_lease, manhattan
):
    """Два арендатора одного договора в одном БЦ — одна строка: полка отвечает договорами,
    а не их арендами, и вторая строка сбила бы и счёт под таблицей."""
    other = Space.objects.get(code="man-f1-b")
    make_lease(other, alpha, contract=portfolio["rent"])
    client.force_login(member)

    _, page = asked(client, building=str(manhattan.pk))

    assert contracts_on(page) == [str(portfolio["rent"].pk)]
    assert "Показано 1 из 4 договоров" in count_line(page)


def test_a_building_of_another_organisation_empties_the_shelf_and_says_why(
    client, member, portfolio, let_room, central, make_building
):
    """Чужой БЦ отвечает тем же, чем несуществующий: сказать их врозь значило бы сказать
    читателю, какие здания есть у другого клиента (ADR 0006)."""
    theirs = make_building(central, "ctr", "Central City")
    client.force_login(member)

    _, page = asked(client, building=str(theirs.pk))

    assert contracts_on(page) == []
    assert "В адресе указан БЦ, которого нет в списке." in stated(page)
    assert "Central City" not in page


# Условия складываются


def test_the_conditions_are_asked_together(client, member, portfolio, alpha, today):
    """Шесть условий — один вопрос, а не шесть вопросов подряд: отвеченные по одному, они
    оставили бы экрану самому решать, как их сложить."""
    client.force_login(member)

    _, page = asked(client, q="Договор", genus="expense", counterparty=str(alpha.pk))

    assert contracts_on(page) == [str(portfolio["lifts"].pk)]


def test_the_findings_of_the_count_line_are_conditions_of_the_same_question(
    client, member, portfolio
):
    """Две находки строки счёта стоят в той же форме седьмой и восьмой: набранные ссылкой,
    они обязаны и сбрасываться тем же «Сбросить»."""
    client.force_login(member)

    _, page = asked(client, no_kind="1")

    assert contracts_on(page) == [str(portfolio["bare"].pk)]
    assert "Сбросить" in page


# Полоса отбора


def test_the_bar_holds_on_to_every_condition_that_was_asked(
    client, member, portfolio, alpha, manhattan, let_room
):
    """Полоса, опустевшая после ответа, оставила бы читателя перед укороченной полкой, на
    которой ничто не говорит почему."""
    client.force_login(member)

    _, page = asked(
        client,
        q="Договор",
        kind=ContractTerms.Kind.LEASE,
        genus="income",
        counterparty=str(alpha.pk),
        ending="90-days",
        building=str(manhattan.pk),
    )

    assert 'value="Договор"' in page
    assert f'value="{alpha.pk}" selected' in page
    assert f'value="{manhattan.pk}" selected' in page
    assert f'value="{ContractTerms.Kind.LEASE}" selected' in page
    assert 'value="income" selected' in page
    assert 'value="90-days" selected' in page


def test_a_narrowed_shelf_offers_the_way_back_to_the_whole_one(client, member, portfolio):
    """«Сбросить» стоит на экране ровно тогда, когда есть что сбрасывать, — и это адрес
    без отбора, то есть сама полка."""
    client.force_login(member)

    _, page = asked(client, q="лифт")

    assert "Сбросить" in page
    assert f'href="{reverse("contracts:contract_list")}"' in page


def test_a_shelf_nobody_asked_anything_of_offers_nothing_to_clear(client, member, portfolio):
    """Отбор без единого заполненного условия не задавали, и «Сбросить» над ним предлагал
    бы отменить вопрос, которого читатель не задавал."""
    client.force_login(member)

    _, page = asked(client)

    assert "Сбросить" not in page


def test_the_bar_is_the_screens_foothold(client, member, portfolio):
    """`data-search` — договор экрана: можно ли полку сузить вообще."""
    client.force_login(member)

    _, page = asked(client)

    assert 'data-search="contracts"' in page


def test_there_is_no_bar_over_a_shelf_with_nothing_on_it(client, member):
    """Сужать нечего, и предложение сузить отвечало бы пустотой на что угодно: полосы нет
    вовсе, а не стоит недоступной."""
    client.force_login(member)

    _, page = asked(client)

    assert 'data-search="contracts"' not in page


def test_the_bar_stays_over_a_shelf_a_condition_emptied(client, member, portfolio):
    """Над полкой, которую опустошил вопрос, полоса остаётся: именно там вопрос и правят."""
    client.force_login(member)

    _, page = asked(client, q="такого договора нет")

    assert contracts_on(page) == []
    assert 'data-search="contracts"' in page
    assert "ничего не нашлось" in stated(page)


# Изоляция


def test_the_search_does_not_reach_into_another_organisations_contracts(
    client, member, portfolio, central, make_contract
):
    """Отбор умеет только убавлять строки из ответа заслона, а не добывать свои
    (ADR 0006)."""
    make_contract(central, "Договор на обслуживание лифтов чужого клиента")
    client.force_login(member)

    _, page = asked(client, q="лифт")

    assert contracts_on(page) == [str(portfolio["lifts"].pk)]
    assert "чужого клиента" not in page


def test_a_document_of_another_kind_answers_no_condition(client, member, portfolio, downtown):
    """Отбор сужает полку договоров, а не полку документов: акт не становится договором
    оттого, что его название подходит под поиск."""
    Document.objects.create(
        org=downtown, kind=Document.Kind.ACT, title="Акт о приёмке лифтов"
    )
    client.force_login(member)

    _, page = asked(client, q="лифт")

    assert contracts_on(page) == [str(portfolio["lifts"].pk)]


def test_an_unreadable_condition_does_not_show_the_whole_shelf(client, member, portfolio):
    """Отброшенное условие показало бы читателю его собственную полку целиком, заявив при
    этом отбор, которого не было (ADR 0014)."""
    client.force_login(member)

    _, page = asked(client, building="не-ключ")

    assert contracts_on(page) == []
    assert "Показано 0 из 4 договоров" in count_line(page)


def test_a_contract_of_the_second_organisation_answers_its_own_readers_condition(
    client, both_clients, portfolio, central, make_contract
):
    """Ведущему двух клиентов отбор отвечает по обоим: заслон отдаёт ему обе организации, а
    условие только убавляет из этого ответа."""
    theirs = make_contract(
        central, "Договор на обслуживание лифтов", kind=ContractTerms.Kind.OPERATION
    )
    client.force_login(both_clients)

    _, page = asked(client, q="лифт")

    assert set(contracts_on(page)) == {str(portfolio["lifts"].pk), str(theirs.pk)}


def test_the_ending_condition_speaks_about_the_readers_own_shelf_alone(
    client, member, portfolio, central, make_contract, today
):
    """Число отложенного в сторону считается по своим договорам: чужой бессрочный,
    попавший в него, назвал бы размер чужой полки."""
    make_contract(central, "Чужой бессрочный договор", is_perpetual=True)
    client.force_login(member)

    _, page = asked(client, ending="90-days")

    assert "бессрочных договоров 1" in count_line(page)
