"""Близнецы в пачке: a converted folder loaded in one go.

The seam is the one the whole section is tested at — HTTP: the batch is submitted to the
address the section stands at, and what is checked is what is observable afterwards — which
документы are on the shelf, which близнец landed on which of them, and what the report says
about the files that did not land.

A converted folder holds three kinds of file at once: the документы, the маркдаун-близнецы
made from them and the картинки those близнецы refer to. Nothing but the names tells them
apart, and that is the contract this module is about — `akt-2024-03.pdf` ↔
`akt-2024-03.md`, and `![](p3-img1.png)` ↔ the file called `p3-img1.png`.
"""

import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document, DocumentTwin, TwinImage

from .test_section import section
from .test_twin import page_of, picture, twin_state, unmatched_on
from .test_upload import pdf, png, said_to, sent, titles, upload, upload_form

pytestmark = pytest.mark.django_db

#: What the batch's file dialog opens on. The formats are asked of the field the files are
#: chosen with, not of the page: a `.md` anywhere in the markup would answer the question
#: without the dialog offering anything.
OFFERED = re.compile(r'<input[^>]*name="files"[^>]*accept="(?P<formats>[^"]+)"')


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Uploaded files go into a temporary directory rather than into the working copy.

    It stands here as its own copy instead of being imported: a fixture is auto-applied
    only in the module where it is declared.
    """
    settings.MEDIA_ROOT = tmp_path


def converted(name, text="# Акт\n\nТекст акта.\n"):
    """A близнец as it arrives in the batch — named after the документ it was made from."""
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/markdown")


def twin_of(title):
    """The близнец of the документ that landed under this title."""
    return Document.objects.get(title=title).twin


def pictures_of(title):
    """The names the близнец of this документ keeps its картинки under."""
    return sorted(twin_of(title).images.values_list("name", flat=True))


def markdown_of(title):
    return twin_of(title).markdown.read().decode("utf-8")


# Each близнец on its own документ


def test_a_batch_of_documents_and_their_twins_lands_with_each_twin_on_its_own_document(
    client, administrator
):
    """The point of the slot existing now: the alternative is a second pass over the same
    pile of hundreds of files."""
    client.force_login(administrator)

    upload(
        client,
        sent("akt-2024-03.pdf"),
        sent("akt-2024-04.pdf"),
        converted("akt-2024-03.md", "# Акт за март\n"),
        converted("akt-2024-04.md", "# Акт за апрель\n"),
    )

    assert titles() == ["akt-2024-03", "akt-2024-04"]
    assert markdown_of("akt-2024-03") == "# Акт за март\n"
    assert markdown_of("akt-2024-04") == "# Акт за апрель\n"


def test_the_markdown_of_a_twin_does_not_land_on_the_shelf_as_a_document_of_its_own(
    client, administrator
):
    """A близнец is not a документ: it conveys what the документ says and attests nothing."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), converted("akt.md"))

    assert titles() == ["akt"]
    assert Document.objects.get().attached_twin() is not None


def test_the_pictures_a_twin_refers_to_go_to_the_twin_that_refers_to_them(
    client, administrator
):
    """The картинки are matched to the близнец that names them, and to no other."""
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        sent("dogovor.pdf"),
        converted("akt.md", "![](p3-img1.png)\n"),
        converted("dogovor.md", "![](p7-img2.png)\n"),
        picture("p3-img1.png"),
        picture("p7-img2.png"),
    )

    assert pictures_of("akt") == ["p3-img1.png"]
    assert pictures_of("dogovor") == ["p7-img2.png"]


def test_a_picture_no_twin_refers_to_is_an_ordinary_document(client, administrator):
    """A photograph of a signed акт is a документ as ordinary as a скан.

    Only a картинка some близнец names is part of one — the reference is what makes it a
    half of a документ rather than a документ in its own right.
    """
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        converted("akt.md", "![](p3-img1.png)\n"),
        picture("p3-img1.png"),
        SimpleUploadedFile("снимок акта.png", png("акт на телефон")),
    )

    assert titles() == ["akt", "снимок акта"]
    assert pictures_of("akt") == ["p3-img1.png"]


def test_one_picture_named_by_two_twins_reaches_both_of_them(client, administrator):
    """A name names one картинка in the batch, and both близнеца that refer to it get it.

    A схема referred to by two документы is one file in the converted folder; refusing to
    resolve it for either would report a finding the batch itself invented.
    """
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        sent("dogovor.pdf"),
        converted("akt.md", "![](plan.png)\n"),
        converted("dogovor.md", "![](plan.png)\n"),
        picture("plan.png"),
    )

    assert pictures_of("akt") == ["plan.png"]
    assert pictures_of("dogovor") == ["plan.png"]
    assert twin_of("akt").unmatched_images == []
    assert twin_of("dogovor").unmatched_images == []


# What is reported and not stored


def test_a_twin_whose_document_is_not_in_the_batch_is_reported_and_stores_nothing(
    client, administrator
):
    """The person who uploaded two hundred files needs to know exactly what did not land."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), converted("protokol.md"))

    assert titles() == ["akt"]
    assert not DocumentTwin.objects.exists()
    said = said_to(client)
    assert "protokol.md" in said
    assert "protokol" in said


def test_a_twin_that_cannot_be_attached_does_not_stop_the_rest_of_the_batch(
    client, administrator
):
    """The same partial-success rule as everything else in the batch: what took, took."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), converted("akt.md"), converted("protokol.md"))

    assert titles() == ["akt"]
    assert DocumentTwin.objects.count() == 1
    assert twin_of("akt") is not None
    assert "protokol.md" in said_to(client)


def test_a_twin_whose_document_was_refused_is_reported_rather_than_left_hanging(
    client, administrator
):
    """A близнец is attached to a документ, so a документ that was not stored takes its
    близнец with it — and both are named, because both have to be sent again."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf", b"MZ\x90\x00 not a scan"), converted("akt.md"))

    assert Document.objects.count() == 0
    assert not DocumentTwin.objects.exists()
    said = said_to(client)
    assert "akt.pdf" in said
    assert "akt.md" in said


def test_a_twin_whose_document_was_already_on_the_shelf_is_reported(client, administrator):
    """Overlapping folders are the norm in an archive transfer, and a duplicate stores
    nothing — so there is no документ of this batch to attach to.

    Replacing the близнец of the документ already on the shelf would be a replacement nobody
    asked for: it is done on that документ's own page, where it says which близнец is being
    superseded.
    """
    client.force_login(administrator)
    upload(client, sent("akt.pdf", pdf("одно и то же")))

    upload(client, sent("akt.pdf", pdf("одно и то же")), converted("akt.md"))

    assert not DocumentTwin.objects.exists()
    said = said_to(client)
    assert "akt.md" in said


def test_a_picture_of_an_unaccepted_format_takes_its_twin_and_leaves_the_batch(
    client, administrator
):
    """All or nothing for the близнец (ADR 0011), partial success for the batch around it.

    A PDF under the name the markdown refers to is a second документ smuggled in past the
    documents section, and it is not stored as either.
    """
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        sent("protokol.pdf"),
        converted("akt.md", "![](p3-img1.png)\n"),
        SimpleUploadedFile("p3-img1.png", b"MZ\x90\x00 not a picture"),
    )

    assert titles() == ["akt", "protokol"]
    assert not DocumentTwin.objects.exists()
    assert not TwinImage.objects.exists()
    said = said_to(client)
    assert "akt.md" in said
    assert "p3-img1.png" in said


def test_a_refused_twin_names_the_pictures_that_went_down_with_it(client, administrator):
    """A картинка nothing refers to lands as a документ, so one that vanished instead has to
    be named: otherwise the sender looks for their схемы on the shelf."""
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        converted("protokol.md", "![](p3-img1.png)\n"),
        picture("p3-img1.png"),
    )

    assert titles() == ["akt"]
    said = said_to(client)
    assert "protokol.md" in said
    assert "p3-img1.png" in said


def test_a_picture_name_held_by_two_files_resolves_to_neither(client, administrator):
    """One name, two files: the reference names both and therefore names none.

    Attaching either would be a coin toss recorded as a complete близнец, and the половина
    of a близнец is exactly what the references are parsed to prevent.
    """
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        converted("akt.md", "![](p3-img1.png)\n"),
        picture("p3-img1.png"),
        SimpleUploadedFile("p3-img1.png", png("другая схема")),
    )

    assert titles() == ["akt"]
    assert not DocumentTwin.objects.exists()
    assert "p3-img1.png" in said_to(client)


def test_two_twins_under_one_name_are_reported_rather_than_one_overwriting_the_other(
    client, administrator
):
    """The name is what a близнец finds its документ by, so two of them under one name find
    the same документ — and the second would silently supersede the first."""
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        converted("akt.md", "# Первый близнец\n"),
        converted("akt.md", "# Второй близнец\n"),
    )

    assert titles() == ["akt"]
    assert not DocumentTwin.objects.exists()
    assert "akt.md" in said_to(client)


def test_a_markdown_that_is_not_text_is_refused_by_name(client, administrator):
    """A близнец is text: what does not decode is not what the ИИ-управляющий would read."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), SimpleUploadedFile("akt.md", png("не текст")))

    assert titles() == ["akt"]
    assert not DocumentTwin.objects.exists()
    assert "akt.md" in said_to(client)


# Unresolved references


def test_an_unresolved_reference_in_a_batched_twin_surfaces_on_the_documents_page(
    client, administrator
):
    """Recorded and displayed exactly as for a близнец attached one at a time: one broken
    reference means the модель reads the документ without its схема and never learns it."""
    client.force_login(administrator)

    upload(
        client,
        sent("akt.pdf"),
        converted("akt.md", "![](p3-img1.png)\n\n![](p9-img7.png)\n"),
        picture("p3-img1.png"),
    )

    _, page = page_of(client, Document.objects.get())
    assert twin_state(page) == "attached"
    assert unmatched_on(page) == ["p9-img7.png"]


def test_an_unresolved_reference_does_not_keep_the_twin_off_the_document(
    client, administrator
):
    """A reference nothing in the folder answers is a finding about the conversion, not a
    reason to store nothing: the половина that exists is still what the модель will read."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), converted("akt.md", "![](p9-img7.png)\n"))

    assert twin_of("akt").unmatched_images == ["p9-img7.png"]


def test_the_report_names_the_documents_whose_twins_have_unresolved_references(
    client, administrator
):
    """Nobody opens two hundred pages after a batch: a finding nothing reports is a finding
    nobody sees."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), converted("akt.md", "![](p9-img7.png)\n"))

    said = said_to(client)
    assert "p9-img7.png" in said
    assert "akt" in said


# What the batch says about itself


def test_the_report_states_how_many_twins_were_stored_alongside_the_files(
    client, administrator
):
    """Two counts and one question — did the folder go through."""
    client.force_login(administrator)

    upload(
        client,
        sent("akt1.pdf"),
        sent("akt2.pdf"),
        converted("akt1.md"),
        converted("akt2.md"),
    )

    said = said_to(client)
    assert "Загружено 2 файла" in said
    assert "Приложено 2 близнеца" in said


def test_a_single_attached_twin_is_counted_in_the_singular(client, administrator):
    """«Приложено 1 близнецов» reads as a glitch on the screen, not as a single близнец."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"), converted("akt.md"))

    assert "Приложен 1 близнец" in said_to(client)


def test_a_batch_without_any_twins_says_nothing_about_them(client, administrator):
    """Most batches are scans and nothing else: a count of nothing is noise on the screen."""
    client.force_login(administrator)

    upload(client, sent("akt.pdf"))

    said = said_to(client)
    assert "Загружен 1 файл" in said
    assert "Приложен" not in said


def test_the_batch_form_offers_to_choose_markdown_files_alongside_the_documents(
    client, administrator
):
    """A folder is chosen in one go, and a dialog that hides the близнецы makes that
    impossible: what the form accepts and what the dialog opens on are one rule."""
    client.force_login(administrator)

    _, page = section(client)

    assert upload_form(page) is not None
    offered = OFFERED.search(page)["formats"]
    assert ".md" in offered
    assert ".pdf" in offered
