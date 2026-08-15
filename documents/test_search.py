"""Finding one документ on a shelf of hundreds — the отбор and its three conditions.

The seam is the same as everywhere else in this section: the HTTP boundary. What is asked
of the shelf is asked in the address, and what is checked is which документы came back,
what is said about them, and what the bar the отбор was typed into holds afterwards.

The foothold in the markup is the `data-document` attribute on a table row — an отбор is
only a different set of rows, and it is read the way the whole shelf is. The bar itself
carries `data-search`: whether the shelf can be narrowed at all is its own assertion,
separate from what any one отбор answers.

Isolation is checked here again rather than left to the section's own tests, and
deliberately: the отбор is the one thing on this screen that takes a value from the reader
and puts it into a query, so «отбором нельзя дотянуться до чужого» has to be asserted of
the conditions themselves (ADR 0006).
"""

import pytest
from django.urls import reverse

from documents.models import Document, DocumentLink

from .test_section import documents_on, make_document, rows_on, stated

pytestmark = pytest.mark.django_db


def asked(client, **conditions):
    """The shelf with an отбор put to it — the conditions travel in the address."""
    response = client.get(reverse("documents:document_list"), conditions)
    return response, response.content.decode()


def attach(document, building):
    """A документ's привязка to a БЦ — what the building condition selects on (ADR 0008)."""
    return DocumentLink.objects.create(
        document=document,
        entity_type=DocumentLink.EntityType.SPACE,
        entity_id=building.pk,
    )


# The search


def test_a_document_is_found_by_its_title(client, member, downtown):
    """The question asked of a shelf of hundreds: «где акт разграничения»."""
    wanted = make_document(downtown, "Акт разграничения балансовой принадлежности")
    make_document(downtown, "Сертификат соответствия на насос")
    client.force_login(member)

    _, page = asked(client, q="разграничения")

    assert documents_on(page) == [str(wanted.pk)]


def test_the_title_is_searched_regardless_of_case(client, member, downtown):
    """«акт» must find «Акт»: the названия come from file names, and their capitalisation
    is whatever the folder they were carried across from happened to use."""
    wanted = make_document(downtown, "Акт разграничения балансовой принадлежности")
    client.force_login(member)

    _, page = asked(client, q="акт разграничения")

    assert documents_on(page) == [str(wanted.pk)]


def test_a_document_is_found_by_its_number(client, member, downtown):
    """A паспорт names the документ by номер, and it is by номер that it is looked for."""
    wanted = make_document(downtown, "Акт разграничения", doc_no="АКТ-12/2024")
    make_document(downtown, "Акт допуска", doc_no="АКТ-13/2024")
    client.force_login(member)

    _, page = asked(client, q="12/2024")

    assert documents_on(page) == [str(wanted.pk)]


def test_the_search_reaches_no_further_than_the_title_and_the_number(
    client, member, downtown, issuer
):
    """Название and номер only, and nothing else about the документ.

    The вид has a condition of its own and кем выдан a column, and a search that also
    matched them would answer «нашлось 40» to a query the reader typed to find one paper.
    """
    make_document(downtown, "Акт разграничения", issuer_party=issuer)
    client.force_login(member)

    _, page = asked(client, q="Промэнерго")

    assert documents_on(page) == []


def test_a_search_matching_nothing_shows_no_rows_at_all(client, member, downtown):
    """A question nothing answers is answered by nothing — not by the whole shelf."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = asked(client, q="протокол замеров")

    assert documents_on(page) == []


# The other two conditions


def test_the_vid_condition_shows_that_kind_alone(client, member, downtown):
    """«Показать все сертификаты» — the question a whole вид is looked at for."""
    certificate = make_document(downtown, "Сертификат на насос", kind=Document.Kind.CERTIFICATE)
    make_document(downtown, "Акт разграничения", kind=Document.Kind.ACT)
    client.force_login(member)

    _, page = asked(client, kind=Document.Kind.CERTIFICATE)

    assert documents_on(page) == [str(certificate.pk)]


def test_the_building_condition_shows_exactly_the_documents_attached_to_that_building(
    client, member, downtown, manhattan, make_building
):
    """The папка of one БЦ, gathered out of a shelf that holds every building's.

    Three states are told apart in one go: attached to this БЦ, attached to another, and
    attached to nothing at all — the устав, which belongs to no building.
    """
    other = make_building(downtown, "brd", "Boardwalk")
    ours = make_document(downtown, "Акт по Manhattan")
    attach(ours, manhattan)
    theirs = make_document(downtown, "Акт по Boardwalk")
    attach(theirs, other)
    make_document(downtown, "Устав")
    client.force_login(member)

    _, page = asked(client, building=str(manhattan.pk))

    assert documents_on(page) == [str(ours.pk)]


def test_a_document_attached_to_two_buildings_is_shown_once_under_each(
    client, member, downtown, manhattan, make_building
):
    """A договор covering two БЦ is on both папки, and it is one row on each."""
    other = make_building(downtown, "brd", "Boardwalk")
    shared = make_document(downtown, "Договор на обслуживание лифтов")
    attach(shared, manhattan)
    attach(shared, other)
    client.force_login(member)

    _, first = asked(client, building=str(manhattan.pk))
    _, second = asked(client, building=str(other.pk))

    assert documents_on(first) == [str(shared.pk)]
    assert documents_on(second) == [str(shared.pk)]


def test_the_building_list_offers_the_readers_own_buildings_only(
    client, member, downtown, central, manhattan, make_building
):
    """A БЦ this reader may not see is not on offer — naming it would name another client's
    building on their screen (ADR 0001)."""
    theirs = make_building(central, "ctr", "Central City")
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = asked(client)

    assert str(manhattan.pk) in page
    assert str(theirs.pk) not in page


# The conditions together


def test_the_three_conditions_compose(client, member, downtown, manhattan):
    """Four questions about one shelf answered at once, not one at a time."""
    wanted = make_document(downtown, "Акт разграничения", kind=Document.Kind.ACT)
    attach(wanted, manhattan)
    unattached = make_document(downtown, "Акт разграничения по другому зданию")
    other_kind = make_document(
        downtown, "Сертификат разграничения", kind=Document.Kind.CERTIFICATE
    )
    attach(other_kind, manhattan)
    client.force_login(member)

    _, page = asked(
        client, q="разграничения", kind=Document.Kind.ACT, building=str(manhattan.pk)
    )

    assert documents_on(page) == [str(wanted.pk)]
    assert str(unattached.pk) not in page
    assert str(other_kind.pk) not in page


def test_clearing_the_question_returns_the_whole_shelf(client, member, downtown):
    """The shelf without a question is the whole shelf: an отбор lives in the address and
    nowhere else, so dropping the address drops it."""
    make_document(downtown, "Акт разграничения")
    make_document(downtown, "Сертификат на насос")
    client.force_login(member)

    _, narrowed = asked(client, q="разграничения")
    _, whole = asked(client, q="", kind="", building="")

    assert len(documents_on(narrowed)) == 1
    assert len(documents_on(whole)) == 2


def test_the_bar_holds_on_to_what_was_asked(client, member, downtown, manhattan):
    """The question stays in the bar after it is answered.

    A bar that emptied itself would leave the reader looking at a shortened shelf with
    nothing on screen saying why it is short — and the way to narrow it further would be to
    type the whole question again.
    """
    document = make_document(downtown, "Акт разграничения", kind=Document.Kind.ACT)
    attach(document, manhattan)
    client.force_login(member)

    _, page = asked(
        client, q="разграничения", kind=Document.Kind.ACT, building=str(manhattan.pk)
    )

    assert 'value="разграничения"' in page
    assert f'value="{Document.Kind.ACT}" selected' in page
    assert f'value="{manhattan.pk}" selected' in page


# What the screen says about the answer


def test_the_stated_count_follows_the_otbor(client, member, downtown):
    """The number beneath the table counts what is in the table, not what is on the shelf."""
    make_document(downtown, "Акт разграничения")
    make_document(downtown, "Сертификат на насос")
    make_document(downtown, "Протокол замеров")
    client.force_login(member)

    _, page = asked(client, q="разграничения")

    assert "Показан 1 документ" in page
    assert "Показано 3" not in page


def test_a_question_that_matched_nothing_says_so_rather_than_that_nothing_was_uploaded(
    client, member, downtown
):
    """«Ничего не нашлось» and «ничего не загружено» are two different findings.

    One sends the reader to change the question, the other to upload the folder. Told apart
    by what was asked and not by what came back: a shelf can be genuinely empty and
    questioned at the same time, and then it is still the question that is on screen.
    """
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    response, page = asked(client, q="протокол замеров")

    assert response.status_code == 200
    assert "ничего не нашлось" in stated(page)
    assert "Ни одного документа пока не загружено" not in stated(page)


def test_an_empty_shelf_says_that_nothing_was_uploaded_rather_than_that_nothing_matched(
    client, member, downtown
):
    """The other half of the same distinction: no question was asked, so nothing was missed."""
    client.force_login(member)

    _, page = asked(client)

    assert "Ни одного документа пока не загружено" in stated(page)
    assert "ничего не нашлось" not in stated(page)


def test_the_bar_is_not_offered_on_a_shelf_nothing_has_been_uploaded_to(
    client, member, downtown
):
    """There is nothing to search: a bar over an empty shelf offers to narrow a nothing."""
    client.force_login(member)

    _, page = asked(client)

    assert "data-search" not in page


def test_the_bar_stands_on_a_shelf_that_a_question_emptied(client, member, downtown):
    """A question that matched nothing must be correctable where it was typed."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = asked(client, q="протокол замеров")

    assert "data-search" in page


# Isolation


def test_the_search_does_not_reach_into_another_organisations_documents(
    client, member, downtown, central
):
    """A search is a question about one's own shelf. Another client's paper is not on it,
    and typing its название does not put it there (ADR 0006)."""
    make_document(central, "Договор с чужим подрядчиком")
    client.force_login(member)

    _, page = asked(client, q="подрядчиком")

    assert documents_on(page) == []
    assert "Договор с чужим подрядчиком" not in page


def test_a_building_of_another_organisation_selects_nothing(
    client, member, downtown, central, make_building
):
    """A БЦ named in the address rather than chosen from the list.

    It is not on offer, and being named anyway does not make it selectable: what is asked
    of the shelf is checked against the buildings this reader may see, not merely against
    the ones the screen happened to print.
    """
    theirs = make_building(central, "ctr", "Central City")
    ours = make_document(downtown, "Акт разграничения")
    not_ours = make_document(central, "Акт по чужому зданию")
    attach(not_ours, theirs)
    client.force_login(member)

    _, page = asked(client, building=str(theirs.pk))

    assert documents_on(page) == []
    assert str(ours.pk) not in page
    assert "Акт по чужому зданию" not in page


def test_a_building_that_does_not_exist_at_all_selects_nothing(client, member, downtown):
    """A мусор in the address is a question nothing answers, not a question nobody asked:
    an unreadable БЦ must not quietly widen the shelf back to all of it."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    response, page = asked(client, building="0f8ff1d0-0000-0000-0000-000000000000")

    assert response.status_code == 200
    assert documents_on(page) == []


def test_a_kind_that_is_not_a_kind_selects_nothing(client, member, downtown):
    """The same rule for the вид: an answer nothing on the list gives is not «всё»."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    response, page = asked(client, kind="прочее-какое-нибудь")

    assert response.status_code == 200
    assert documents_on(page) == []


def test_a_condition_that_did_not_read_is_said_on_the_screen(client, member, downtown):
    """An empty shelf beneath a bar standing on «Любой вид» reads as a breakage.

    The отбор that emptied it came from the address and is not in the select, so the
    select shows nothing of it: without a line saying so, the reader is looking at a shelf
    narrowed to nothing by something the screen never showed them.
    """
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = asked(client, kind="прочее-какое-нибудь")

    assert "В адресе указан вид, которого нет в списке" in stated(page)


def test_a_building_that_did_not_read_is_said_on_the_screen(
    client, member, downtown, central, make_building
):
    """The same for a БЦ — and worded the same whether it is missing or another client's:
    telling the two apart would tell this reader what the other one has (ADR 0006)."""
    theirs = make_building(central, "ctr", "Central City")
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = asked(client, building=str(theirs.pk))

    assert "В адресе указан БЦ, которого нет в списке" in stated(page)
    assert "Central City" not in page


# The shelf around the question


def test_the_rows_of_a_narrowed_shelf_read_as_they_always_do(
    client, member, downtown, issuer
):
    """An отбор changes which rows are shown and nothing about how one is read."""
    make_document(
        downtown,
        "Акт разграничения балансовой принадлежности",
        doc_no="АКТ-12/2024",
        issuer_party=issuer,
    )
    client.force_login(member)

    _, page = asked(client, q="разграничения")
    (row,) = rows_on(page).values()

    assert "АКТ-12/2024" in row
    assert "ТОО Промэнерго" in row


def test_the_narrowed_page_carries_no_leftover_template_comments(client, member, downtown):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on screen."""
    make_document(downtown, "Акт разграничения")
    client.force_login(member)

    _, page = asked(client, q="разграничения")

    assert "{#" not in page
