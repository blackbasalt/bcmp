"""Близнец: attaching one to a документ, replacing it, taking it off and reading it back.

The seam is the one the whole section is tested at — HTTP. The tests submit the form that
stands on the документ's page, on behalf of an employee with a known membership, and check
what is observable: what the page says about the близнец, what is left in the store after a
replacement, and what code a request for someone else's близнец answers with.

Two footholds in the markup. `data-twin` is the indicator: it says whether the документ has
a близнец, and it stands both on the page and in the row of the shelf, because both must
say the same thing. `data-unmatched` carries an image reference the близнец makes and no
attached picture answers — the finding this screen exists to report.
"""

import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documents.models import DocumentTwin, TwinImage

from .test_section import ROW, make_document, section
from .test_upload import pdf, png

pytestmark = pytest.mark.django_db

#: The близнец indicator, wherever it stands: on the page and in a row of the shelf. What
#: is asked of it is the state it names, not the layout around it.
TWIN = re.compile(r'data-twin="(?P<state>[^"]+)"')

#: An image reference the близнец makes and nothing answers — named in the attribute, so
#: that "something is unresolved" and "this is what is unresolved" are two different
#: assertions.
UNMATCHED = re.compile(r'data-unmatched="(?P<reference>[^"]+)"')


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Uploaded files go into a temporary directory rather than into the working copy.

    It stands here as its own copy instead of being imported: a fixture is auto-applied
    only in the module where it is declared.
    """
    settings.MEDIA_ROOT = tmp_path


def markdown(text="# Акт\n\nТекст акта.\n", name="акт.md"):
    """A близнец as it arrives: the документ's content, already converted by someone else."""
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/markdown")


def picture(name="p3-img1.png"):
    """A схема pulled out of the документ, named the way the markdown refers to it."""
    return SimpleUploadedFile(name, png(name), content_type="image/png")


def page_of(client, document):
    response = client.get(reverse("documents:document_detail", args=[document.pk]))
    return response, response.content.decode()


def attach(client, document, twin=None, images=()):
    """Attach a близнец the way the form on the документ's page sends it."""
    submission = {"submitted": "twin", "markdown": twin if twin is not None else markdown()}
    if images:
        submission["images"] = list(images)
    return client.post(reverse("documents:document_detail", args=[document.pk]), submission)


def remove(client, document):
    """Take the близнец off — the same address, and the submission names itself."""
    return client.post(
        reverse("documents:document_detail", args=[document.pk]), {"submitted": "twin-removal"}
    )


def twin_state(page):
    """What the indicator says about the близнец: attached, or none."""
    return TWIN.search(page)["state"]


def row_of(shelf, document):
    """A row of the shelf as it stands in the markup: the indicator is an attribute, and the
    section's own reading strips the tags off before it hands a row over."""
    return next(row["cells"] for row in ROW.finditer(shelf) if row["key"] == str(document.pk))


def unmatched_on(page):
    """The image references reported as unresolved, as the markdown wrote them."""
    return [found["reference"] for found in UNMATCHED.finditer(page)]


def attach_form(page):
    """The form for attaching a близнец — or nothing, if it is not offered."""
    return page if 'data-attach="twin"' in page else None


def stored_files(settings):
    """Everything lying under `MEDIA_ROOT` — what a replacement must not accumulate."""
    return {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}


# What the документ says about its близнец


def test_a_document_without_a_twin_says_so_on_its_page(client, member, downtown):
    """Having none is the ordinary state, and it is stated: a документ the ИИ-управляющий
    cannot read must be identifiable."""
    document = make_document(downtown, "Акт без близнеца")
    client.force_login(member)

    _, page = page_of(client, document)

    assert twin_state(page) == "none"


def test_the_shelf_says_the_same_about_a_document_without_a_twin(client, member, downtown):
    """The page and the row must not diverge: the shelf is where the shortfall is counted."""
    document = make_document(downtown, "Акт без близнеца")
    client.force_login(member)

    _, shelf = section(client)

    assert twin_state(row_of(shelf, document)) == "none"


def test_an_attached_twin_is_shown_on_the_page_and_in_the_row(
    client, administrator, downtown
):
    """One близнец, two screens: what the page says about it the shelf says too."""
    document = make_document(downtown, "Акт разграничения")
    client.force_login(administrator)

    attach(client, document)

    _, page = page_of(client, document)
    assert twin_state(page) == "attached"
    _, shelf = section(client)
    assert twin_state(row_of(shelf, document)) == "attached"


# Attaching


def test_an_administrator_attaches_a_twin_from_the_documents_own_page(
    client, administrator, downtown
):
    """A one-off conversion must not require a batch: it is attached where it is read."""
    document = make_document(downtown, "Акт разграничения")
    client.force_login(administrator)

    response = attach(client, document, markdown("# Акт\n\nРазграничение.\n"))

    assert response.status_code == 302
    assert response["Location"] == reverse("documents:document_detail", args=[document.pk])
    assert document.twin.markdown.read().decode("utf-8") == "# Акт\n\nРазграничение.\n"


def test_the_images_the_twin_refers_to_are_attached_with_it(client, administrator, downtown):
    """The схемы inside a документ are the half of it the markdown cannot carry."""
    document = make_document(downtown, "Акт со схемой")
    client.force_login(administrator)

    attach(
        client,
        document,
        markdown("![](p3-img1.png)\n\n![](p4-img2.png)\n"),
        [picture("p3-img1.png"), picture("p4-img2.png")],
    )

    assert sorted(document.twin.images.values_list("name", flat=True)) == [
        "p3-img1.png",
        "p4-img2.png",
    ]


def test_an_image_reference_with_no_matching_image_is_reported_on_screen(
    client, administrator, downtown
):
    """The finding this screen exists for: one broken reference and the модель reads the
    документ without its схема, never learning that it did."""
    document = make_document(downtown, "Акт с оборванной ссылкой")
    client.force_login(administrator)

    attach(client, document, markdown("![](p3-img1.png)\n\n![](p9-img7.png)\n"), [picture()])

    _, page = page_of(client, document)
    assert unmatched_on(page) == ["p9-img7.png"]


def test_an_image_nothing_refers_to_does_not_make_the_twin_incomplete(
    client, administrator, downtown
):
    """Completeness is asked of the references, not of the pictures: a схема attached and
    never mentioned costs a file, whereas a reference with nothing behind it costs an
    answer."""
    document = make_document(downtown, "Акт с лишней картинкой")
    client.force_login(administrator)

    attach(client, document, markdown("![](p3-img1.png)\n"), [picture(), picture("p8-img4.png")])

    _, page = page_of(client, document)
    assert unmatched_on(page) == []
    assert document.twin.unmatched_images == []


def test_a_reference_that_names_a_folder_is_reported_rather_than_resolved(
    client, administrator, downtown
):
    """Pictures are addressed by name and not by URL (ADR 0007), and the rule holds even
    when being lenient would be easy.

    `images/p3-img1.png` names no attached picture. Dropping the folder here would make the
    близнец complete only at this moment: whoever later shows it to a human resolves the
    same markdown against the same names, finds nothing, and by then nobody is being told.
    """
    document = make_document(downtown, "Акт со схемой в папке")
    client.force_login(administrator)

    attach(client, document, markdown("![](images/p3-img1.png)\n"), [picture("p3-img1.png")])

    _, page = page_of(client, document)
    assert unmatched_on(page) == ["images/p3-img1.png"]


def test_a_refused_attachment_leaves_no_pictures_in_the_store(
    client, administrator, downtown, settings
):
    """All or nothing reaches the store too (ADR 0011): what a refused attach wrote, if it
    wrote anything, must not stay behind as a file nothing points at."""
    document = make_document(downtown, "Акт со схемой")
    client.force_login(administrator)

    attach(
        client,
        document,
        markdown("![](p3-img1.png)\n"),
        [picture(), SimpleUploadedFile("p4-img2.png", b"MZ\x90\x00 not a picture")],
    )

    assert stored_files(settings) == set()


def test_a_twin_that_is_not_text_is_refused_with_the_reason_on_the_form(
    client, administrator, downtown
):
    """A близнец is text: what does not decode is not what the ИИ-управляющий would read."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)

    response = attach(client, document, SimpleUploadedFile("акт.md", png("не текст")))

    assert response.status_code == 200
    assert not DocumentTwin.objects.exists()
    assert attach_form(response.content.decode()) is not None


def test_a_picture_of_an_unaccepted_format_takes_the_whole_twin_with_it(
    client, administrator, downtown
):
    """Not partial success, unlike a batch: a batch is a hundred independent папок, and a
    близнец is one thing — stored by halves it would be exactly the incomplete близнец the
    references are parsed to prevent."""
    document = make_document(downtown, "Акт со схемой")
    client.force_login(administrator)

    response = attach(
        client,
        document,
        markdown("![](p3-img1.png)\n"),
        [picture(), SimpleUploadedFile("p4-img2.png", b"MZ\x90\x00 not a picture")],
    )

    assert response.status_code == 200
    assert not DocumentTwin.objects.exists()
    assert not TwinImage.objects.exists()


# Replacing


def test_replacing_a_twin_leaves_none_of_the_previous_images_behind(
    client, administrator, downtown, settings
):
    """A better conversion supersedes a worse one whole — rows and files together."""
    document = make_document(downtown, "Акт со схемой")
    client.force_login(administrator)
    attach(client, document, markdown("![](p3-img1.png)\n"), [picture()])
    of_the_first = stored_files(settings)

    attach(client, document, markdown("![](p4-img2.png)\n"), [picture("p4-img2.png")])

    assert DocumentTwin.objects.count() == 1
    assert list(TwinImage.objects.values_list("name", flat=True)) == ["p4-img2.png"]
    assert not (of_the_first & stored_files(settings))


def test_a_replacement_is_read_back_where_it_was_attached(client, administrator, downtown):
    """The reloaded page is the confirmation: the new conversion is the one on screen."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    attach(client, document, markdown("# Первый близнец\n"))

    attach(client, document, markdown("# Второй близнец\n"))

    document.refresh_from_db()
    assert document.twin.markdown.read().decode("utf-8") == "# Второй близнец\n"


# Removing


def test_removing_a_twin_leaves_the_document_and_its_original_untouched(
    client, administrator, downtown, settings
):
    """A bad conversion is withdrawn; the scan it was made from stays where it was."""
    document = make_document(
        downtown, "Акт со сканом", file_uri=SimpleUploadedFile("акт.pdf", pdf("скан"))
    )
    original = Path(settings.MEDIA_ROOT) / document.file_uri.name
    client.force_login(administrator)
    attach(client, document, markdown("![](p3-img1.png)\n"), [picture()])

    response = remove(client, document)

    assert response.status_code == 302
    document.refresh_from_db()
    assert not DocumentTwin.objects.exists()
    assert not TwinImage.objects.exists()
    assert document.title == "Акт со сканом"
    assert original.exists()
    assert stored_files(settings) == {original}


def test_after_a_removal_the_document_says_it_has_no_twin_again(
    client, administrator, downtown
):
    """Withdrawn is not hidden: the документ goes back to being one the ИИ cannot read."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    attach(client, document)

    remove(client, document)

    _, page = page_of(client, document)
    assert twin_state(page) == "none"


# Reading it back


def test_a_twin_is_downloaded_through_the_documents_chokepoint(
    client, member, administrator, downtown
):
    """A сотрудник checks what the ИИ-управляющий would be reading — through the one
    chokepoint, with the same sandboxing as the original file."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    attach(client, document, markdown("# Акт\n\nТекст.\n"))
    client.force_login(member)

    response = client.get(reverse("documents:document_twin", args=[document.pk]))

    assert response.status_code == 200
    assert b"".join(response.streaming_content).decode("utf-8") == "# Акт\n\nТекст.\n"
    assert response["Content-Security-Policy"] == "sandbox"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_the_page_leads_to_the_twin_it_says_is_attached(client, administrator, downtown):
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    attach(client, document)

    _, page = page_of(client, document)

    assert reverse("documents:document_twin", args=[document.pk]) in page


def test_a_document_without_a_twin_offers_no_download_of_one(client, member, downtown):
    """A link to nothing is a broken link, and the address answers accordingly."""
    document = make_document(downtown, "Акт без близнеца")
    client.force_login(member)

    _, page = page_of(client, document)
    response = client.get(reverse("documents:document_twin", args=[document.pk]))

    assert reverse("documents:document_twin", args=[document.pk]) not in page
    assert response.status_code == 404


def test_another_organisations_twin_is_missing_rather_than_forbidden(client, member, central):
    """The answer must not confirm that another client's близнец exists (ADR 0006)."""
    theirs = make_document(central, "Чужой акт")
    DocumentTwin.objects.create(document=theirs, markdown=markdown("# Чужой\n", "чужой.md"))
    client.force_login(member)

    response = client.get(reverse("documents:document_twin", args=[theirs.pk]))

    assert response.status_code == 404


def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, downtown):
    """Before signing in nothing is read — not even that a близнец exists."""
    document = make_document(downtown, "Акт")

    response = client.get(reverse("documents:document_twin", args=[document.pk]))

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


# Who may attach


def test_an_administrator_of_the_organisation_is_offered_the_attaching(
    client, administrator, downtown
):
    document = make_document(downtown, "Акт")
    client.force_login(administrator)

    _, page = page_of(client, document)

    assert attach_form(page) is not None


def test_a_member_without_the_flag_is_offered_no_attaching_at_all(client, member, downtown):
    """An action an employee cannot perform is not offered to them either (ADR 0005)."""
    document = make_document(downtown, "Акт")
    client.force_login(member)

    _, page = page_of(client, document)

    assert attach_form(page) is None


def test_a_member_without_the_flag_is_offered_no_replacing_or_removing_either(
    client, member, administrator, downtown
):
    """Not only the empty slot is withheld: a близнец already attached is read, not edited."""
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    attach(client, document)
    client.force_login(member)

    _, page = page_of(client, document)

    assert attach_form(page) is None
    assert "twin-removal" not in page


def test_a_member_without_the_flag_is_refused_even_by_posting_directly(
    client, member, downtown
):
    """The right is checked on the request, not only on what the screen offers."""
    document = make_document(downtown, "Акт")
    client.force_login(member)

    response = attach(client, document)

    assert response.status_code == 403
    assert not DocumentTwin.objects.exists()


def test_a_member_without_the_flag_cannot_remove_a_twin_by_posting_directly(
    client, member, administrator, downtown
):
    document = make_document(downtown, "Акт")
    client.force_login(administrator)
    attach(client, document)
    client.force_login(member)

    response = remove(client, document)

    assert response.status_code == 403
    assert DocumentTwin.objects.count() == 1


def test_administering_one_organisation_does_not_administer_another(
    client, administrator, central
):
    """The right belongs to the pair "employee + organisation" (ADR 0005), and another
    client's документ is missing rather than forbidden (ADR 0006)."""
    theirs = make_document(central, "Чужой акт")
    client.force_login(administrator)

    response = attach(client, theirs)

    assert response.status_code == 404
    assert not DocumentTwin.objects.exists()
