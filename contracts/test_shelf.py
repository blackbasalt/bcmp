"""Полка договоров — что сотрудник УК видит по HTTP.

Шов один: граница HTTP адреса `/contracts/`. Тесты ходят по именованному адресу тестовым
клиентом от лица сотрудника с известным членством и проверяют наблюдаемое — какие договоры
на экране, в каком порядке, что написано в строке, что говорит строка счёта и каким кодом
отвечает запрос. Ниже HTTP шва нет: заслон изоляции стоит на `Document.org` (ADR 0006), и
проверяется он через этот экран, потому что так его и читают.

Опора в разметке — `data-contract` на строке таблицы, наравне с `data-room` на полке
помещений, `data-document` на полке документов и `data-party` на полке Сторон. Это договор
экрана: он показывает, какие договоры выведены и в каком порядке, а перестройка вёрстки не
переписывает набор тестов.

Правило рода (`contracts/genus.py`) своих тестов не имеет намеренно — его читают экраны, и
экраны его проверяют. На этой полке род не напечатан ни в одной колонке, поэтому читает его
пока экран договора, а не этот.
"""

import re
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from documents.models import ContractTerms, Document

pytestmark = pytest.mark.django_db

#: Во сколько запросов обходится полка, сколько бы строк на ней ни стояло: читатель, его
#: организации, сами строки и счёт всей полки. Числом, а не потолком: потолок с запасом
#: пропустил бы запрос на договор ровно до того дня, когда договоров станет достаточно,
#: чтобы это стало видно на экране.
QUERIES_PER_SHELF = 4

#: Строка таблицы вместе с ключом договора: договор экрана и всё, что в строке написано.
#: Читается не разбором тегов — у строки спрашивают не устройство, а текст, и текст этот
#: обязан найтись в самой строке, а не где-нибудь на странице.
ROW = re.compile(r'<tr[^>]*data-contract="(?P<key>[^"]+)"[^>]*>(?P<cells>.*?)</tr>', re.DOTALL)

#: Ячейки одной строки в том порядке, в каком они в ней стоят, — для вопросов об отдельной
#: колонке, где текст строки целиком не отличит «Номер» от «Кончается».
CELL = re.compile(r"<t[dh][^>]*>(?P<text>.*?)</t[dh]>", re.DOTALL)


def stated(text):
    """Текст в одну строку: фраза не должна ломаться о перенос в разметке."""
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def contracts_on(page):
    """Ключи показанных договоров сверху вниз — порядок строк проверяется тоже."""
    return [row["key"] for row in ROW.finditer(page)]


def rows_on(page):
    """Строки таблицы по ключу договора: что написано в каждой."""
    return {row["key"]: stated(row["cells"]) for row in ROW.finditer(page)}


def cells_on(page):
    """Те же строки по ячейкам: ключ → список ячеек, как они стоят."""
    return {
        row["key"]: [stated(cell["text"]) for cell in CELL.finditer(row["cells"])]
        for row in ROW.finditer(page)
    }


def headings_on(page):
    """Заголовки колонок слева направо — то, с чем сверяются ячейки строки."""
    head = re.search(r"<thead>(.*?)</thead>", page, re.DOTALL)
    return [stated(cell["text"]) for cell in CELL.finditer(head.group(1))] if head else []


def cell_under(page, contract, heading):
    """Что одна колонка говорит об одном договоре — найденная по заголовку, а не по месту.

    Колонка, вставленная перед другой, не должна превращать утверждение о «Кончается» в
    вопрос о контрагенте.
    """
    return cells_on(page)[str(contract.pk)][headings_on(page).index(heading)]


def ending_cell(page, contract):
    """Что колонка «Кончается» говорит об одном договоре."""
    return cell_under(page, contract, "Кончается")


def row_markup(page, contract):
    """Одна строка как она есть, с тегами, — для того, чего в строке быть не должно."""
    return next(row["cells"] for row in ROW.finditer(page) if row["key"] == str(contract.pk))


def count_line(page):
    """Строка, говорящая, сколько полки на экране.

    Ищется по `data-count` — договору экрана о ней, — а не по классам, которые она носит:
    она стоит под таблицей на полке со строками и под предупреждением на полке, которую
    опустошил отбор, и это одна и та же строка.
    """
    found = re.search(r'data-count="contracts"[^>]*>(.*?)</p>', page, re.DOTALL)
    return stated(found.group(1)) if found else ""


def links_on(page, wording):
    """Адрес, на который ведёт число-находка, названная этими словами."""
    line = re.search(r'data-count="contracts"[^>]*>(.*?)</p>', page, re.DOTALL).group(1)
    found = re.search(rf'{wording}\s*<a[^>]*href="([^"]+)"', " ".join(line.split()))
    return found.group(1) if found else None


def shelf(client, **asked):
    response = client.get(reverse("contracts:contract_list"), asked)
    return response, response.content.decode()


@pytest.fixture
def our_contracts(downtown, alpha, make_contract):
    """Два договора DownTown Management — обычная полка: заполненный и пустой.

    Пустой здесь не для порядка: сорок сканов попадают на полку раньше, чем кому-нибудь
    проставят вид (ADR 0035), и полка, которую видно только заполненной, молчала бы ровно о
    них.
    """
    filled = make_contract(
        downtown,
        "Договор на обслуживание лифтов",
        doc_no="ЭКС-2026/04",
        valid_until=date(2027, 3, 14),
        kind=ContractTerms.Kind.OPERATION,
        counterparty=alpha,
    )
    bare = make_contract(downtown, "Скан договора из пачки")
    return filled, bare


@pytest.fixture
def shelf_page(client, member, our_contracts):
    client.force_login(member)
    _, page = shelf(client)
    return page


# Доступ и изоляция


def test_a_contract_of_another_organisation_stays_off_the_shelf(
    client, member, central, our_contracts, make_contract
):
    """Изоляция на экране — тот же заслон, которым живёт полка документов: организация
    документа и ничто другое (ADR 0006). Второму заслону здесь неоткуда взяться, потому
    что второго его и нет."""
    theirs = make_contract(central, "Договор с чужим подрядчиком")
    client.force_login(member)

    response, page = shelf(client)

    assert response.status_code == 200
    assert str(theirs.pk) not in contracts_on(page)
    assert "чужим подрядчиком" not in page


def test_an_anonymous_visitor_is_sent_to_login(client, our_contracts):
    """Полка — не обход входа, которого требует каждый другой экран."""
    response = client.get(reverse("contracts:contract_list"))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_a_superuser_reads_every_organisations_contracts(
    client, django_user_model, central, our_contracts, make_contract
):
    """Суперпользователь читает за всех — то же правило, что и на каждом другом экране."""
    make_contract(central, "Договор с чужим подрядчиком")
    client.force_login(django_user_model.objects.create_superuser("root"))

    _, page = shelf(client)

    assert "Договор на обслуживание лифтов" in page
    assert "чужим подрядчиком" in page


# Что стоит на полке


def test_the_shelf_holds_the_contracts_of_the_reader(shelf_page, our_contracts):
    """Экран начинается с того, что говорит, сколько всего есть: отбора нет, полка вся."""
    assert len(contracts_on(shelf_page)) == 2


def test_a_document_of_another_kind_is_not_a_contract(client, member, downtown, our_contracts):
    """Полка держит документы вида «Договор» и никакие другие: акт разграничения — бумага
    того же раздела документов, но не обязательство."""
    Document.objects.create(
        org=downtown,
        kind=Document.Kind.ACT,
        title="Акт разграничения балансовой принадлежности",
    )
    client.force_login(member)

    _, page = shelf(client)

    assert len(contracts_on(page)) == 2
    assert "Акт разграничения" not in page


def test_a_contract_whose_terms_nobody_filled_is_on_the_shelf(shelf_page, our_contracts):
    """Пачка сканов, которую никто не разобрал, стоит на полке и считается на ней: полка
    заведена ради того, чтобы не потерять обязательство, и молчать о сорока сканах ей
    нечем (ADR 0035)."""
    _, bare = our_contracts

    assert str(bare.pk) in contracts_on(shelf_page)


def test_the_rows_are_ordered_by_name(client, member, downtown, our_contracts, make_contract):
    """Полку читают глазами, ища на ней договор, и помогает тут алфавит: порядок, в котором
    пачка сканов легла в хранилище, не помогает никому. Строки ставятся вразнобой нарочно,
    чтобы утверждение было о порядке экрана, а не о порядке заведения."""
    filled, bare = our_contracts
    first = make_contract(downtown, "Договор аренды №17")
    client.force_login(member)

    _, page = shelf(client)

    assert contracts_on(page) == [str(first.pk), str(filled.pk), str(bare.pk)]


# Что говорит строка


def test_a_row_says_what_is_needed_to_judge_a_contract_without_opening_it(
    shelf_page, our_contracts, alpha
):
    """Название, номер, вид, контрагент и «Кончается» — всё в строке: полка отвечает, не
    открывая ничего."""
    filled, _ = our_contracts
    row = rows_on(shelf_page)[str(filled.pk)]

    assert "Договор на обслуживание лифтов" in row
    assert "ЭКС-2026/04" in row
    assert "Эксплуатация" in row
    assert "ТОО «Альфа»" in row
    assert "14.03.2027" in row


def test_a_contract_with_no_kind_shows_a_dash(shelf_page, our_contracts):
    """Вид может пустовать, и это обычное состояние (ADR 0035), а не «вид, которого не
    бывает»: прочерк ставит `or_missing`, одним правилом на весь проект."""
    _, bare = our_contracts

    assert cell_under(shelf_page, bare, "Вид") == "— нет данных"


def test_a_contract_with_no_counterparty_shows_a_dash(shelf_page, our_contracts):
    """Контрагент — своё поле, и незаполненное оно пробел, а не ответ: договор подписан
    двумя, и вторая сторона у него есть всегда, даже когда её не завели."""
    _, bare = our_contracts

    assert cell_under(shelf_page, bare, "Контрагент") == "— нет данных"


def test_the_counterparty_is_not_read_off_the_issuer(
    client, member, downtown, make_contract, alpha
):
    """«Кем выдан» про договор не значит ничего: договор не выдают, его подписывают двое.
    Контрагент берётся со своего поля, и `issuer_party`, заполненный по недосмотру,
    контрагентом не притворяется."""
    contract = make_contract(downtown, "Договор поставки", issuer_party=alpha)
    client.force_login(member)

    _, page = shelf(client)

    assert cell_under(page, contract, "Контрагент") == "— нет данных"


# «Кончается» в трёх состояниях


def test_an_ending_date_is_said_as_a_date(shelf_page, our_contracts):
    """Первое из трёх состояний: срок до числа — и число написано."""
    filled, _ = our_contracts

    assert ending_cell(shelf_page, filled) == "14.03.2027"


def test_a_perpetual_contract_says_so(client, member, downtown, make_contract):
    """Второе состояние: конца срока нет по самому соглашению — и строка говорит это
    словом, а не пустой клеткой (ADR 0031)."""
    contract = make_contract(
        downtown, "Договор поставки расходных материалов", is_perpetual=True
    )
    client.force_login(member)

    _, page = shelf(client)

    assert ending_cell(page, contract) == "бессрочный"


def test_a_contract_with_no_term_says_the_term_is_unrecorded(shelf_page, our_contracts):
    """Третье состояние, и ради него заведены первые два: одна пустота на два смысла тихо
    спрятала бы договор, истекающий через месяц (ADR 0031)."""
    _, bare = our_contracts

    assert ending_cell(shelf_page, bare) == "срок не заведён"


def test_a_stated_date_outweighs_a_perpetuity_flag(client, member, downtown, make_contract):
    """Два условия, спорящие между собой, разрешаются в пользу даты: «бессрочный» над
    заведённым концом срока спрятал бы ровно тот договор, ради которого полка и стоит."""
    contract = make_contract(
        downtown, "Договор охраны", is_perpetual=True, valid_until=date(2026, 10, 1)
    )
    client.force_login(member)

    _, page = shelf(client)

    assert ending_cell(page, contract) == "01.10.2026"


def test_an_auto_prolonging_contract_stays_on_the_shelf_and_says_so(
    client, member, downtown, make_contract
):
    """Автопролонгация меняет то, что строка говорит, а не то, попадает ли она на полку:
    убрать такой договор значило бы спрятать обязательство, показать молча — поднять
    ложную тревогу (ADR 0031)."""
    contract = make_contract(
        downtown,
        "Договор на охрану объектов",
        valid_until=date(2026, 9, 30),
        auto_prolongs=True,
    )
    client.force_login(member)

    _, page = shelf(client)

    assert str(contract.pk) in contracts_on(page)
    assert "продлевается автоматически" in ending_cell(page, contract)
    assert "30.09.2026" in ending_cell(page, contract)


# Строка счёта


def test_the_count_says_how_much_of_the_shelf_is_on_screen(shelf_page):
    """Вопрос, который задают первым, отвечен фразой, а не длиной списка."""
    assert "Показано 2 из 2 договоров" in count_line(shelf_page)


def test_the_count_agrees_with_the_numeral(client, member, downtown, make_contract):
    """«из 1 договора», а не «из 1 договоров»: «из» правит родительным падежом, и форм
    здесь две, а не три, которых потребовал бы именительный."""
    make_contract(
        downtown,
        "Договор аренды №17",
        kind=ContractTerms.Kind.LEASE,
        valid_until=date(2027, 1, 1),
    )
    client.force_login(member)

    _, page = shelf(client)

    assert count_line(page) == "Показано 1 из 1 договора"


def test_the_count_line_names_both_findings(shelf_page):
    """Пачка сканов, которую никто не разобрал, — это число, а не молчание."""
    assert "вид не заведён у 1" in count_line(shelf_page)
    assert "срок не заведён у 1" in count_line(shelf_page)


def test_each_finding_is_a_link_that_narrows_the_shelf_to_it(client, member, our_contracts):
    """Пробел в данных находится с той же полки, одним нажатием: число — ссылка, и ведёт
    она к работе, а не сообщает о ней."""
    _, bare = our_contracts
    client.force_login(member)

    _, page = shelf(client)
    without_kind = links_on(page, "вид не заведён у")
    without_term = links_on(page, "срок не заведён у")

    assert contracts_on(client.get(without_kind).content.decode()) == [str(bare.pk)]
    assert contracts_on(client.get(without_term).content.decode()) == [str(bare.pk)]


def test_a_finding_is_counted_over_what_is_on_screen(
    client, member, downtown, our_contracts, make_contract
):
    """Число о всей полке под суженной таблицей противоречило бы таблице над собой."""
    make_contract(downtown, "Ещё один скан")
    client.force_login(member)

    _, page = shelf(client, no_kind="1")

    assert "Показано 2 из 3 договоров" in count_line(page)
    assert "вид не заведён у 2" in count_line(page)


def test_a_finding_with_nothing_to_find_is_not_said(client, member, downtown, make_contract):
    """«вид не заведён у 0» — строка ни о чём, и ссылка её вела бы на пустую полку."""
    make_contract(
        downtown,
        "Договор аренды №17",
        kind=ContractTerms.Kind.LEASE,
        valid_until=date(2027, 1, 1),
    )
    client.force_login(member)

    _, page = shelf(client)

    assert "вид не заведён" not in count_line(page)
    assert "срок не заведён" not in count_line(page)


def test_a_perpetual_contract_is_no_gap_in_the_record(client, member, downtown, make_contract):
    """Бессрочный договор — это ответ, а не пробел: считать его в «срок не заведён»
    значило бы послать чинить то, что никогда не было проблемой (ADR 0031)."""
    make_contract(
        downtown, "Договор поставки", is_perpetual=True, kind=ContractTerms.Kind.SUPPLY
    )
    client.force_login(member)

    _, page = shelf(client)

    assert "срок не заведён" not in count_line(page)


# Пустые экраны


def test_a_shelf_with_no_contracts_says_who_enters_them(client, member):
    """Организация без единого договора читает «Договоры не заведены», а не «ничего не
    нашлось»: читателя не посылают чинить вопрос, который никогда не был проблемой."""
    client.force_login(member)

    _, page = shelf(client)

    assert contracts_on(page) == []
    assert "Договоры не заведены" in stated(page)
    assert "администратор организации" in stated(page)


def test_a_shelf_with_no_contracts_says_so_even_with_a_condition_in_the_address(client, member):
    """Какой из двух пустых экранов показан, решает размер несуженной полки, а не то,
    спрашивали ли что-нибудь: находить тут нечего, что у полки ни спроси."""
    client.force_login(member)

    _, page = shelf(client, no_kind="1")

    assert "Договоры не заведены" in stated(page)
    assert "ничего не нашлось" not in stated(page)


def test_a_shelf_a_condition_emptied_says_so(client, member, downtown, make_contract):
    """«ничего не нашлось» отправляет читателя изменить вопрос, «Договоры не заведены» —
    к тому, кто их заводит, и один экран на оба посылал бы не туда через раз."""
    make_contract(
        downtown,
        "Договор аренды №17",
        kind=ContractTerms.Kind.LEASE,
        valid_until=date(2027, 1, 1),
    )
    client.force_login(member)

    _, page = shelf(client, no_kind="1")

    assert contracts_on(page) == []
    assert "ничего не нашлось" in stated(page)
    assert "Показано 0 из 1 договора" in count_line(page)


# Колонка организации


def test_a_member_of_two_organisations_sees_each_contract_under_its_own_organisation(
    client, both_clients, downtown, central, make_contract
):
    """Ведущему двух клиентов полка общая, и «чей это договор» он спрашивает о каждой
    строке — тот же вопрос, что задают полка документов, помещений и Сторон."""
    ours = make_contract(downtown, "Договор на обслуживание лифтов")
    theirs = make_contract(central, "Договор на вывоз мусора")
    client.force_login(both_clients)

    _, page = shelf(client)

    assert cell_under(page, ours, "Организация") == "DownTown Management ТОО"
    assert cell_under(page, theirs, "Организация") == "Central City Properties ТОО"


def test_a_member_of_one_organisation_gets_no_organisation_column(shelf_page):
    """Ведущему одного клиента колонка повторяла бы одно имя на всю таблицу."""
    assert "Организация" not in headings_on(shelf_page)


# Устройство экрана


def test_the_shelf_costs_no_query_per_row(
    client, member, downtown, make_contract, alpha
):
    """Условия и контрагент едут в том же запросе, что и строки: спрошенные построчно, они
    были бы двумя запросами на договор при сотнях договоров."""
    for number in range(10):
        make_contract(
            downtown,
            f"Договор №{number}",
            kind=ContractTerms.Kind.SUPPLY,
            counterparty=alpha,
            valid_until=date(2027, 1, 1),
        )
    client.force_login(member)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("contracts:contract_list"))
        assert len(contracts_on(response.content.decode())) == 10

    assert len(queries) == QUERIES_PER_SHELF


def test_the_shelf_is_rendered_whole_with_no_pagination(
    client, member, downtown, make_contract
):
    """Поиск самого браузера обязан работать по всем строкам, а ссылка, отправленная
    коллеге, — ничего не терять."""
    for number in range(30):
        make_contract(downtown, f"Договор №{number:02d}")
    client.force_login(member)

    _, page = shelf(client)

    assert len(contracts_on(page)) == 30
    assert "?page=" not in page


def test_the_shelf_carries_no_way_to_change_anything(shelf_page, our_contracts):
    """Створок заведения, правки и удаления этим тикетом не появляется: полка отвечает
    «что подписано и до каких пор», а каждая запись стоит в другом месте."""
    filled, _ = our_contracts

    assert "Завести" not in shelf_page
    assert "Удалить" not in shelf_page
    assert "<form" not in row_markup(shelf_page, filled)
    assert "<button" not in row_markup(shelf_page, filled)


def test_the_shelf_says_no_sum(shelf_page):
    """Суммы договора нет нигде: денежная черта стоит там, где её держат восемь ADR."""
    assert "сумма" not in stated(shelf_page).lower()



def test_the_page_carries_no_leftover_template_comments(shelf_page):
    """Django не считает многострочный `{# … #}` комментарием и печатает его на экране."""
    assert "{#" not in shelf_page
