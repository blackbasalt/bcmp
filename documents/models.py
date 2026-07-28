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


class Document(CommonModel):
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

    org = models.ForeignKey(Org, null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=512)
    doc_no = models.CharField(max_length=128, blank=True, null=True)
    file_uri = models.TextField(blank=True, null=True)
    file_hash = models.CharField(max_length=128, blank=True, null=True)
    page_count = models.IntegerField(blank=True, null=True)
    issued_at = models.DateField(blank=True, null=True)
    valid_until = models.DateField(blank=True, null=True)
    issuer_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="issued_documents")
    revision = models.CharField(max_length=32, blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True, db_default={})

    class Meta:
        ordering = ["-issued_at"]
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
    """Полиморфная привязка документа к любой сущности паспорта."""

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
    role = models.ForeignKey(DictDocumentRole, on_delete=models.PROTECT, related_name="+")

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

