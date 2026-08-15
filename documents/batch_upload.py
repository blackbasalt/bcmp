"""The batch upload form — how hundreds of scans get off a network drive and into BCMP.

It asks for three things for the whole submission: the files, the вид документа and the
БЦ — and the last one may be left unset, because the устав and the лицензия belong to no
building. The path of a file is not parsed at all (ADR 0008): the management company's
folders predate BCMP and match neither `code` nor `name`, so a guess from a folder name
would attach a document to the wrong building — worse than attaching it to none.

The название comes from the file name; номер, дата выдачи, кем выдан, срок and ревизия
stay empty and are filled in later. Whoever carries the archive across knows what the
folder was about, and nothing else about the papers inside it.

The batch is partial-success: what took, took. Good files are stored and rejected ones are
listed by name with a reason, because with a hundred files "all or nothing" means
re-uploading ninety-nine good ones because of one bad one. Only the submission limit is
checked before anything at all is stored — an oversized batch is split by whoever sends
it, not applied by halves.
"""

from dataclasses import dataclass, field

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from building_passport.models import Space
from parties.models import Org

from .models import Document, DocumentLink
from .uploaded_files import (
    ACCEPTED_IN_A_DIALOG,
    ACCEPTED_NAMES,
    BATCH_LIMIT,
    FILE_LIMIT,
    MEGABYTE,
    digest_of,
    head_of,
    refusal_for,
    title_from,
)


@dataclass(frozen=True)
class Submission:
    """The three answers a batch carries, and the organisation they land on.

    They travel together because they are one thing — what this submission is (ADR 0008):
    the вид документа and the БЦ are chosen once for the whole folder, and the organisation
    follows from the building rather than being asked for on top of it.
    """

    kind: str
    org: object
    building: object


@dataclass
class BatchReport:
    """What became of a submission: what was stored, what was already there, what was not taken.

    A file that was not stored is kept by name and not merely counted: a count says nothing
    about which of the hundred to send again.
    """

    stored: list = field(default_factory=list)
    #: The files whose content is already on the shelf, each with the document it is stored
    #: as. Not a refusal — a message: overlapping folders are the norm in an archive
    #: transfer, and the sender's next action is to look at that document, not to resend.
    already_stored: list = field(default_factory=list)
    #: The files that were not taken, each with the reason.
    refused: list = field(default_factory=list)


class MultipleFileInput(forms.ClearableFileInput):
    """A file input that takes more than one file — a folder is chosen in one go."""

    allow_multiple_selected = True


class SubmittedFiles(forms.FileField):
    """The files of one submission, taken as they came.

    A file is not judged here, only counted: what is wrong with one file must not refuse
    the other ninety-nine, and Django's own per-file checks — an empty file among them —
    would do exactly that by failing the whole field. Every file is judged one at a time
    while being stored, and the submission limit is the one thing decided over the batch as
    a whole, before anything is written.
    """

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, list) else ([data] if data else [])
        if not files:
            raise ValidationError("Выберите файлы: отправка без них ничего не сохраняет.")
        if len(files) > BATCH_LIMIT:
            raise ValidationError(
                f"В одной отправке не больше {BATCH_LIMIT} файлов, а прислано {len(files)}. "
                f"Ничего не сохранено — пачку нужно разделить и отправить частями."
            )
        return files


class BuildingChoice(forms.ModelChoiceField):
    """The BCs on offer, named the way they are named everywhere else.

    A space says itself as «man (building)» — the code and the type, which is what a row in
    the admin needs. Whoever is uploading a folder knows the building as «Manhattan», and
    a list of codes is a list they have to translate before every batch. The code is left
    for a building with no name at all: it is worse than a name, but it is what there is.
    """

    def label_from_instance(self, building):
        return building.name or building.code


class DocumentBatchForm(forms.Form):
    """Files, вид документа and БЦ — one set of answers for the whole submission.

    The BC comes from a list rather than from the file paths, and the list holds only the
    buildings whose data this employee maintains (ADR 0005): a building missing from it
    does not become available by being named in the request either.
    """

    files = SubmittedFiles(
        label="Файлы",
        # What may be sent and how much of it is said once, here, from the same place that
        # decides it: the hint under the field, the filter in the file dialog and the
        # refusal a rejected file gets must not be three different accounts of one rule.
        help_text=(
            f"{ACCEPTED_NAMES}, до {FILE_LIMIT // MEGABYTE} МБ каждый и до {BATCH_LIMIT} "
            f"файлов за раз. Название документа берётся из имени файла."
        ),
        widget=MultipleFileInput(attrs={"accept": ACCEPTED_IN_A_DIALOG}),
    )
    # The list opens on nothing chosen. A вид filled in for the sender would be accepted
    # without a glance — and unlike a wrong date, a folder of «актов» filed as «проектная
    # документация» is not visible on any screen afterwards: it is simply not where it is
    # looked for. The same reasoning as the plan's date, which has no default either
    # (ADR 0005).
    kind = forms.ChoiceField(
        choices=[("", "Выберите вид документа"), *Document.Kind.choices],
        label="Вид документа",
    )
    building = BuildingChoice(
        queryset=Space.objects.none(),
        required=False,
        label="БЦ",
        # The empty choice is not a technicality but the ordinary case: the charter, the
        # licence and a contract covering every site belong to no building.
        empty_label="Без привязки к зданию",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["building"].queryset = Space.objects.buildings_administered_by(
            user
        ).order_by("name", "code")

    def clean(self):
        """Whose shelf the batch lands on (ADR 0010).

        The building names the organisation when there is one; without a building it is
        named by the membership of whoever is uploading, which for an administrator of a
        single client is unambiguous. Only an administrator of two who names no building
        leaves nothing to derive it from, and then the batch is refused rather than guessed
        at: a document on the wrong shelf is a document shown to the wrong client
        (ADR 0006).
        """
        cleaned = super().clean()
        building = cleaned.get("building")
        if building is not None:
            cleaned["org"] = building.org
            return cleaned
        administered = list(Org.objects.administered_by(self.user)[:2])
        if len(administered) != 1:
            raise ValidationError(
                "Выберите БЦ: вы ведёте несколько организаций, и без здания непонятно, "
                "чьи это документы."
            )
        cleaned["org"] = administered[0]
        return cleaned

    def save(self):
        """Store what took. The report says the rest."""
        return store_batch(
            self.cleaned_data["files"],
            Submission(
                kind=self.cleaned_data["kind"],
                org=self.cleaned_data["org"],
                building=self.cleaned_data.get("building"),
            ),
        )


def store_batch(files, submission):
    """Store the files of one submission, one at a time, and report on each of them.

    One at a time and not in one transaction: the point of the batch is that a bad file
    among a hundred good ones costs the sender that one file and not the afternoon.
    """
    report = BatchReport()
    for uploaded in files:
        refusal = refusal_for(uploaded.name, uploaded.size, head_of(uploaded))
        if refusal is not None:
            report.refused.append((uploaded.name, refusal))
            continue
        digest = digest_of(uploaded)
        # The shelf a duplicate is looked for on is the one the file would land on: the
        # same content in another client's organisation is another client's document, and
        # naming it would tell one what the other has stored (ADR 0006).
        already = Document.objects.filter(org=submission.org, file_hash=digest).first()
        if already is not None:
            report.already_stored.append((uploaded.name, already))
            continue
        report.stored.append(_store(uploaded, submission, digest))
    return report


def _store(uploaded, submission, digest):
    """One document and its link appear together: a link to a document that was not stored
    would point at nothing."""
    with transaction.atomic():
        document = Document.objects.create(
            org=submission.org,
            kind=submission.kind,
            title=title_from(uploaded.name),
            file_uri=uploaded,
            file_hash=digest,
        )
        if submission.building is not None:
            # `space` is the only one of the nine entity types this stage uses; the other
            # eight point at empty or non-existent tables and are created by the stage that
            # creates the entity (ADR 0008). The роль is left empty: it is not asked for
            # here, and a default one would be a made-up answer (ADR 0009).
            DocumentLink.objects.create(
                document=document,
                entity_type=DocumentLink.EntityType.SPACE,
                entity_id=submission.building.pk,
            )
        return document
