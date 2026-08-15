"""A документ's own page — everything recorded about it, and the filling in of what is not.

The seam is the same one the section is tested at: HTTP. The tests walk named addresses with
the test client on behalf of a user with a known membership, and check what is observable —
what stands on the page, what a POST does to the shelf and what code a request answers with.

The foothold in the markup is `data-field` on the value of a field. That is the page's
contract: it says which particular is shown and what is written in it, and a rebuild of the
layout does not rewrite the test suite.
"""

import re
from datetime import date

import pytest
from django.urls import reverse

from documents.models import Document, DocumentLink

from .test_section import documents_on, make_document, rows_on, section, stated

pytestmark = pytest.mark.django_db

#: The value of a field on the page, by the name of the field — the page's contract. The
#: same device as the `data-document` row of the table: what is asked of a field is not the
#: structure around it but the text inside it, and that text must be found in the field
#: itself rather than somewhere on the page.
FIELD = re.compile(r'data-field="(?P<name>[^"]+)"[^>]*>(?P<value>.*?)</dd>', re.DOTALL)


def page_of(client, document):
    response = client.get(reverse("documents:document_detail", args=[document.pk]))
    return response, response.content.decode()


def fields_on(page):
    """What the page says about each particular of the document."""
    return {
        field["name"]: stated(re.sub(r"<[^>]+>", " ", field["value"]))
        for field in FIELD.finditer(page)
    }


# What the page shows


def test_a_row_of_the_table_opens_the_documents_own_page(client, member, downtown):
    """The way in: the shelf names a document, and its own page holds everything about it."""
    document = make_document(downtown, "Акт разграничения балансовой принадлежности")
    client.force_login(member)

    _, shelf = section(client)

    assert reverse("documents:document_detail", args=[document.pk]) in shelf


def test_the_page_shows_everything_recorded_about_the_document(
    client, member, downtown, issuer
):
    """Вид, название, номер, дата выдачи, кем выдан, срок, ревизия — all on one page."""
    document = make_document(
        downtown,
        "Акт разграничения балансовой принадлежности",
        kind=Document.Kind.ACT,
        doc_no="АКТ-12/2024",
        issued_at=date(2024, 3, 14),
        issuer_party=issuer,
        valid_until=date(2027, 3, 13),
        revision="ред. 2",
    )
    client.force_login(member)

    response, page = page_of(client, document)
    fields = fields_on(page)

    assert response.status_code == 200
    assert fields["kind"] == "Акт"
    assert fields["title"] == "Акт разграничения балансовой принадлежности"
    assert fields["doc_no"] == "АКТ-12/2024"
    assert fields["issued_at"] == "14.03.2024"
    assert fields["issuer"] == "ТОО Промэнерго"
    assert fields["valid_until"] == "13.03.2027"
    assert fields["revision"] == "ред. 2"


def test_a_particular_nobody_filled_in_reads_as_no_data(client, member, downtown):
    """A batch arrives with nothing but a name: blank space reads as a zero, a dash does not."""
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(member)

    _, page = page_of(client, document)
    fields = fields_on(page)

    assert fields["doc_no"] == "— нет данных"
    assert fields["issued_at"] == "— нет данных"
    assert fields["issuer"] == "— нет данных"
    assert fields["valid_until"] == "— нет данных"
    assert fields["revision"] == "— нет данных"


def test_the_page_names_the_bcs_the_document_is_attached_to(
    client, member, downtown, manhattan
):
    """A привязка is read as the building it names, not as the identifier it holds."""
    document = make_document(downtown, "Договор на обслуживание")
    DocumentLink.objects.create(
        document=document,
        entity_type=DocumentLink.EntityType.SPACE,
        entity_id=manhattan.pk,
    )
    client.force_login(member)

    _, page = page_of(client, document)

    assert "Manhattan" in fields_on(page)["links"]


def test_a_document_attached_to_nothing_says_so_rather_than_showing_an_empty_place(
    client, member, downtown
):
    """The устав belongs to no building, and an empty place there reads as a breakage."""
    document = make_document(downtown, "Устав")
    client.force_login(member)

    _, page = page_of(client, document)

    assert fields_on(page)["links"] == "— нет данных"


def test_the_original_is_downloaded_from_the_page(client, member, downtown):
    """The archive comes back out through the documents chokepoint, from where it is read."""
    document = make_document(downtown, "Акт со сканом", file_uri="documents/акт.pdf")
    client.force_login(member)

    _, page = page_of(client, document)

    assert reverse("documents:document_file", args=[document.pk]) in page


def test_a_document_without_a_file_offers_no_download_from_the_page(client, member, downtown):
    """Documents entered in the admin have no file, and a link to nothing is a broken link."""
    document = make_document(downtown, "Акт без файла")
    client.force_login(member)

    _, page = page_of(client, document)

    assert reverse("documents:document_file", args=[document.pk]) not in page
    assert fields_on(page)["original"] == "— нет данных"


# Who may reach the page


def test_another_organisations_document_is_missing_rather_than_forbidden(
    client, member, central
):
    """The answer must not confirm that another client's document exists (ADR 0006)."""
    theirs = make_document(central, "Чужой акт")
    client.force_login(member)

    response, _ = page_of(client, theirs)

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, downtown):
    """Before sign-in nothing is shown — not even that a document exists."""
    document = make_document(downtown, "Акт разграничения")

    response = client.get(reverse("documents:document_detail", args=[document.pk]))

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


# Filling in the реквизиты


def fill_in(client, document, **particulars):
    """Send the реквизиты the way the form on the page sends them: every field, filled or not.

    A form posts all five whether or not anything was typed into them, and a test that sent
    only the one it cares about would be checking a submission the screen never makes.
    """
    submission = {
        "doc_no": "",
        "issued_at": "",
        "issuer_party": "",
        "valid_until": "",
        "revision": "",
    }
    return client.post(
        reverse("documents:document_detail", args=[document.pk]), submission | particulars
    )


def edit_form(page):
    """The form for filling in the реквизиты — or nothing, if it is not offered."""
    return page if 'data-edit="document"' in page else None


def test_an_administrator_of_the_organisation_is_offered_the_editing(
    client, administrator, downtown
):
    """The other half of the transfer: a batch that arrived with nothing but a name is
    enriched over time, and not through the Django admin."""
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(administrator)

    _, page = page_of(client, document)

    assert edit_form(page) is not None


def test_a_member_without_the_flag_is_offered_no_editing_at_all(client, member, downtown):
    """An action an employee cannot perform is not offered to them either (ADR 0005)."""
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(member)

    _, page = page_of(client, document)

    assert edit_form(page) is None


def test_a_member_without_the_flag_is_refused_even_by_posting_directly(
    client, member, downtown
):
    """It is not only the form that is withheld: the right is checked on the request itself."""
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(member)

    response = fill_in(client, document, doc_no="АКТ-12/2024")

    assert response.status_code == 403
    document.refresh_from_db()
    assert document.doc_no is None


def test_administering_one_organisation_does_not_administer_another(
    client, administrator, central
):
    """The right belongs to the pair "employee + organisation", not to the employee (ADR 0005).

    Another client's document is missing rather than forbidden, in writing as in reading:
    the answer must not confirm that it exists (ADR 0006). Being refused would say that
    there is something at this address to be refused.
    """
    theirs = make_document(central, "Чужой акт")
    client.force_login(administrator)

    response = fill_in(client, theirs, doc_no="АКТ-12/2024")

    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.doc_no is None


def test_an_anonymous_attempt_to_fill_in_is_sent_to_the_login_screen(client, downtown):
    """Before signing in nothing is written — just as nothing is read."""
    document = make_document(downtown, "Акт без реквизитов")

    response = fill_in(client, document, doc_no="АКТ-12/2024")

    assert response.status_code == 302
    assert reverse("login") in response["Location"]
    document.refresh_from_db()
    assert document.doc_no is None


def test_what_was_filled_in_is_read_afterwards_on_the_page_and_in_the_table(
    client, administrator, downtown, issuer
):
    """The point of the whole page: what an administrator enters is there the next time.

    In the table too, and not only on the page: the shelf is where a document is looked for,
    and a номер known to the page alone is a номер nobody finds.
    """
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(administrator)

    fill_in(
        client,
        document,
        doc_no="АКТ-12/2024",
        issued_at="2024-03-14",
        issuer_party=str(issuer.pk),
    )

    _, page = page_of(client, document)
    fields = fields_on(page)
    assert fields["doc_no"] == "АКТ-12/2024"
    assert fields["issued_at"] == "14.03.2024"
    assert fields["issuer"] == "ТОО Промэнерго"

    _, shelf = section(client)
    row = rows_on(shelf)[str(document.pk)]
    assert "АКТ-12/2024" in row
    assert "14.03.2024" in row
    assert "ТОО Промэнерго" in row


def test_a_particular_filled_in_earlier_comes_back_into_the_form(
    client, administrator, downtown
):
    """A date already stored must return in the notation the field reads.

    Otherwise it comes back empty, and whoever opened the page to enter the номер saves the
    дата выдачи away without ever seeing it.
    """
    document = make_document(downtown, "Акт", issued_at=date(2024, 3, 14))
    client.force_login(administrator)

    _, page = page_of(client, document)

    assert 'value="2024-03-14"' in page


def test_a_srok_and_a_revision_are_stored_and_shown_and_do_nothing_else(
    client, administrator, downtown
):
    """Two fields without behaviour: they are displayed and they threaten nothing.

    A срок long past changes no screen — the document is not marked, not moved, not counted
    among anything and not warned about. A реестр сроков is a different stage, and a screen
    that hinted at one would promise a watch nobody keeps.
    """
    long_past = make_document(downtown, "Акт со старым сроком")
    # The one to compare it against: the same document in every respect but the срок.
    ordinary = make_document(downtown, "Акт без срока")
    client.force_login(administrator)

    fill_in(client, long_past, valid_until="2020-01-01", revision="ред. 3")

    _, page = page_of(client, long_past)
    fields = fields_on(page)
    assert fields["valid_until"] == "01.01.2020"
    assert fields["revision"] == "ред. 3"

    _, shelf = section(client)
    rows = rows_on(shelf)
    # The shelf writes the two of them alike: apart from their titles the rows say the same
    # thing, so a срок five years past sets nothing apart, and neither does a ревизия. Both
    # are still there and both are still counted — nothing has been sorted out.
    without_title = {
        key: row.replace(title, "")
        for key, row, title in (
            (str(long_past.pk), rows[str(long_past.pk)], long_past.title),
            (str(ordinary.pk), rows[str(ordinary.pk)], ordinary.title),
        )
    }
    assert without_title[str(long_past.pk)] == without_title[str(ordinary.pk)]
    assert sorted(documents_on(shelf)) == sorted([str(long_past.pk), str(ordinary.pk)])
    assert "Показано 2\u00a0документа" in shelf  # the number and the word do not drift apart


def test_a_link_to_another_clients_building_is_not_resolved_on_the_page(
    client, member, downtown, central, make_building
):
    """A привязка holds an identifier, and an identifier is not a licence to read a row.

    The document is visible through its own organisation (ADR 0006), the building through
    its own checkpoint (ADR 0001) — and a link pointing across is a link that names nothing.
    """
    theirs = make_building(central, "cc", "Central City")
    document = make_document(downtown, "Договор на все объекты")
    DocumentLink.objects.create(
        document=document,
        entity_type=DocumentLink.EntityType.SPACE,
        entity_id=theirs.pk,
    )
    client.force_login(member)

    _, page = page_of(client, document)

    assert "Central City" not in page
    assert fields_on(page)["links"] == "— нет данных"


def test_a_saved_document_is_read_back_on_its_own_page(client, administrator, downtown):
    """The reloaded page is the confirmation: what was entered is read where it was entered."""
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(administrator)

    response = fill_in(client, document, doc_no="АКТ-12/2024")

    assert response.status_code == 302
    assert response["Location"] == reverse("documents:document_detail", args=[document.pk])


def test_the_page_carries_no_leftover_template_comments(client, administrator, downtown):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on the screen."""
    document = make_document(downtown, "Акт без реквизитов")
    client.force_login(administrator)

    _, page = page_of(client, document)

    assert "{#" not in page


def test_a_link_to_something_that_is_not_a_bc_opens_no_broken_address(
    client, member, downtown, first_floor
):
    """Every привязка on the page opens a building's card, and a floor has no card.

    The схема permits a привязка to any space and the Django admin can create one; rendered
    as a BC it would be an address that answers 404. This stage attaches papers to buildings
    (ADR 0008), and the screen for anything else arrives with the stage that attaches it.
    """
    document = make_document(downtown, "Акт на этаж")
    DocumentLink.objects.create(
        document=document,
        entity_type=DocumentLink.EntityType.SPACE,
        entity_id=first_floor.pk,
    )
    client.force_login(member)

    _, page = page_of(client, document)

    assert reverse("building_passport:bc_detail", args=[first_floor.pk]) not in page
