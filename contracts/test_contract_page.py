"""Экран договора — обязательство и его срок, прочитанные по HTTP.

Шов тот же, которым проверяется полка: граница HTTP адреса `/contracts/<ключ>/`. Тесты
ходят по именованному адресу тестовым клиентом от лица сотрудника с известным членством и
проверяют наблюдаемое — что стоит в шапке, какие аренды перечислены, куда ведут ссылки и
каким кодом отвечает запрос. Ниже HTTP шва нет: заслон изоляции стоит на `Document.org`
(ADR 0006), и читают его через этот экран.

Опоры в разметке — `data-section` на блоке и `data-field` на значении шапки, те же, что на
экране Стороны и на странице документа. Это договор экрана: он говорит, какие блоки на нём
стоят и что написано в каждом поле, а перестройка вёрстки не переписывает набор тестов.

Правило рода (`contracts/genus.py`) своих тестов не имеет намеренно: его читают экраны, и
проверяет его этот — «Доходный» и «Расходный» в шапке выведены из вида и больше ниоткуда.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from documents.models import ContractTerms, Document

from .test_shelf import shelf, stated

pytestmark = pytest.mark.django_db

#: Блок экрана по имени, которым он себя называет. Читается с элемента `<section>`, а не с
#: одного атрибута: `data-section` носит ещё и пункт меню, а меню стоит на каждом экране
#: (ADR 0016), и спрошенное без элемента «какие блоки на экране» ответило бы разделами
#: приложения.
SECTION = re.compile(
    r'<section[^>]*data-section="(?P<name>[^"]+)"[^>]*>(?P<body>.*?)</section>', re.DOTALL
)

#: Значение одного поля шапки по имени поля — тот же приём, которым читает свои реквизиты
#: страница документа: у поля спрашивают текст внутри него, а не вёрстку вокруг.
FIELD = re.compile(r'data-field="(?P<name>[^"]+)"[^>]*>(?P<value>.*?)</dd>', re.DOTALL)


def page_of(client, contract):
    response = client.get(reverse("contracts:contract_detail", args=[contract.pk]))
    return response, response.content.decode()


def blocks_on(page):
    """Блоки экрана по имени, с разметкой, — для того, чего в блоке быть не должно."""
    return {block["name"]: block["body"] for block in SECTION.finditer(page)}


def sections_on(page):
    """Блоки экрана по имени: что написано в каждом из них."""
    return {name: stated(body) for name, body in blocks_on(page).items()}


def fields_on(page):
    """Что шапка говорит о каждом поле договора."""
    return {field["name"]: stated(field["value"]) for field in FIELD.finditer(page)}


@pytest.fixture
def lifts(downtown, alpha, make_contract):
    """Обычный расходный договор: заполнен весь, и по нему читается вся шапка."""
    return make_contract(
        downtown,
        "Договор на обслуживание лифтов",
        doc_no="ЭКС-2026/04",
        valid_until=date(2027, 3, 14),
        kind=ContractTerms.Kind.OPERATION,
        counterparty=alpha,
    )


# Дорога на экран


def test_a_row_of_the_shelf_opens_the_contracts_own_page(client, member, downtown, make_contract):
    """Дорога внутрь: полка называет договор, а его собственный экран отвечает, какое это
    обязательство и до каких пор."""
    contract = make_contract(downtown, "Договор на обслуживание лифтов")
    client.force_login(member)

    _, page = shelf(client)

    assert reverse("contracts:contract_detail", args=[contract.pk]) in page


# Шапка


def test_the_header_says_what_was_signed_and_until_when(client, member, lifts):
    """Название, номер, вид, род, контрагент и срок: что подписано и до каких пор, решено
    прежде, чем прочитано что-либо ещё."""
    client.force_login(member)

    response, page = page_of(client, lifts)
    fields = fields_on(page)

    assert response.status_code == 200
    assert fields["title"] == "Договор на обслуживание лифтов"
    assert fields["doc_no"] == "ЭКС-2026/04"
    assert fields["kind"] == "Эксплуатация"
    assert fields["genus"] == "Расходный"
    assert fields["counterparty"] == "ТОО «Альфа»"
    assert fields["ending"] == "14.03.2027"


def test_a_contract_nobody_filled_in_says_so_in_words_and_dashes(
    client, member, downtown, make_contract
):
    """Пачка сканов попадает на экран раньше, чем ей проставят вид (ADR 0035): вид,
    род и контрагент читаются прочерком, а срок — словами, потому что пустая клетка под
    «Кончается» значила бы и «бессрочный», и «никто не завёл» (ADR 0031)."""
    bare = make_contract(downtown, "Скан договора из пачки")
    client.force_login(member)

    _, page = page_of(client, bare)
    fields = fields_on(page)

    assert fields["doc_no"] == "— нет данных"
    assert fields["kind"] == "— нет данных"
    assert fields["genus"] == "— нет данных"
    assert fields["counterparty"] == "— нет данных"
    assert fields["ending"] == "срок не заведён"


def test_a_perpetual_contract_says_so_instead_of_a_date(client, member, downtown, make_contract):
    """Третье состояние срока: конца нет по самому соглашению, и это ответ, а не пробел."""
    perpetual = make_contract(downtown, "Договор на воду", is_perpetual=True)
    client.force_login(member)

    _, page = page_of(client, perpetual)

    assert fields_on(page)["ending"] == "бессрочный"


def test_a_contract_that_renews_itself_says_so_beside_its_term(
    client, member, downtown, make_contract
):
    """Автопролонгация — приписка к состоянию срока, а не четвёртое из них: она о том, что
    будет, когда срок кончится, и читателя незачем посылать перезаключать договор, который
    продлевается сам (ADR 0031)."""
    renewing = make_contract(
        downtown, "Договор охраны", valid_until=date(2027, 3, 14), auto_prolongs=True
    )
    client.force_login(member)

    _, page = page_of(client, renewing)

    assert fields_on(page)["ending"] == "14.03.2027 · продлевается автоматически"


# Ссылка на документ


def test_the_screen_leads_to_the_document_itself(client, member, lifts):
    """Скан, близнец и связи — одним нажатием: «что это за бумага» отвечает страница
    документа, и этот экран отправляет к ней, а не пересказывает её."""
    client.force_login(member)

    _, page = page_of(client, lifts)

    assert reverse("documents:document_detail", args=[lifts.pk]) in page


def test_the_screen_does_not_repeat_what_the_document_page_holds(client, member, lifts):
    """И не удваивает: скан и близнец выдаются с одного экрана, потому что два места, где
    их берут, — это два места, которые придётся держать в согласии."""
    client.force_login(member)

    _, page = page_of(client, lifts)

    assert reverse("documents:document_file", args=[lifts.pk]) not in page
    assert reverse("documents:document_twin", args=[lifts.pk]) not in page


# Аренды договора


@pytest.fixture
def letting(downtown, alpha, first_floor, make_space, make_lease, make_lease_contract):
    """Договор аренды с одной арендой на нём — «что входит в договор», спрошенное с его
    стороны."""
    contract = make_lease_contract(downtown, alpha, "Договор аренды №17")
    space = make_space(first_floor, "man-f1-c", "каб102", area_m2=Decimal("80.00"))
    lease = make_lease(
        space,
        alpha,
        contract=contract,
        area_m2=Decimal("64.50"),
        rate=Decimal("4500.00"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
    )
    return contract, lease


def test_a_lease_contract_lists_the_leases_it_holds(client, member, letting):
    """Помещение, БЦ, арендуемая площадь, ставка и срок: «что входит в договор» отвечено с
    его собственной стороны, а не только со стороны помещения."""
    contract, _ = letting
    client.force_login(member)

    _, page = page_of(client, contract)
    leases = sections_on(page)["leases"]

    assert "каб102" in leases
    assert "Manhattan" in leases
    assert "64,50 м²" in leases
    assert "4 500,00 за м² в месяц" in leases
    assert "с 01.01.2026 по 31.12.2026" in leases


def test_each_lease_carries_the_same_foothold_as_on_the_other_screens(client, member, letting):
    """`data-lease` — та же опора, что у строки аренды на карточке помещения и на экране
    Стороны: одна аренда, три экрана, и найти её на каждом надо одним и тем же способом."""
    contract, lease = letting
    client.force_login(member)

    _, page = page_of(client, contract)

    assert f'data-lease="{lease.pk}"' in blocks_on(page)["leases"]


def test_a_lease_contract_reads_as_income(client, member, letting):
    """Род выводится из вида и нигде не хранится: «Аренда помещений» — то, за что платят
    нам, и шапка называет это словом, которого в базе нет (ADR 0030)."""
    contract, _ = letting
    client.force_login(member)

    _, page = page_of(client, contract)

    assert fields_on(page)["genus"] == "Доходный"


def test_the_leases_are_not_totalled(
    client, member, letting, first_floor, alpha, make_space, make_lease
):
    """Итога нет ни по площади, ни по ставке: сложить арендуемые площади значит посчитать
    дважды помещение, стоящее внутри другого (ADR 0015, ADR 0019), а сложенные ставки за м²
    в месяц не значат вовсе ничего. Число, раздутое на неизвестную величину, хуже
    отсутствующего, потому что его процитируют."""
    contract, _ = letting
    make_lease(
        make_space(first_floor, "man-f1-d", "каб103"),
        alpha,
        contract=contract,
        area_m2=Decimal("35.50"),
        rate=Decimal("5500.00"),
    )
    client.force_login(member)

    _, page = page_of(client, contract)
    leases = sections_on(page)["leases"]

    assert "64,50 м²" in leases
    assert "35,50 м²" in leases
    assert "Итого" not in leases
    assert "100,00" not in leases
    assert "10 000,00" not in leases


def test_an_expense_contract_has_no_leases_block_at_all(client, member, lifts):
    """Не пустой блок, а никакого: всегда пустой раздел научил бы читателя, что у договоров
    эксплуатации бывают аренды, которых никто не завёл (ADR 0033)."""
    client.force_login(member)

    _, page = page_of(client, lifts)

    assert "leases" not in sections_on(page)


def test_a_contract_whose_kind_nobody_entered_has_no_leases_block_either(
    client, member, downtown, make_contract
):
    """Аренду на бумагу без вида не повесить — модель отвергает её теми же словами
    (ADR 0035), — и блок не обещает того, что будет отвергнуто."""
    bare = make_contract(downtown, "Скан договора из пачки")
    client.force_login(member)

    _, page = page_of(client, bare)

    assert "leases" not in sections_on(page)


def test_an_income_contract_that_lets_no_rooms_has_no_leases_block_either(
    client, member, downtown, alpha, make_contract
):
    """Блок стоит по виду, а не по роду: доп услуги — вид доходный, а аренд на нём не бывает,
    потому что клининг, проданный арендатору, помещения не сдаёт. Род, решавший это, завёл бы
    блок ровно там, где заведение аренды отвергают."""
    extras = make_contract(
        downtown,
        "Договор на уборку помещений арендатора",
        kind=ContractTerms.Kind.EXTRA_SERVICES,
        counterparty=alpha,
    )
    client.force_login(member)

    _, page = page_of(client, extras)

    assert fields_on(page)["genus"] == "Доходный"
    assert "leases" not in sections_on(page)


def test_a_lease_contract_with_no_leases_keeps_the_block_and_says_it_is_empty(
    client, member, downtown, alpha, make_lease_contract
):
    """Пустой блок у договора аренды — ответ об этом договоре, а не раздел, который не
    загрузился: аренду сюда прицепить можно, и пока никто не прицепил."""
    contract = make_lease_contract(downtown, alpha, "Договор аренды №18")
    client.force_login(member)

    _, page = page_of(client, contract)

    assert "Аренды на этот договор не заведены" in sections_on(page)["leases"]


def test_a_lease_contract_carries_two_blocks_and_names_both(client, member, letting):
    """Два блока, и ни одного лишнего: обязательство и то, что в него входит. Каждый несёт
    своё имя — опора, по которой блок находят, не разбирая вёрстки."""
    contract, _ = letting
    client.force_login(member)

    _, page = page_of(client, contract)

    assert set(sections_on(page)) == {"contract", "leases"}



# Доступ и изоляция


def test_another_organisations_contract_is_missing_rather_than_forbidden(
    client, member, central, make_contract
):
    """404, а не 403: отличив «нельзя» от «нет такого», читатель узнал бы, с кем работает
    другой клиент платформы (ADR 0006). Заслон один — организация документа, — и второго
    ему здесь не заводится."""
    theirs = make_contract(central, "Договор с чужим подрядчиком")
    client.force_login(member)

    response, _ = page_of(client, theirs)

    assert response.status_code == 404


def test_a_paper_that_is_not_a_contract_has_no_obligation_to_open(client, member, downtown):
    """У акта обязательства нет, и этот адрес отвечает о нём так же, как о чужом: экран
    обещает вид, род и срок, а показал бы одни прочерки."""
    act = Document.objects.create(
        org=downtown,
        kind=Document.Kind.ACT,
        title="Акт разграничения балансовой принадлежности",
    )
    client.force_login(member)

    response, _ = page_of(client, act)

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_login(client, downtown, make_contract):
    """Экран договора — не обход входа, которого требует каждый другой экран."""
    contract = make_contract(downtown, "Договор на обслуживание лифтов")

    response = client.get(reverse("contracts:contract_detail", args=[contract.pk]))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_a_superuser_reads_another_organisations_contract(
    client, django_user_model, central, make_contract
):
    """Суперпользователь читает за всех — то же правило, что и на каждом другом экране."""
    theirs = make_contract(central, "Договор с чужим подрядчиком")
    client.force_login(django_user_model.objects.create_superuser("root"))

    response, page = page_of(client, theirs)

    assert response.status_code == 200
    assert "Договор с чужим подрядчиком" in page


# Чего на экране нет


def test_the_screen_says_no_sum(client, member, letting):
    """Суммы договора нет нигде: денежная черта стоит там, где её держат восемь ADR."""
    contract, _ = letting
    client.force_login(member)

    _, page = page_of(client, contract)

    assert "сумма" not in stated(page).lower()


def test_the_screen_carries_no_way_to_change_anything(client, member, letting):
    """Заведения, правки и удаления этим тикетом не появляется: экран отвечает «какое
    обязательство и до каких пор», а каждая запись стоит в другом тикете."""
    contract, _ = letting
    client.force_login(member)

    _, page = page_of(client, contract)
    blocks = blocks_on(page)

    assert "<form" not in blocks["contract"]
    assert "<form" not in blocks["leases"]
    assert "Удалить" not in stated(page)


def test_the_page_carries_no_leftover_template_comments(client, member, letting):
    """Django не считает многострочный `{# … #}` комментарием и печатает его на экране."""
    contract, _ = letting
    client.force_login(member)

    _, page = page_of(client, contract)

    assert "{#" not in page
