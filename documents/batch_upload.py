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

A converted folder arrives whole: the близнецы come in the same submission as the документы
they were made from and are matched to them by file name (ADR 0012). The alternative is a
second pass over the same pile of hundreds of files, which is why the slot exists now
rather than later.
"""

from dataclasses import dataclass, field
from typing import NamedTuple

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from building_passport.models import Space
from parties.models import Org

from .batch_twins import sort_out
from .building_choice import BuildingChoice
from .models import Document, DocumentLink
from .twin_attach import attach_twin
from .uploaded_files import (
    ACCEPTED_NAMES,
    BATCH_IN_A_DIALOG,
    BATCH_LIMIT,
    FILE_LIMIT,
    MEGABYTE,
    MultipleFileInput,
    digest_of,
    head_of,
    refusal_for,
    stem_of,
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
    #: The близнецы attached by this batch. Counted apart from the files, because they are
    #: not on the shelf: they are what makes the документы already on it readable, and «12
    #: файлов» would say nothing about whether the близнецы landed with them.
    twins: list = field(default_factory=list)
    #: The files whose content is already on the shelf, each with the document it is stored
    #: as. Not a refusal — a message: overlapping folders are the norm in an archive
    #: transfer, and the sender's next action is to look at that document, not to resend.
    already_stored: list = field(default_factory=list)
    #: The files that were not taken, each with the reason. Близнецы among them: one that
    #: found no документ of its own is reported by name and stored nowhere.
    refused: list = field(default_factory=list)


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
            f"файлов за раз. Название документа берётся из имени файла. Маркдаун-близнецы "
            f"кладутся в ту же пачку: «akt-2024-03.md» приложится к «akt-2024-03.pdf», а "
            f"картинки — к тому близнецу, который на них ссылается."
        ),
        widget=MultipleFileInput(attrs={"accept": BATCH_IN_A_DIALOG}),
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
        self.fields["building"].offer(Space.objects.buildings_administered_by(user))

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


class Landed(NamedTuple):
    """What became of the документ a близнец of the same name is looking for.

    Either the документ this batch stored, or the reason there is none to attach to — and
    the reason is kept rather than the mere absence, because «его документ не сохранён» and
    «такого документа в пачке нет» send the sender to two different places.
    """

    document: Document | None
    refusal: str | None


def store_batch(files, submission):
    """Store the files of one submission, one at a time, and report on each of them.

    One at a time and not in one transaction: the point of the batch is that a bad file
    among a hundred good ones costs the sender that one file and not the afternoon.

    The документы go first and the близнецы after them, because a близнец is attached to a
    документ: until the folder has been stored there is nothing to attach it to, and which
    of the файлы actually landed is not known in advance.
    """
    report = BatchReport()
    documents, batched = sort_out(files)
    landed = {}
    for uploaded in documents:
        stem = stem_of(uploaded.name)
        refusal = refusal_for(uploaded.name, uploaded.size, head_of(uploaded))
        if refusal is not None:
            report.refused.append((uploaded.name, refusal))
            _note_landing(landed, stem, Landed(None, f"документ «{stem}» в пачке не сохранён"))
            continue
        digest = digest_of(uploaded)
        # The shelf a duplicate is looked for on is the one the file would land on: the
        # same content in another client's organisation is another client's document, and
        # naming it would tell one what the other has stored (ADR 0006).
        already = Document.objects.filter(org=submission.org, file_hash=digest).first()
        if already is not None:
            report.already_stored.append((uploaded.name, already))
            _note_landing(
                landed,
                stem,
                # A duplicate stores nothing, so this batch has no документ to attach to.
                # The one already on the shelf may well have a близнец of its own, and
                # replacing it silently in the middle of a batch of two hundred is a
                # replacement nobody asked for: it is done on that документ's own page,
                # where the screen says which близнец is being superseded.
                Landed(
                    None,
                    f"документ «{already.title}» уже был загружен раньше — близнеца "
                    f"прикладывают на его странице",
                ),
            )
            continue
        document = _store(uploaded, submission, digest)
        report.stored.append(document)
        _note_landing(landed, stem, Landed(document, None))
    for twin in batched:
        refusal = _cannot_attach(twin, landed)
        if refusal is not None:
            # A близнец that found no документ of its own is reported in the same list as a
            # refused file and for the same reason: the person who uploaded two hundred
            # files needs to know exactly what did not land.
            report.refused.append((twin.name, refusal))
            continue
        report.twins.append(
            attach_twin(landed[twin.stem].document, twin.uploaded, twin.text, twin.pictures)
        )
    return report


def _note_landing(landed, stem, entry):
    """Remember what became of a file under its name — the name a близнец will look for.

    One name in a batch names one документ. Where it names two, it names neither: a близнец
    would otherwise land on whichever of them happened to be stored second. The same rule
    as for the картинки of a близнец, which is why it is stated in words there too.
    """
    landed[stem] = (
        entry
        if stem not in landed
        else Landed(None, f"в пачке несколько документов с именем «{stem}»")
    )


def _cannot_attach(twin, landed):
    """Why this близнец is not attached to anything — or `None` if it is.

    Its own reasons come first: a близнец that cannot be attached at all is not attached to
    a документ that happens to be missing either, and the sender is told the thing they can
    act on.

    Whatever the reason, the картинки that came with it are named in it: a картинка no
    близнец refers to is stored as a документ in its own right, so a sender told only about
    the markdown would look for the схемы on the shelf. They are not there — they are
    halves of a близнец, and the близнец did not land (ADR 0012).
    """
    absent = Landed(None, f"в пачке нет документа с именем «{twin.stem}»")
    refusal = twin.refusal or landed.get(twin.stem, absent).refusal
    if refusal is None or not twin.pictures:
        return refusal
    names = ", ".join(name for name, _ in twin.pictures)
    return f"{refusal}. Вместе с ним не сохранены картинки: {names}"


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
