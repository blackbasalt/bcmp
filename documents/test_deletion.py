"""Deleting a документ: the confirmation, what goes with it, and who is allowed.

The seam is the one the whole section is tested at — HTTP. The tests submit from the
документ's own page on behalf of an employee with a known membership, and check what is
observable: what the screen asks before anything is destroyed, what is left in the store
afterwards, and what code a request answers with.

Two footholds in the markup. `data-deletion` is the state of the deletion — whether it is
offered at all, and whether the screen is holding the question rather than the answer.
`data-taken` names one thing that goes with the документ: the confirmation is only worth
having if it says what will be destroyed, and it is that list which is asserted rather than
the sentence around it.

There is no seam below HTTP: a deletion writes nothing back that a caller could inspect,
and what it did is read in the store and in the tables — which is where these tests look.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from documents.models import Document, DocumentTwin, TwinImage

from .test_section import documents_on, make_document, section, stated
from .test_twin import attach, markdown, picture, stored_files
from .test_upload import pdf, said_to, sent

pytestmark = pytest.mark.django_db


#: The state of the deletion on the page: offered, or being confirmed. Absent altogether
#: from a page shown to whoever may not delete — an action that cannot be performed is not
#: named on the screen either.
DELETION = re.compile(r'data-deletion="(?P<state>[^"]+)"')

#: One thing that goes with the документ: what it is, and what the confirmation says about
#: it. Named in the attribute, so that "something goes with it" and "this is what goes with
#: it" are two different assertions.
TAKEN = re.compile(r'data-taken="(?P<name>[^"]+)">(?P<said>[^<]*)<')


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Uploaded files go into a temporary directory rather than into the working copy.

    It stands here as its own copy instead of being imported: a fixture is auto-applied
    only in the module where it is declared.
    """
    settings.MEDIA_ROOT = tmp_path


def page_of(client, document):
    response = client.get(reverse("documents:document_detail", args=[document.pk]))
    return response, response.content.decode()


def ask_to_delete(client, document):
    """Press «Удалить документ» — the submission that asks the question and destroys nothing."""
    return client.post(
        reverse("documents:document_detail", args=[document.pk]), {"submitted": "deletion"}
    )


def confirm_deletion(client, document):
    """Answer the question — the submission the confirmation itself sends."""
    return client.post(
        reverse("documents:document_detail", args=[document.pk]),
        {"submitted": "deletion-confirmed"},
    )


def deletion_state(page):
    """What the page says about deleting this документ, or None if it does not offer it."""
    found = DELETION.search(page)
    return found["state"] if found else None


def taken_on(page):
    """What the confirmation says goes with the документ, by the name of each thing.

    Each phrase is read on a single line: a number and the word attached to it are held
    together by a non-breaking space, and what is asked here is the phrase, not the spacing
    inside it.
    """
    return {found["name"]: stated(found["said"]) for found in TAKEN.finditer(page)}


def with_a_scan(org, title="Акт со сканом"):
    """A документ that has put a file in the store — the ordinary case after a batch."""
    return make_document(org, title, file_uri=sent("акт.pdf", pdf("скан")))


# Asking before anything is destroyed


def test_asking_to_delete_destroys_nothing_and_holds_the_question(
    client, administrator, downtown, settings
):
    """A misclick must not cost an upload: the first press asks, and only the second acts."""
    document = with_a_scan(downtown)
    original = stored_files(settings)
    client.force_login(administrator)

    response = ask_to_delete(client, document)

    assert response.status_code == 200
    assert deletion_state(response.content.decode()) == "confirming"
    assert Document.objects.filter(pk=document.pk).exists()
    assert stored_files(settings) == original


def test_the_confirmation_names_what_goes_with_the_document(
    client, administrator, downtown
):
    """What is destroyed is said before it is: «удалить» over a документ with a близнец
    means more than the row the reader is looking at."""
    document = with_a_scan(downtown)
    client.force_login(administrator)
    attach(client, document, markdown("![](p3-img1.png)\n"), [picture()])

    response = ask_to_delete(client, document)

    assert taken_on(response.content.decode()) == {
        "original": "оригинал документа",
        "twin": "близнец и 1 картинка",
    }


def test_a_twin_without_pictures_is_named_on_its_own(client, administrator, downtown):
    """«Близнец и 0 картинок» is not what a близнец without pictures is: nothing has gone
    astray there, and a zero in a warning reads as something that has."""
    document = make_document(downtown, "Акт без файла")
    client.force_login(administrator)
    attach(client, document)

    response = ask_to_delete(client, document)

    assert taken_on(response.content.decode()) == {"twin": "близнец"}


def test_a_document_with_nothing_attached_names_nothing_in_the_confirmation(
    client, administrator, downtown
):
    """A документ entered by hand has neither a файл nor a близнец, and a list of nothing
    would be an empty promise on the screen."""
    document = make_document(downtown, "Акт без файла")
    client.force_login(administrator)

    response = ask_to_delete(client, document)

    assert taken_on(response.content.decode()) == {}


def test_the_page_of_a_document_offers_the_deletion_before_it_is_asked_for(
    client, administrator, downtown
):
    """The way in: the deletion stands on the документ's own page, where it is read about."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)

    _, page = page_of(client, document)

    assert deletion_state(page) == "offered"


# Deleting


def test_an_administrator_deletes_a_document_and_lands_back_on_the_shelf(
    client, administrator, downtown
):
    """The документ's own page is gone with it, so the confirmation is the shelf."""
    document = make_document(downtown, "Ошибочно загруженный акт")
    client.force_login(administrator)

    response = confirm_deletion(client, document)

    assert response.status_code == 302
    assert response["Location"] == reverse("documents:document_list")
    assert not Document.objects.filter(pk=document.pk).exists()


def test_deleting_a_document_takes_its_twin_its_images_and_every_stored_file(
    client, administrator, downtown, settings
):
    """Nothing is left behind in the store: a файл is not deleted by deleting the row that
    names it, and nothing else in the project would ever come back for it."""
    document = with_a_scan(downtown)
    client.force_login(administrator)
    attach(
        client,
        document,
        markdown("![](p3-img1.png)\n\n![](p4-img2.png)\n"),
        [picture(), picture("p4-img2.png")],
    )
    assert stored_files(settings)

    confirm_deletion(client, document)

    assert not Document.objects.exists()
    assert not DocumentTwin.objects.exists()
    assert not TwinImage.objects.exists()
    assert stored_files(settings) == set()


def test_a_deleted_document_is_gone_from_the_shelf_and_the_rest_stay(
    client, administrator, downtown, settings
):
    """One документ is deleted, not the folder it was uploaded with."""
    deleted = with_a_scan(downtown, "Ошибка")
    kept = with_a_scan(downtown, "Акт разграничения")
    of_the_kept = Path(settings.MEDIA_ROOT) / kept.file_uri.name
    client.force_login(administrator)

    confirm_deletion(client, deleted)

    _, shelf = section(client)
    assert documents_on(shelf) == [str(kept.pk)]
    assert of_the_kept.exists()


def test_the_shelf_names_the_deleted_document_and_what_went_with_it(
    client, administrator, downtown
):
    """The page it was deleted from went with it, and the shelf it lands on looks much the
    same as before with one row fewer: «удалён» alone leaves whoever deleted a документ with
    a близнец wondering whether the близнец is still lying somewhere."""
    document = with_a_scan(downtown, "Ошибочно загруженный акт")
    client.force_login(administrator)
    attach(client, document, markdown("![](p3-img1.png)\n"), [picture()])

    confirm_deletion(client, document)

    said = said_to(client)
    assert "Документ «Ошибочно загруженный акт» удалён" in said
    assert "оригинал документа, близнец и 1 картинка" in said


def test_a_document_with_no_file_at_all_is_deleted_all_the_same(
    client, administrator, downtown
):
    """A документ entered in the admin has no файл, and having none is not a failure to
    delete one."""
    document = make_document(downtown, "Акт без файла")
    client.force_login(administrator)

    response = confirm_deletion(client, document)

    assert response.status_code == 302
    assert not Document.objects.exists()


def test_deleting_a_document_that_is_already_gone_answers_that_it_is_missing(
    client, administrator, downtown
):
    """The second click of a double: the документ the submission names no longer exists,
    and that is said the way everything missing is said (ADR 0006)."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    confirm_deletion(client, document)

    response = confirm_deletion(client, document)

    assert response.status_code == 404


# Who may delete


def test_a_member_without_the_flag_is_offered_no_deletion(client, member, downtown):
    """The shelf is not editable by readers: an action an employee cannot perform is not
    offered to them either (ADR 0005)."""
    document = with_a_scan(downtown)
    client.force_login(member)

    _, page = page_of(client, document)

    assert deletion_state(page) is None


def test_a_readers_attempt_to_delete_leaves_the_document_in_place(
    client, member, downtown, settings
):
    """The right is checked on the request, not only on what the screen offers."""
    document = with_a_scan(downtown)
    original = stored_files(settings)
    client.force_login(member)

    response = confirm_deletion(client, document)

    assert response.status_code == 403
    assert Document.objects.filter(pk=document.pk).exists()
    assert stored_files(settings) == original


def test_a_reader_is_not_even_allowed_to_ask_the_question(client, member, downtown):
    """The confirmation is a screen of the deletion, and it is refused with it: shown the
    question, a reader would take the refusal for a fault of the form."""
    document = make_document(downtown, "Акт")
    client.force_login(member)

    response = ask_to_delete(client, document)

    assert response.status_code == 403


def test_administering_one_organisation_does_not_delete_anothers_document(
    client, administrator, central, settings
):
    """The right belongs to the pair "employee + organisation" (ADR 0005), and another
    client's документ is missing rather than forbidden (ADR 0006)."""
    theirs = make_document(central, "Чужой акт", file_uri=sent("чужой.pdf", pdf("чужой скан")))
    theirs_stored = stored_files(settings)
    client.force_login(administrator)

    response = confirm_deletion(client, theirs)

    assert response.status_code == 404
    assert Document.objects.filter(pk=theirs.pk).exists()
    assert stored_files(settings) == theirs_stored


def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, downtown):
    """Before signing in nothing is deleted — and nothing is confirmed to exist either."""
    document = make_document(downtown, "Акт")

    response = confirm_deletion(client, document)

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")
    assert Document.objects.filter(pk=document.pk).exists()
