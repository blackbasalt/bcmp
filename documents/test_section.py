"""Раздел «Документы» — то, что сотрудник УК видит по HTTP.

Шов один: граница HTTP. Тесты ходят тестовым клиентом по именованным адресам от
имени пользователя с известным членством и проверяют наблюдаемое — какие документы
на экране, что о них написано и каким кодом отвечает запрос. Ниже HTTP шва нет:
чокпоинт видимости проверяется тем же экраном, потому что через него он и читается.

Опора в разметке — атрибут `data-document` на строке таблицы. Это договор экрана:
по нему видно, какие документы показаны и в каком порядке, и перестройка вёрстки
не переписывает набор тестов.
"""

import re
from datetime import date

import pytest
from django.urls import reverse

from documents.models import Document
from parties.models import OrgMembership, Party

pytestmark = pytest.mark.django_db

#: Строка таблицы вместе с ключом документа: договор экрана и всё, что в строке
#: написано. Разбором по тегам это не читается — спрашивают у строки не структуру,
#: а текст, и найтись он должен именно в ней, а не где-то на странице.
ROW = re.compile(r'<tr[^>]*data-document="(?P<key>[^"]+)"[^>]*>(?P<cells>.*?)</tr>', re.DOTALL)


def stated(text):
    """Текст одной строкой: фраза не должна ломаться о перенос в разметке."""
    return " ".join(text.split())


def rows_on(page):
    """Строки таблицы по ключу документа: что написано в каждой из них."""
    return {row["key"]: stated(re.sub(r"<[^>]+>", " ", row["cells"])) for row in ROW.finditer(page)}


def documents_on(page):
    """Ключи показанных документов сверху вниз — порядок строк тоже проверяется."""
    return [row["key"] for row in ROW.finditer(page)]


def section(client):
    response = client.get(reverse("documents:document_list"))
    return response, response.content.decode()


def make_document(org, title, **fields):
    """Документ организации. Всё, кроме вида и названия, необязательно — как в жизни."""
    fields.setdefault("kind", Document.Kind.ACT)
    return Document.objects.create(org=org, title=title, **fields)


@pytest.fixture
def issuer(db):
    """Сторона, выдавшая документ, — она же «кем выдан» в строке таблицы."""
    return Party.objects.create(kind=Party.Kind.COMPANY, name="ТОО Промэнерго")


@pytest.fixture
def both_clients(django_user_model, downtown, central):
    """Сотрудник, ведущий двух клиентов сразу: их документы не должны смешаться."""
    user = django_user_model.objects.create_user("manager")
    OrgMembership.objects.create(user=user, org=downtown)
    OrgMembership.objects.create(user=user, org=central)
    return user


# Доступ и изоляция


def test_a_member_sees_the_documents_of_their_own_organisation_only(
    client, member, downtown, central
):
    """Изоляция клиентов на экране — ровно то, ради чего у документа свой чокпоинт."""
    make_document(downtown, "Акт разграничения балансовой принадлежности")
    make_document(central, "Договор с чужим подрядчиком")
    client.force_login(member)

    response, page = section(client)

    assert response.status_code == 200
    assert "Акт разграничения балансовой принадлежности" in page
    assert "Договор с чужим подрядчиком" not in page


def test_a_member_of_two_organisations_sees_each_organisation_under_its_own_name(
    client, both_clients, downtown, central
):
    """Два клиента у одного сотрудника — две полки, а не одна общая куча.

    Названо это должно быть в самой строке: имена обеих организаций где-то на
    странице ничего не различают — они сошлись бы и перепутанными местами.
    """
    ours = make_document(downtown, "Акт разграничения")
    theirs = make_document(central, "Акт допуска")
    client.force_login(both_clients)

    _, page = section(client)
    rows = rows_on(page)

    assert downtown.name in rows[str(ours.pk)]
    assert central.name not in rows[str(ours.pk)]
    assert central.name in rows[str(theirs.pk)]
    assert downtown.name not in rows[str(theirs.pk)]


def test_the_organisation_is_named_even_when_the_second_client_has_nothing_yet(
    client, both_clients, downtown
):
    """Подпись держится за читателя, а не за данные.

    Пропасть она должна была бы ровно тогда, когда у второго клиента документов ещё
    нет, — то есть когда ведущему двоих особенно нужно знать, чья это полка.
    """
    ours = make_document(downtown, "Акт разграничения")
    client.force_login(both_clients)

    _, page = section(client)

    assert downtown.name in rows_on(page)[str(ours.pk)]


def test_a_reader_of_one_client_is_not_told_the_same_name_in_every_row(
    client, member, downtown
):
    """Колонка, повторяющая одно имя во всю таблицу, не различает ничего."""
    ours = make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = section(client)

    assert downtown.name not in rows_on(page)[str(ours.pk)]


def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, downtown):
    """До входа не показывается ничего — даже пустая полка."""
    make_document(downtown, "Акт разграничения")

    response = client.get(reverse("documents:document_list"))

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


# Таблица


def test_a_row_shows_what_tells_the_documents_apart(client, member, downtown, issuer):
    """Вид, название, номер, дата выдачи и кем выдан — прямо в строке."""
    make_document(
        downtown,
        "Акт разграничения балансовой принадлежности",
        kind=Document.Kind.ACT,
        doc_no="АКТ-12/2024",
        issued_at=date(2024, 3, 14),
        issuer_party=issuer,
    )
    client.force_login(member)

    _, page = section(client)
    (row,) = rows_on(page).values()

    assert "Акт" in row
    assert "Акт разграничения балансовой принадлежности" in row
    assert "АКТ-12/2024" in row
    assert "14.03.2024" in row
    assert "ТОО Промэнерго" in row


def test_a_field_nobody_filled_in_reads_as_no_data(client, member, downtown):
    """Пустое место в строке можно прочитать как ноль; «— нет данных» — нельзя."""
    make_document(downtown, "Акт без реквизитов")
    client.force_login(member)

    _, page = section(client)
    (row,) = rows_on(page).values()

    assert row.count("— нет данных") == 3  # номер, дата выдачи и кем выдан


def test_the_newest_uploads_are_at_the_top(client, member, downtown):
    """Порядок — по загрузке: пакет, который только что перенесли, лежит сверху.

    Дата выдачи порядка не задаёт: акт 2019 года, загруженный сегодня, ищут там же,
    где и остальной сегодняшний пакет, а не в хвосте списка.
    """
    older = make_document(downtown, "Загружен первым", issued_at=date(2024, 3, 14))
    newer = make_document(downtown, "Загружен вторым", issued_at=date(2019, 1, 9))
    client.force_login(member)

    _, page = section(client)

    assert documents_on(page) == [str(newer.pk), str(older.pk)]


def test_the_section_states_how_many_documents_it_shows(client, member, downtown):
    """Число на экране словами: «сколько всего» — вопрос, который задают первым."""
    for number in range(3):
        make_document(downtown, f"Акт {number}")
    client.force_login(member)

    _, page = section(client)

    assert "Показано 3\u00a0документа" in page  # число и слово не разъезжаются


def test_a_single_document_is_counted_in_the_singular(client, member, downtown):
    """«Показано 1 документов» читается сбоем экрана, а не единственным документом."""
    make_document(downtown, "Единственный акт")
    client.force_login(member)

    _, page = section(client)

    assert "Показан 1\u00a0документ" in page


def test_eleven_documents_are_counted_by_the_tens_rather_than_by_the_last_digit(
    client, member, downtown
):
    """Одиннадцать — не «одиннадцать документ»: вторая цифра числа отменяет первую."""
    for number in range(11):
        make_document(downtown, f"Акт {number}")
    client.force_login(member)

    _, page = section(client)

    assert "Показано 11\u00a0документов" in page


def test_an_empty_section_states_its_emptiness_rather_than_showing_an_empty_table(
    client, member, downtown, central
):
    """«Ничего не загружено» должно отличаться от «что-то сломалось»."""
    make_document(central, "Чужой акт")
    client.force_login(member)

    response, page = section(client)

    assert response.status_code == 200
    assert documents_on(page) == []
    assert "Ни одного документа пока не загружено" in stated(page)


def test_a_row_carries_the_document_handle(client, member, downtown):
    """`data-document` — договор разметки, тот же приём, что и у контуров плана."""
    document = make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = section(client)

    assert documents_on(page) == [str(document.pk)]


def test_the_page_carries_no_leftover_template_comments(client, member, downtown):
    """Многострочный `{# … #}` Django комментарием не считает и печатает на экране."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = section(client)

    assert "{#" not in page
