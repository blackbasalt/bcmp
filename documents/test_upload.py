"""Batch upload and the download of the original — how an archive gets into BCMP and back out.

The seam is the same as on the other screens — the HTTP boundary: the tests submit the
form of the "Документы" section with the test client on behalf of an employee with a known
membership, and check what is observable — how many documents were stored, what is said
about the files that were not, which code a request for a file answers with and which
headers it carries.

There is no second seam below HTTP: what a single file must be to be stored is observable
as the refusal the screen prints, and the limits are driven through the form like
everything else. The one place a constant is read rather than typed out is the submission
limit — two hundred files written into a test is two hundred files nobody would notice
changing.

The foothold in the markup is the `data-upload` attribute on the form itself: it shows
whether the upload is offered, and to an employee without the administrator flag it is not
offered at all.
"""

import hashlib
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documents import uploaded_files
from documents.models import Document, DocumentLink
from parties.models import OrgMembership

from .test_section import documents_on, section, stated

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Uploaded files go into a temporary directory rather than into the working copy.

    It stands here as its own copy instead of being imported: a fixture is auto-applied
    only in the module where it is declared.
    """
    settings.MEDIA_ROOT = tmp_path


def pdf(text="скан"):
    """A file the size of a scan and the shape of a PDF: it is the first bytes that matter."""
    return f"%PDF-1.4\n{text}".encode()


def png(text="снимок"):
    """A photograph of a signed act — what a phone in a building produces."""
    return b"\x89PNG\r\n\x1a\n" + text.encode()


def jpeg(text="снимок"):
    return b"\xff\xd8\xff\xe0" + text.encode()


def sent(name, content=None):
    """A file as it arrives in a submission: a scan by default, named as in a folder."""
    return SimpleUploadedFile(name, pdf(name) if content is None else content)


def upload(client, *files, kind=Document.Kind.ACT, building=None):
    """Submit the batch — to the same address the section is opened at."""
    submission = {"files": list(files), "kind": kind}
    if building is not None:
        submission["building"] = str(building.pk)
    return client.post(reverse("documents:document_list"), submission)


def upload_form(page):
    """The upload form on the screen — or nothing, if it is not offered."""
    return page if 'data-upload="documents"' in page else None


def said_to(client):
    """What the section says after a batch: the reloaded screen carries the report."""
    _, page = section(client)
    return stated(page)


def file_url(document):
    """The address the original is downloaded from — through the documents chokepoint."""
    return reverse("documents:document_file", args=[document.pk])


def titles():
    """The documents on the shelf by title — what a batch left behind."""
    return sorted(Document.objects.values_list("title", flat=True))


# Who may upload


def test_an_administrator_of_the_organisation_is_offered_the_upload(client, administrator):
    """Moving the management company's archive no longer requires the Django admin."""
    client.force_login(administrator)

    _, page = section(client)

    assert upload_form(page) is not None


def test_a_member_without_the_flag_is_offered_no_upload_form_at_all(client, member):
    """An action an employee cannot perform is not offered to them either (ADR 0005)."""
    client.force_login(member)

    _, page = section(client)

    assert upload_form(page) is None


def test_a_member_without_the_flag_is_refused_even_by_posting_directly(client, member):
    """It is not only the form that is withheld: the right is checked on the request itself."""
    client.force_login(member)

    response = upload(client, sent("акт.pdf"))

    assert response.status_code == 403
    assert Document.objects.count() == 0


def test_an_anonymous_upload_is_sent_to_the_login_screen(client):
    """Before signing in nothing is written — just as nothing is read."""
    response = upload(client, sent("акт.pdf"))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]
    assert Document.objects.count() == 0


def test_administering_one_organisation_does_not_administer_another(
    client, django_user_model, downtown, central, make_building
):
    """Administratorship belongs to the pair "employee + organisation" (ADR 0005).

    The same employee maintains one client's data and stays an ordinary reader at another:
    the second client's papers are on their screen, and the second client's building is not
    among the buildings they may upload to — nor does it become one by being named in the
    submission.
    """
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=False)
    theirs = make_building(central, "ctr", "Central")
    their_document = Document.objects.create(
        org=central, kind=Document.Kind.ACT, title="Чужой акт"
    )
    client.force_login(user)

    response = upload(client, sent("акт.pdf"), building=theirs)

    assert response.status_code == 200
    assert Document.objects.filter(org=downtown).count() == 0
    _, page = section(client)
    assert documents_on(page) == [str(their_document.pk)]


# Whose shelf the batch lands on


def test_the_batch_lands_on_the_shelf_of_the_chosen_building(
    client, django_user_model, downtown, central, make_building
):
    """The organisation is not asked for: the building already says whose documents these are."""
    user = django_user_model.objects.create_user("group")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=True)
    theirs = make_building(central, "ctr", "Central")
    client.force_login(user)

    upload(client, sent("акт.pdf"), building=theirs)

    assert Document.objects.get().org_id == central.pk


def test_a_batch_without_a_building_from_an_administrator_of_two_clients_is_refused(
    client, django_user_model, downtown, central
):
    """A document belongs to an organisation, and here nothing says which one.

    For whoever maintains a single client the answer is their client; for whoever maintains
    two, a charter without a building could land on either shelf — and a document on the
    wrong shelf is shown to the wrong client (ADR 0006). So the batch is refused rather
    than guessed at (ADR 0010).
    """
    user = django_user_model.objects.create_user("group")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=True)
    client.force_login(user)

    response = upload(client, sent("Устав.pdf"))

    assert response.status_code == 200
    assert Document.objects.count() == 0
    assert "БЦ" in stated(response.content.decode())


def test_a_building_is_offered_under_the_name_it_is_known_by(client, administrator, manhattan):
    """«Manhattan», not «man (building)»: the uploader knows the building by its name."""
    client.force_login(administrator)

    _, page = section(client)

    assert str(manhattan.pk) in page
    assert ">Manhattan</option>" in page
    assert "man (building)" not in page


def test_a_batch_without_a_kind_chosen_stores_nothing(client, administrator):
    """The вид is not filled in for the sender: a folder of актов filed as проектная
    документация is not wrong on any screen, it is simply not where it is looked for."""
    client.force_login(administrator)

    response = upload(client, sent("акт.pdf"), kind="")

    assert response.status_code == 200
    assert Document.objects.count() == 0


# What a batch does


def test_a_batch_stores_every_file_with_the_kind_chosen_once(client, administrator, downtown):
    """Hundreds of scans arrive in one submission, and the kind is stated for all of them.

    A photograph among them is as ordinary as a scan: an act is signed on paper and
    photographed on a phone as often as it is put through a scanner.
    """
    client.force_login(administrator)

    upload(
        client,
        sent("акт1.pdf"),
        sent("акт2.pdf"),
        sent("акт3.jpg", png("снятый акт")),
        kind=Document.Kind.ACT,
    )

    assert Document.objects.count() == 3
    assert {document.kind for document in Document.objects.all()} == {Document.Kind.ACT}
    assert {document.org_id for document in Document.objects.all()} == {downtown.pk}


def test_the_title_is_taken_from_the_file_name(client, administrator):
    """Nobody types out hundreds of titles: the folder has already named the files."""
    client.force_login(administrator)

    upload(client, sent("Акт разграничения балансовой принадлежности.pdf"))

    assert Document.objects.get().title == "Акт разграничения балансовой принадлежности"


def test_the_particulars_are_left_for_later(client, administrator):
    """Number, issue date, issuer, deadline and revision are filled in afterwards."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf"))
    document = Document.objects.get()

    assert not document.doc_no
    assert document.issued_at is None
    assert document.issuer_party_id is None
    assert document.valid_until is None
    assert not document.revision


def test_the_chosen_building_is_recorded_as_a_link_of_type_space(
    client, administrator, manhattan
):
    """The building is chosen once for the whole batch and applies to every file (ADR 0008)."""
    client.force_login(administrator)

    upload(client, sent("акт1.pdf"), sent("акт2.pdf"), building=manhattan)

    links = DocumentLink.objects.all()
    assert links.count() == 2
    assert {link.entity_type for link in links} == {DocumentLink.EntityType.SPACE}
    assert {link.entity_id for link in links} == {manhattan.pk}


def test_a_link_is_stored_without_any_seeded_dictionary_rows(client, administrator, manhattan):
    """The role is not asked for: whoever moves a folder of scans does not choose one.

    And storing a document must not depend on a dictionary having been seeded — an empty
    `DictDocumentRole` table is the state of a fresh installation.
    """
    client.force_login(administrator)

    upload(client, sent("акт.pdf"), building=manhattan)

    assert DocumentLink.objects.get().role_id is None


def test_a_batch_without_a_building_stores_documents_linked_to_nothing(client, administrator):
    """The charter and the licence belong to no building at all (ADR 0008)."""
    client.force_login(administrator)

    upload(client, sent("Устав.pdf"))

    assert Document.objects.count() == 1
    assert DocumentLink.objects.count() == 0


def test_the_content_hash_is_computed_on_upload(client, administrator):
    """The hash is what the next batch's duplicates are recognised by, so it is stored at once."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf", pdf("один и тот же файл")))

    assert Document.objects.get().file_hash == hashlib.sha256(pdf("один и тот же файл")).hexdigest()


def test_the_stored_file_can_be_read_back(client, administrator):
    """A batch that stored a row and lost the file would be worse than a refusal."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf", pdf("содержимое")))

    assert Document.objects.get().file_uri.read() == pdf("содержимое")


def test_the_number_of_files_stored_is_stated(client, administrator):
    """After a batch of hundreds "did it go through" is the question asked first."""
    client.force_login(administrator)

    upload(client, sent("акт1.pdf"), sent("акт2.pdf"), sent("акт3.pdf"))

    assert "Загружено 3 файла" in said_to(client)


def test_a_single_stored_file_is_counted_in_the_singular(client, administrator):
    """«Загружено 1 файлов» reads as a glitch on the screen, not as a single file."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf"))

    assert "Загружен 1 файл" in said_to(client)


def test_the_uploaded_documents_are_on_the_screen_the_form_stands_on(client, administrator):
    """The reloaded section is the confirmation: the batch is looked at where it was sent from."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf"))

    _, page = section(client)
    assert documents_on(page) == [str(Document.objects.get().pk)]


# What the batch takes and what it leaves


def test_a_batch_where_one_file_is_rejected_stores_the_rest(client, administrator):
    """All-or-nothing would mean re-uploading ninety-nine good files because of one bad one."""
    client.force_login(administrator)

    upload(
        client,
        sent("акт1.pdf"),
        sent("таблица.xlsx", b"PK\x03\x04nonsense"),
        sent("акт2.pdf"),
    )

    assert titles() == ["акт1", "акт2"]


def test_a_rejected_file_is_named_on_the_screen_with_the_reason(client, administrator):
    """A count of the refused says nothing about which of the hundred to send again."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf"), sent("таблица.xlsx", b"PK\x03\x04nonsense"))

    said = said_to(client)
    assert "таблица.xlsx" in said
    assert ".xlsx" in said
    assert "акт.pdf" not in said


def test_a_batch_over_the_submission_limit_stores_nothing(client, administrator):
    """An oversized batch is split by whoever sends it, not applied by halves."""
    client.force_login(administrator)
    files = [sent(f"акт{number}.pdf") for number in range(uploaded_files.BATCH_LIMIT + 1)]

    response = upload(client, *files)

    assert response.status_code == 200
    assert Document.objects.count() == 0
    assert "200" in stated(response.content.decode())


def test_a_batch_at_the_submission_limit_is_stored(client, administrator):
    """The limit is the largest batch that goes through, not the first one refused."""
    client.force_login(administrator)
    files = [sent(f"акт{number}.pdf") for number in range(uploaded_files.BATCH_LIMIT)]

    upload(client, *files)

    assert Document.objects.count() == uploaded_files.BATCH_LIMIT


def test_a_file_already_stored_is_reported_by_the_document_it_is_stored_as(
    client, administrator
):
    """Overlapping folders are the norm in an archive transfer: a duplicate is a message.

    It names the document the file is already stored as — otherwise the reader is left to
    search for it themselves.
    """
    client.force_login(administrator)
    upload(client, sent("Акт разграничения.pdf", pdf("одно и то же")))

    response = upload(client, sent("копия акта.pdf", pdf("одно и то же")), sent("новый.pdf"))

    assert response.status_code == 302
    assert titles() == ["Акт разграничения", "новый"]
    said = said_to(client)
    assert "копия акта.pdf" in said
    assert "Акт разграничения" in said


def test_a_duplicate_of_another_organisations_file_is_not_reported(
    client, administrator, central, downtown
):
    """The shelf a duplicate is looked for on is one's own: naming another client's document
    would tell one client what another has stored (ADR 0006)."""
    Document.objects.create(
        org=central,
        kind=Document.Kind.ACT,
        title="Чужой акт",
        file_hash=hashlib.sha256(pdf("одно и то же")).hexdigest(),
    )
    client.force_login(administrator)

    upload(client, sent("акт.pdf", pdf("одно и то же")))

    assert Document.objects.filter(org=downtown).count() == 1
    assert "Чужой акт" not in said_to(client)


# What a single file must be


def test_a_format_that_is_not_accepted_is_refused_with_its_format_named(client, administrator):
    """The reason names the format so the sender knows what to convert."""
    client.force_login(administrator)

    upload(client, sent("договор.docx", b"PK\x03\x04nonsense"))

    said = said_to(client)
    assert ".docx" in said
    assert "PDF" in said
    assert Document.objects.count() == 0


def test_a_file_pretending_to_be_a_pdf_by_its_name_is_refused(client, administrator):
    """The format is decided by the content: a renamed executable is not a scan.

    And the refusal says so, because «формат .pdf не принимается» would send its owner off
    to convert a file that already carries the right extension and is something else.
    """
    client.force_login(administrator)

    upload(client, sent("акт.pdf", b"MZ\x90\x00" + b"\x00" * 64))

    said = said_to(client)
    assert "акт.pdf" in said
    assert "не PDF" in said
    assert Document.objects.count() == 0


def test_a_file_over_the_limit_is_refused_with_the_limit_stated(client, administrator):
    """Without the limit in the refusal the sender only learns that it was «too big».

    Fifty megabytes really are sent: the limit is what a scan of a whole project folder
    runs into, and a rule checked on a made-up number would not be this rule.
    """
    client.force_login(administrator)
    oversized = sent("огромный.pdf", pdf("скан") + b"\x00" * uploaded_files.FILE_LIMIT)

    upload(client, oversized, sent("акт.pdf"))

    said = said_to(client)
    assert "огромный.pdf" in said
    assert "50" in said
    assert titles() == ["акт"]


def test_an_empty_file_is_refused_as_empty_rather_than_as_a_wrong_format(client, administrator):
    """A zero-byte file is what a failed copy leaves behind, and that is what it is called."""
    client.force_login(administrator)

    upload(client, sent("акт.pdf", b""))

    assert "пустой" in said_to(client)
    assert Document.objects.count() == 0


def test_a_scan_and_a_photograph_both_go_through(client, administrator):
    """PDF and images — what a scanner and a phone produce, and nothing that executes."""
    client.force_login(administrator)

    upload(client, sent("скан.pdf", pdf()), sent("снимок.png", png()), sent("снимок.jpg", jpeg()))

    assert titles() == ["скан", "снимок", "снимок"]


# The original file


def test_the_original_is_downloaded_through_the_documents_chokepoint(client, administrator):
    """Getting the archive back out is the other half of getting it in."""
    client.force_login(administrator)
    upload(client, sent("акт.pdf", pdf("содержимое")))

    response = client.get(file_url(Document.objects.get()))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == pdf("содержимое")


def test_the_file_is_served_so_that_it_cannot_act_as_part_of_the_site(client, administrator):
    """The file comes from whoever uploaded it and is served from our own domain.

    The same sandboxing as the plan drawings: without our origin and without type sniffing.
    """
    client.force_login(administrator)
    upload(client, sent("акт.pdf"))

    response = client.get(file_url(Document.objects.get()))

    assert "sandbox" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_another_organisations_file_is_missing_rather_than_forbidden(
    client, administrator, central
):
    """A 403 would confirm that the document exists — the leak the chokepoint is for (ADR 0006)."""
    theirs = Document.objects.create(org=central, kind=Document.Kind.ACT, title="Чужой акт")
    client.force_login(administrator)

    assert client.get(file_url(theirs)).status_code == 404


def test_an_anonymous_request_for_a_file_is_sent_to_the_login_screen(client, downtown):
    """A file is as much a read path as a screen."""
    document = Document.objects.create(org=downtown, kind=Document.Kind.ACT, title="Акт")

    response = client.get(file_url(document))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_the_file_lands_in_the_same_protected_place_as_the_plan_drawings(
    settings, client, administrator, downtown
):
    """Under `MEDIA_ROOT`, which nothing but the application reads, and laid out by
    organisation — the directory is the last place a file says whose it is."""
    client.force_login(administrator)
    upload(client, sent("акт.pdf"))

    stored = Path(Document.objects.get().file_uri.path)

    assert stored.is_relative_to(Path(settings.MEDIA_ROOT))
    assert stored.parent.name == str(downtown.pk)


def test_the_project_publishes_no_address_of_its_own_for_uploaded_files():
    """`MEDIA_URL` is not configured — and there is no nginx `/media/` location either.

    Django serves nothing out of `MEDIA_ROOT` by itself, so the only way to a document is
    the view that goes through the chokepoint. This is asked of the settings module rather
    than of `settings.MEDIA_URL`: Django reads that one back as the script prefix «/» even
    when it was never set, and the question here is whether the project set it.
    """
    from bcmp import settings as project_settings

    assert not hasattr(project_settings, "MEDIA_URL")


def test_the_row_of_a_stored_document_offers_its_file(client, administrator):
    """The download stands where the document is read about, not at a guessed address."""
    client.force_login(administrator)
    upload(client, sent("акт.pdf"))

    _, page = section(client)

    assert file_url(Document.objects.get()) in page


def test_a_document_without_a_file_offers_no_download(client, member, downtown):
    """Documents created in the admin have no file, and a link to nothing is a broken link."""
    Document.objects.create(org=downtown, kind=Document.Kind.ACT, title="Акт без файла")
    client.force_login(member)

    _, page = section(client)

    assert file_url(Document.objects.get()) not in page
