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

