"""Экран Стороны — то, что организация знает об одной Стороне, на одном экране.

The seam is the HTTP boundary of `/parties/<uuid>/`, the same one the полка is read at. The
tests walk the named address with the test client on behalf of a user with a known
membership and check what is observable — which блоки stand on the screen, what is written
in a строка of each, which блок is absent and what code the request answers with.

Two footholds in the markup, and both are the screen's contract:

- `data-section` on each of the five блоков — it says which блоки are on screen and what
  stands in them. Read off a `<section>` element and not off the attribute alone: a menu
  item carries `data-section` too, and that one is the раздел of the меню (ADR 0016).
- `data-field` on a value of the шапка, and `data-contact`, `data-payment`, `data-lease`
  and `data-document` on the строки of the блоки under it — mirroring the полки, whose rows
  already answer to `data-room` and `data-document`.

The адрес names the учётная карточка and not the Сторона: what the экран shows — платёжные
реквизиты, контактные лица, поводы, аренды, документы — hangs off the карточка, and a
Сторона two клиентов of one reader both know would otherwise be one адрес with two answers
(ADR 0020).
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from documents.models import Document
from parties.models import PaymentDetails

from .test_shelf import stated

pytestmark = pytest.mark.django_db

#: One блок of the screen, by the name it carries. Read off a `<section>` and not off the
#: attribute alone: `data-section` is also the меню item's contract, and the меню stands on
#: every screen — asked without the element, «какие блоки на экране» would answer with the
#: разделы of the приложение.
SECTION = re.compile(
    r'<section[^>]*data-section="(?P<name>[^"]+)"[^>]*>(?P<body>.*?)</section>', re.DOTALL
)

#: The value of one field of the шапка, by the name of the field — the same device the
#: страница документа reads its реквизиты by: what is asked of a field is the text inside
#: it and not the layout around it.
FIELD = re.compile(r'data-field="(?P<name>[^"]+)"[^>]*>(?P<value>.*?)</dd>', re.DOTALL)


def screen(client, record):
    response = client.get(reverse("parties:party_detail", args=[record.pk]))
    return response, response.content.decode()


def blocks_on(page):
    """The блоки of the screen by name, markup and all — for what a блок must not carry."""
    return {block["name"]: block["body"] for block in SECTION.finditer(page)}


def sections_on(page):
    """The блоки of the screen by name: what is written in each of them."""
    return {name: stated(body) for name, body in blocks_on(page).items()}


def fields_on(page):
    """What the шапка says about each particular of the Сторона."""
    return {field["name"]: stated(field["value"]) for field in FIELD.finditer(page)}


def rows_in(page, section, attribute):
    """The строки of one блок, top to bottom — the order is checked as well as the text."""
    return [
        stated(row["body"])
        for row in re.finditer(
            rf'<li[^>]*{attribute}="[^"]*"[^>]*>(?P<body>.*?)</li>',
            blocks_on(page)[section],
            re.DOTALL,
        )
    ]


@pytest.fixture
def page(client, member, our_record):
    """Экран карточки ТОО «Альфа», прочитанный сотрудником DownTown Management."""
    client.force_login(member)
    return screen(client, our_record)[1]


# Адрес и дорога к нему


def test_the_screen_stands_at_its_own_address(client, member, our_record):
    """`parties/<uuid>/` — организации в адресе нет, ровно как у документа нет здания."""
    client.force_login(member)

    response, _ = screen(client, our_record)

    assert reverse("parties:party_detail", args=[our_record.pk]) == f"/parties/{our_record.pk}/"
    assert response.status_code == 200


def test_a_row_of_the_shelf_leads_to_the_screen(client, member, our_record):
    """Дорога на экран одна и она с полки: полка отвечает «с кем мы имеем дело», экран —
    «а что мы о ней знаем»."""
    client.force_login(member)

    shelf = client.get(reverse("parties:party_list")).content.decode()

    assert reverse("parties:party_detail", args=[our_record.pk]) in shelf


# Шапка


def test_the_header_settles_who_this_is(
    client, member, downtown, make_party, make_record, construction
):
    """Название, БИН, юрлицо и сфера деятельности — личность улаживается прежде остального."""
    party = make_party(
        "ТОО «Центр крепежных систем»", "060340004567", line_of_business=construction
    )
    record = make_record(downtown, party)
    client.force_login(member)

    _, screened = screen(client, record)
    fields = fields_on(screened)

    assert fields["name"] == "ТОО «Центр крепежных систем»"
    assert fields["bin_iin"] == "060340004567"
    assert fields["kind"] == "Юрлицо"
    assert fields["line_of_business"] == "Строительство"


def test_a_natural_person_is_named_a_person_and_not_an_organisation(
    client, member, downtown, petrov, make_record
):
    """«Организация» на этом экране — арендатор платформы, и вторым значением она не бывает."""
    record = make_record(downtown, petrov)
    client.force_login(member)

    _, screened = screen(client, record)

    assert fields_on(screened)["kind"] == "Физлицо"


def test_a_particular_nobody_filled_in_reads_as_no_data(page):
    """Ни у одной из 699 Сторон сфера не проставлена: пустое место читалось бы как «ничем
    не занимается»."""
    assert fields_on(page)["line_of_business"] == "— нет данных"


def test_the_birthday_of_a_natural_person_stands_in_the_header(
    client, member, downtown, petrov, make_record
):
    """У физлица контактных лиц нет, и повесить личный повод не на кого — он на карточке."""
    record = make_record(downtown, petrov, born_on=date(1977, 1, 1))
    client.force_login(member)

    _, screened = screen(client, record)

    assert fields_on(screened)["born_on"] == "01.01.1977"


def test_a_legal_entity_carries_no_birthday_of_its_own(page):
    """День рождения юрлица — это дни рождения его людей, и они в блоке контактных лиц."""
    assert "born_on" not in fields_on(page)


def test_the_screen_names_the_organisation_whose_record_it_is(
    client, both_clients, downtown, central, alpha, make_record
):
    """У кого два клиента, у того две карточки одной Стороны и два одинаковых экрана."""
    ours = make_record(downtown, alpha)
    make_record(central, alpha)
    client.force_login(both_clients)

    _, screened = screen(client, ours)

    assert fields_on(screened)["org"] == "DownTown Management ТОО"


def test_a_single_client_is_not_named_on_the_screen(page):
    """Одному клиенту его собственное имя на каждом экране не сообщают."""
    assert "org" not in fields_on(page)


# Поводы


def test_the_occasions_are_read_by_the_one_rule_the_shelf_column_reads(
    client, member, downtown, make_party, make_record, make_contact, construction, make_holiday
):
    """Хранимый личный и выведенный профессиональный — одним списком, ближайшим вперёд, тем
    же `occasions_of`, каким полка считает свою колонку."""
    make_holiday(construction, "День строителя", month=8, week_of_month=2, weekday=7)
    party = make_party("ТОО «Стройка»", "060340004568", line_of_business=construction)
    record = make_record(downtown, party)
    make_contact(record, "Иванов Иван", born_on=date(1980, 3, 14))
    client.force_login(member)

    _, screened = screen(client, record)
    occasions = fields_on(screened)["occasions"]

    assert "День строителя" in occasions
    assert "День рождения — Иванов Иван" in occasions


def test_a_party_with_nothing_to_congratulate_says_so(page):
    """637 из 699 Сторон — поставщики, которым дня рождения никто не заводил."""
    assert fields_on(page)["occasions"] == "—"


# Платёжные реквизиты


def test_the_payment_details_are_listed_with_the_primary_first(
    client, member, our_record, kaspi
):
    """Обычный случай отвечается, ничего не разворачивая, — потому основной наверху."""
    PaymentDetails.objects.create(
        record=our_record, bank=kaspi, account="KZ999999999999999999", kbe="19"
    )
    PaymentDetails.objects.create(
        record=our_record, bank=kaspi, account="KZ111111111111111111", kbe="17", is_primary=True
    )
    client.force_login(member)

    _, screened = screen(client, our_record)
    rows = rows_in(screened, "payment", "data-payment")

    assert len(rows) == 2
    assert "KZ111111111111111111" in rows[0]
    assert "KZ999999999999999999" in rows[1]


def test_the_payment_details_name_the_bank_the_account_and_the_kbe(
    client, member, our_record, kaspi
):
    """Куда платить: банк из справочника вместе с его БИК, счёт и КБе."""
    PaymentDetails.objects.create(
        record=our_record, bank=kaspi, account="KZ111111111111111111", kbe="17", is_primary=True
    )
    client.force_login(member)

    _, screened = screen(client, our_record)
    payment = rows_in(screened, "payment", "data-payment")[0]

    assert "Kaspi Bank" in payment
    assert "CASPKZKA" in payment
    assert "KZ111111111111111111" in payment
    assert "17" in payment


def test_a_record_with_no_payment_details_says_so_rather_than_showing_an_empty_block(page):
    """«Не заведено» и «не бывает» — разные ответы, и блок говорит первый из них."""
    assert rows_in(page, "payment", "data-payment") == []
    assert "не заведены" in sections_on(page)["payment"]


# Контактные лица


def test_a_contact_person_is_listed_with_everything_known_about_them(
    client, member, our_record, make_contact
):
    """«Кому звонить» и «кого поздравить» — один список."""
    make_contact(
        our_record,
        "Иванов Иван",
        position="главный инженер",
        phone="+7 701 000 00 00",
        email="ivanov@alpha.kz",
        born_on=date(1980, 3, 14),
    )
    client.force_login(member)

    _, screened = screen(client, our_record)
    contact = rows_in(screened, "contacts", "data-contact")[0]

    assert "Иванов Иван" in contact
    assert "главный инженер" in contact
    assert "+7 701 000 00 00" in contact
    assert "ivanov@alpha.kz" in contact
    assert "14.03.1980" in contact


def test_a_natural_person_has_no_block_of_contact_persons_at_all(
    client, member, downtown, petrov, make_record
):
    """Физлицо не делают своим же представителем."""
    record = make_record(downtown, petrov)
    client.force_login(member)

    _, screened = screen(client, record)

    assert "contacts" not in sections_on(screened)


# Аренды


def test_the_leases_of_the_party_are_listed_from_her_side(
    client, member, downtown, alpha, make_record, first_floor, make_space, make_lease
):
    """«Где сидит ТОО «Альфа»» отвечается с её стороны отношения: помещение, БЦ, метры, срок."""
    record = make_record(downtown, alpha)
    room = make_space(first_floor, "man-f1-c", "каб102", area_m2=Decimal("40.00"))
    make_lease(
        room,
        alpha,
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        area_m2=Decimal("20.00"),
    )
    client.force_login(member)

    _, screened = screen(client, record)
    lease = rows_in(screened, "leases", "data-lease")[0]

    assert "каб102" in lease
    assert "Manhattan" in lease
    assert "20 м²" in lease
    assert "с 01.01.2026 по 31.12.2026" in lease


def test_the_leases_are_not_totalled(
    client, member, downtown, alpha, make_record, first_floor, make_space, make_lease
):
    """Число, раздутое вложенными помещениями, не цитируется никогда (ADR 0019)."""
    record = make_record(downtown, alpha)
    entrance = make_space(first_floor, "man-f1-d", "каб103вход", area_m2=Decimal("60.00"))
    inner = make_space(entrance, "man-f1-d1", "каб103", area_m2=Decimal("30.00"))
    make_lease(entrance, alpha, area_m2=Decimal("60.00"))
    make_lease(inner, alpha, area_m2=Decimal("30.00"))
    client.force_login(member)

    _, screened = screen(client, record)
    leases = sections_on(screened)["leases"]

    assert len(rows_in(screened, "leases", "data-lease")) == 2
    assert "Итого" not in leases
    assert "Всего" not in leases
    assert "90" not in leases


def test_another_clients_lease_of_the_same_party_stays_off_the_screen(
    client,
    both_clients,
    downtown,
    central,
    alpha,
    make_record,
    first_floor,
    make_space,
    make_lease,
    make_building,
):
    """Сторона общая, её аренды — нет: кто видит помещение, тот видит его аренды (ADR 0018)."""
    ours = make_record(downtown, alpha)
    make_record(central, alpha)
    theirs = make_building(central, "brk", "Brooklyn")
    make_lease(make_space(first_floor, "man-f1-e", "каб104"), alpha)
    make_lease(make_space(theirs, "brk-r1", "каб201"), alpha)
    client.force_login(both_clients)

    _, screened = screen(client, ours)
    leases = sections_on(screened)["leases"]

    assert "каб104" in leases
    assert "каб201" not in leases


# Документы


def test_the_documents_she_issued_are_reachable_from_her(
    client, member, downtown, alpha, make_record
):
    """Бумажный след достижим от Стороны: документы, где она стоит «Кем выдан»."""
    record = make_record(downtown, alpha)
    document = Document.objects.create(
        org=downtown, kind=Document.Kind.ACT, title="Акт разграничения", issuer_party=alpha
    )
    Document.objects.create(org=downtown, kind=Document.Kind.ACT, title="Чужой акт")
    client.force_login(member)

    _, screened = screen(client, record)
    documents = sections_on(screened)["issued"]

    assert "Акт разграничения" in documents
    assert "Чужой акт" not in documents
    assert reverse("documents:document_detail", args=[document.pk]) in screened


def test_another_clients_document_naming_the_same_party_stays_off_the_screen(
    client, both_clients, downtown, central, alpha, make_record
):
    """Документ виден по своей организации, и карточка показывает только свою (ADR 0006)."""
    ours = make_record(downtown, alpha)
    make_record(central, alpha)
    Document.objects.create(
        org=downtown, kind=Document.Kind.ACT, title="Наш акт", issuer_party=alpha
    )
    Document.objects.create(
        org=central, kind=Document.Kind.ACT, title="Чужой акт", issuer_party=alpha
    )
    client.force_login(both_clients)

    _, screened = screen(client, ours)
    documents = sections_on(screened)["issued"]

    assert "Наш акт" in documents
    assert "Чужой акт" not in documents


# Пять блоков, и ни одного лишнего


def test_the_screen_carries_the_five_blocks(page):
    """Пять блоков и ни одного лишнего — и каждый несёт своё имя."""
    assert set(sections_on(page)) == {"party", "payment", "contacts", "leases", "issued"}


def test_there_is_no_block_of_roles_at_all(page):
    """`PartyRole` держит ноль строк и не имеет читателя: всегда пустой блок учил бы
    читателя, что у Сторон нет ролей."""
    assert "Роли" not in page
    assert "roles" not in sections_on(page)


def test_the_screen_carries_no_way_to_change_anything(page):
    """Створок заведения, правки и удаления этим тикетом не появляется."""
    blocks = " ".join(blocks_on(page).values())

    assert "Завести" not in blocks
    assert "Редактировать" not in blocks
    assert "Удалить" not in blocks
    assert "<form" not in blocks
    assert "<button" not in blocks


def test_the_page_carries_no_leftover_template_comments(page):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on screen."""
    assert "{#" not in page


# Доступ и изоляция


def test_a_party_without_a_record_of_mine_is_missing_rather_than_forbidden(
    client, member, central, alpha, make_record
):
    """Отсутствие чужих данных должно быть неотличимо от отсутствия (ADR 0006)."""
    theirs = make_record(central, alpha)
    client.force_login(member)

    response, _ = screen(client, theirs)

    assert response.status_code == 404


def test_a_party_nobody_keeps_a_record_on_has_no_screen(client, member, make_party):
    """62 Стороны из чужих баз остаются в реестре и ни на чей экран не попадают."""
    stranger = make_party("Asset-Asia ТОО", "990140001234")
    client.force_login(member)

    response = client.get(reverse("parties:party_detail", args=[stranger.pk]))

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, our_record):
    """До входа не показывают ничего — в том числе и того, что карточка существует."""
    response = client.get(reverse("parties:party_detail", args=[our_record.pk]))

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")
