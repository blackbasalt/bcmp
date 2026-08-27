"""The "Документы" section — what an employee of the management company sees over HTTP.

There is one seam: the HTTP boundary. The tests walk named addresses with the test client
on behalf of a user with a known membership and check what is observable — which documents
are on screen, what is said about them and what code the request answers with. Below HTTP
there is no seam: the visibility chokepoint is checked through the same screen, because
that is how it is read.

The foothold in the markup is the `data-document` attribute on a table row. That is the
screen's contract: it shows which documents are displayed and in what order, and a rebuild
of the layout does not rewrite the test suite.
"""

import re
from datetime import date

import pytest
from django.urls import reverse

from documents.models import Document

pytestmark = pytest.mark.django_db

#: A table row together with the document's key: the screen's contract and everything
#: written in the row. It is not read by parsing tags — what is asked of a row is not its
#: structure but its text, and that text must be found in the row itself, not somewhere on
#: the page.
ROW = re.compile(r'<tr[^>]*data-document="(?P<key>[^"]+)"[^>]*>(?P<cells>.*?)</tr>', re.DOTALL)


def stated(text):
    """The text on a single line: a phrase must not break on a line wrap in the markup."""
    return " ".join(text.split())


def rows_on(page):
    """The table rows by document key: what is written in each of them."""
    return {row["key"]: stated(re.sub(r"<[^>]+>", " ", row["cells"])) for row in ROW.finditer(page)}


def documents_on(page):
    """The keys of the documents shown, top to bottom — the order of the rows is checked too."""
    return [row["key"] for row in ROW.finditer(page)]


def section(client):
    response = client.get(reverse("documents:document_list"))
    return response, response.content.decode()


def make_document(org, title, **fields):
    """An organisation's document. Everything but kind and title is optional — as in life."""
    fields.setdefault("kind", Document.Kind.ACT)
    return Document.objects.create(org=org, title=title, **fields)



# Access and isolation


def test_a_member_sees_the_documents_of_their_own_organisation_only(
    client, member, downtown, central
):
    """Client isolation on screen — exactly what a document has its own chokepoint for."""
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
    """Two clients for one employee — two shelves, not one common heap.

    This must be said in the row itself: the names of both organisations somewhere on the
    page distinguish nothing — they would match even with their places swapped.
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
    """The label holds on to the reader, not to the data.

    It would have to vanish exactly when the second client has no documents yet — that is,
    when whoever handles two of them most needs to know whose shelf this is.
    """
    ours = make_document(downtown, "Акт разграничения")
    client.force_login(both_clients)

    _, page = section(client)

    assert downtown.name in rows_on(page)[str(ours.pk)]


def test_a_reader_of_one_client_is_not_told_the_same_name_in_every_row(
    client, member, downtown
):
    """A column repeating one name down the whole table distinguishes nothing."""
    ours = make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = section(client)

    assert downtown.name not in rows_on(page)[str(ours.pk)]


def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, downtown):
    """Before sign-in nothing is shown — not even an empty shelf."""
    make_document(downtown, "Акт разграничения")

    response = client.get(reverse("documents:document_list"))

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


# The table


def test_a_row_shows_what_tells_the_documents_apart(client, member, downtown, issuer):
    """Kind, title, number, issue date and issuer — right there in the row."""
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
    """Blank space in a row can be read as a zero; «— нет данных» cannot."""
    make_document(downtown, "Акт без реквизитов")
    client.force_login(member)

    _, page = section(client)
    (row,) = rows_on(page).values()

    assert row.count("— нет данных") == 3  # number, issue date and issuer


def test_the_newest_uploads_are_at_the_top(client, member, downtown):
    """The order is by upload: the batch that has just been transferred lies on top.

    The issue date sets no order: an act from 2019 uploaded today is looked for in the same
    place as the rest of today's batch, not at the tail of the list.
    """
    older = make_document(downtown, "Загружен первым", issued_at=date(2024, 3, 14))
    newer = make_document(downtown, "Загружен вторым", issued_at=date(2019, 1, 9))
    client.force_login(member)

    _, page = section(client)

    assert documents_on(page) == [str(newer.pk), str(older.pk)]


def test_the_section_states_how_many_documents_it_shows(client, member, downtown):
    """The number on screen in words: «сколько всего» is the question asked first."""
    for number in range(3):
        make_document(downtown, f"Акт {number}")
    client.force_login(member)

    _, page = section(client)

    assert "Показано 3\u00a0документа" in page  # the number and the word do not drift apart


def test_a_single_document_is_counted_in_the_singular(client, member, downtown):
    """«Показано 1 документов» reads as a glitch on the screen, not as a single document."""
    make_document(downtown, "Единственный акт")
    client.force_login(member)

    _, page = section(client)

    assert "Показан 1\u00a0документ" in page


def test_eleven_documents_are_counted_by_the_tens_rather_than_by_the_last_digit(
    client, member, downtown
):
    """Eleven is not «одиннадцать документ»: the second digit of the number cancels the first."""
    for number in range(11):
        make_document(downtown, f"Акт {number}")
    client.force_login(member)

    _, page = section(client)

    assert "Показано 11\u00a0документов" in page


def test_an_empty_section_states_its_emptiness_rather_than_showing_an_empty_table(
    client, member, downtown, central
):
    """"Nothing has been uploaded" must differ from "something has broken"."""
    make_document(central, "Чужой акт")
    client.force_login(member)

    response, page = section(client)

    assert response.status_code == 200
    assert documents_on(page) == []
    assert "Ни одного документа пока не загружено" in stated(page)


def test_a_row_carries_the_document_handle(client, member, downtown):
    """`data-document` is a contract of the markup, the same device as the plan's contours."""
    document = make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = section(client)

    assert documents_on(page) == [str(document.pk)]


def test_the_page_carries_no_leftover_template_comments(client, member, downtown):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on the screen."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = section(client)

    assert "{#" not in page
