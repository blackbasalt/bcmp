import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Now


from dictionary.models import *
from parties.models import *

# Create your models here.
class CommonModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')

    class Meta:
        abstract = True


def discarded_with_its_files(row):
    """Delete a row and then everything it put in the store — the one account of the order.

    The rows first and the files after them, never the other way round: a removal that
    emptied the store and then failed would leave a row pointing at files that are no longer
    there — worse than the orphans this is here to prevent, because it looks complete.

    Two things are discarded this way, a близнец and a документ, and the order is the same
    for both (ADR 0011, ADR 0013). Written twice it would be two accounts of it, and the
    first one to be "tidied up" would be the one nobody was reading.

    Whatever is handed over says what it stored, and says it before the row goes: after the
    cascade there is nothing left to ask, and a file is not deleted by deleting the row that
    names it.
    """
    stored = row.stored_files()
    row.delete()
    for file in stored:
        # A документ entered by hand may have no файл at all, and an empty field names
        # nothing in the store to delete.
        if file:
            file.delete(save=False)


def document_file_path(instance, filename):
    """Files are laid out by organisation: the directory shows whose they are.

    The same device as with the drawings laid out by floor, and for the same reason: the
    directory is the last place where a file can tell you where it came from, once the
    database is out of reach.
    """
    return f"documents/{instance.org_id}/{filename}"


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        """The documents available to a user — the only place of filtering (ADR 0006).

        Its own chokepoint, rather than visibility through the target of a link as with a
        plan: a document may have several links, or none at all, and Parties are set up
        system-wide. Inherited visibility would both leak (a scan of a contract visible to
        everyone who can see the Party) and hide (a document without links visible to no
        one). Bringing documents "into line" with `FloorPlan` means opening that leak.

        The shape is the same as for spaces (ADR 0001): a superuser sees everything, an
        anonymous visitor nothing, everyone else the organisations of their memberships.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(org_id__in=user.memberships.values("org_id"))


class Document(CommonModel):
    """A file attached to a passport entity: an act, a certificate, a protocol, a permit.

    Nothing is computed from a document: whatever has a state of its own is created as an
    entity, and a document is merely attached to it. Hence a lease is an entity with its
    own subject rather than a document of kind `contract`, and a floor plan is not a
    document: a plan shows, a document attests.

    It is visible through its own organisation, not through the entity it is linked to
    (ADR 0006). The file lies in the same protected directory as the drawings, and
    `MEDIA_URL` is unset, so no direct link to it can be assembled: it will be served by a
    view through the same chokepoint the document itself is read by.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Kind(models.TextChoices):
        DESIGN = "design", "Проектная документация"
        AS_BUILT = "as_built", "Исполнительная документация"
        SCHEME = "scheme", "Схема"
        PASSPORT = "passport", "Паспорт изделия"
        MANUAL = "manual", "Руководство по эксплуатации"
        CERTIFICATE = "certificate", "Сертификат"
        ACT = "act", "Акт"
        PROTOCOL = "protocol", "Протокол испытаний / замеров"
        PERMIT = "permit", "Разрешение"
        EXPERTISE = "expertise", "Заключение экспертизы"
        CONTRACT = "contract", "Договор"
        REPORT = "report", "Отчёт"
        PHOTO = "photo", "Фотофиксация"
        OTHER = "other", "Прочее"

    #: Whose document it is. Mandatory: a document without an organisation is filtered by
    #: nothing and shown to everyone — that is not a softening of the visibility rule but
    #: its absence.
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="documents")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=512)
    doc_no = models.CharField(max_length=128, blank=True, null=True)
    #: The file itself, not a path to it: a path as a string would describe a place the
    #: project knows nothing about, whereas the drawings already lie in a protected
    #: directory and are served by a view. There must not be two accounts of where an
    #: upload lives.
    #:
    #: The length matches the title rather than the default 100: the path holds the
    #: organisation's `uuid`, leaving some fifty characters for the file name itself. Names
    #: in the management company's folders are longer, and they would be truncated
    #: silently.
    file_uri = models.FileField(upload_to=document_file_path, max_length=512, blank=True)
    file_hash = models.CharField(max_length=128, blank=True, null=True)
    issued_at = models.DateField(blank=True, null=True)
    #: A field without behaviour: the deadline is stored and shown, but threatens nothing
    #: and counts nothing — no one has ordered a register of deadlines yet.
    valid_until = models.DateField(blank=True, null=True)
    issuer_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="issued_documents")
    #: Also without behaviour: there is no "supersedes such-and-such" relation between
    #: documents, and with zero documents stored any shape for it would be a guess.
    revision = models.CharField(max_length=32, blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True, db_default={})

    objects = DocumentQuerySet.as_manager()

    class Meta:
        # The order is by upload, not by issue date: a batch that has just been
        # transferred is looked for at the top, whereas an act from 2019 uploaded today
        # would slide down to the tail of the list by its issue date.
        #
        # The title as a second key is not decoration: hundreds of files arrive in a
        # batch, and for those landing in the same instant the order would otherwise be
        # undefined altogether, that is, the table would change it from request to
        # request. Within one instant "by upload" means nothing, and the folder reads the
        # way it looked.
        ordering = ["-created_at", "title"]
        indexes = [
            models.Index(fields=["kind", "-issued_at"], name="document_kind_idx"),
            models.Index(
                fields=["valid_until"],
                name="document_expiry",
                condition=Q(valid_until__isnull=False),
            ),
        ]

    def __str__(self):
        return self.title

    def attached_twin(self):
        """The близнец of this документ, or `None` — asked as a question with two answers.

        Having none is the ordinary state (ADR 0007), so it must not be an attribute that
        raises: every place that asks — the page, the download, the replacement — would
        then carry its own account of what "no близнец" looks like, and the four accounts
        would be four chances to disagree.
        """
        return getattr(self, "twin", None)

    def stored_files(self):
        """Everything this документ put in the store — its original, and its близнец's files.

        Asked before the rows go, because after the cascade there is nothing left to ask:
        the близнец and its картинки are children of the документ, and once they are gone
        nothing in the project names the files they wrote.
        """
        twin = self.attached_twin()
        return [self.file_uri] + (twin.stored_files() if twin is not None else [])

    def discard(self):
        """Delete the документ — the whole of it, and for good.

        The близнец, its картинки and the привязки follow the row by cascade, and the files
        are taken out of the store after it, in the order stated once for both kinds of
        discarding.

        There is no soft delete here, as there is nowhere in this project (ADR 0013): a
        hidden документ would be a second lifecycle, and the reader on the shelf would have
        to be told which of the two they are looking at.
        """
        discarded_with_its_files(self)


def twin_file_path(instance, filename):
    """The markdown of a близнец, in a directory of its own.

    Laid out by organisation like the original — the directory is the last place a file can
    say whose it is once the database is out of reach — and then by близнец rather than by
    документ, because a близнец is replaced whole: a new conversion gets an empty directory
    and keeps the names the markdown refers to, instead of squeezing in beside the previous
    one's files and being renamed by the suffix Django adds to avoid a collision.
    """
    return f"documents/{instance.document.org_id}/twins/{instance.pk}/{filename}"


def twin_image_path(instance, filename):
    """A picture of a близнец — beside the markdown that refers to it, in the same directory."""
    return twin_file_path(instance.twin, filename)


class DocumentTwin(CommonModel):
    """The content of a документ in markdown, for the ИИ-управляющий to read.

    BCMP **stores** близнецы and does not produce them: there is no PDF parser, no OCR and
    no markdown library here, and acquiring one is a different stage's problem (ADR 0007).
    Having none is the ordinary state of a документ, not an error — and the документ says
    so, which is what makes a документ the ИИ-управляющий cannot read identifiable.

    A row of its own, one-to-one with the документ, rather than fields on it: a близнец is
    replaced whole together with its pictures while the документ does not change. As a row
    the replacement is a delete and an insert and the pictures follow by cascade; as fields
    they would need clearing by hand, and the first missed clearing would leave the store
    holding pictures from a conversion nobody can reach any more.

    It is not registered in the Django admin, and deliberately: the image references are
    resolved by whoever attaches the markdown and the pictures together, and a близнец
    created in the admin would be one nobody ever asked that question of — recorded as
    complete because the question was never put.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.OneToOneField(
        Document, on_delete=models.CASCADE, related_name="twin", verbose_name="документ"
    )
    #: The markdown itself, in the same protected directory as the original and served by a
    #: view through the same chokepoint (ADR 0006). A file and not a text field: it is
    #: written once, read whole and downloaded as it came.
    markdown = models.FileField(
        upload_to=twin_file_path, max_length=512, verbose_name="маркдаун"
    )
    #: The image references the markdown makes and no attached picture answers, written the
    #: way the markdown wrote them. Kept because they are noticed on attaching and shown on
    #: the документ's page — the same treatment `unmatched_ids` gets on a поэтажный план.
    #: A близнец must be complete: one broken reference means the модель reads the документ
    #: without its схема and never learns that it did.
    unmatched_images = models.JSONField(
        default=list, editable=False, verbose_name="неразрешённые ссылки"
    )

    class Meta:
        verbose_name = "близнец"
        verbose_name_plural = "близнецы"

    def __str__(self):
        return f"Близнец: {self.document.title}"

    def stored_files(self):
        """Everything this близнец put in the store — the markdown and every picture.

        Asked before the rows go, because after the cascade there is nothing left to ask:
        a file is not deleted by deleting the row that names it, and nothing else in the
        project would ever come back for it.
        """
        return [image.file for image in self.images.all()] + [self.markdown]

    def discard(self):
        """Take the близнец off: the rows, and then what they stored.

        The документ itself is not touched — that is the whole reason a близнец is a row of
        its own: a bad conversion is withdrawn and the скан it was made from stays where it
        was.
        """
        discarded_with_its_files(self)


class TwinImage(models.Model):
    """A picture pulled out of the документ, which the близнец's markdown refers to.

    Addressed by name and not by URL: the markdown says `![](p3-img1.png)`, and it is
    against these names that it is resolved. Whoever later shows a близнец to a human is
    responsible for turning a name into an address; the ИИ-управляющий reads text and needs
    nothing here.

    A child row and not a field: it appears and disappears with the близнец, and outlives
    it in no form at all.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    twin = models.ForeignKey(
        DocumentTwin, on_delete=models.CASCADE, related_name="images", verbose_name="близнец"
    )
    #: What the markdown calls the picture. The name is the contract, so two pictures under
    #: one name would make a reference ambiguous — hence the constraint, and the form says
    #: as much in words before the database has to.
    name = models.CharField(max_length=512, verbose_name="имя")
    file = models.FileField(upload_to=twin_image_path, max_length=512, verbose_name="файл")

    class Meta:
        ordering = ["name"]
        verbose_name = "картинка близнеца"
        verbose_name_plural = "картинки близнеца"
        constraints = [
            models.UniqueConstraint(fields=["twin", "name"], name="twin_image_uq"),
        ]

    def __str__(self):
        return self.name


class DocumentLink(models.Model):
    """A polymorphic link from a document to any passport entity."""

    class EntityType(models.TextChoices):
        SPACE = "space", "Пространство"
        ZONE = "zone", "Зона"
        ELEMENT = "building_element", "Конструктив"
        SYSTEM = "building_system", "Система"
        ASSET = "asset", "Оборудование"
        REQUIREMENT = "space_requirement", "Требование"
        SURVEY = "element_survey", "Обследование"
        REPAIR = "element_repair", "Ремонт"
        PARTY = "party", "Контрагент"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="links")
    entity_type = models.CharField(max_length=32, choices=EntityType.choices)
    entity_id = models.UUIDField()
    #: What the document is to the entity: основной, основание, подтверждение, справочно,
    #: устаревший. Optional, because the batch upload does not ask for it and does not
    #: default it either (ADR 0009): empty says "not stated yet", which is the truth about
    #: a folder of scans just carried across.
    role = models.ForeignKey(
        DictDocumentRole, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["entity_type", "entity_id"], name="document_link_entity")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'entity_type', 'entity_id'],
                name='document_link_uq'
            )
        ]

