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
    """Файлы лежат по организациям: в каталоге видно, чьи они.

    Тот же приём, что и у чертежей, разложенных по этажам, и по той же причине:
    каталог — последнее место, где по файлу можно понять, откуда он взялся, если
    до базы дела уже нет.
    """
    return f"documents/{instance.org_id}/{filename}"


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Документы, доступные пользователю, — единственное место фильтрации (ADR 0006).

        Свой чокпоинт, а не видимость по цели привязки, как у плана: у документа
        привязок может быть несколько, а может не быть ни одной, и Стороны заведены
        на всю систему. Унаследованная видимость и утекала бы (скан договора виден
        всем, кому видна Сторона), и прятала бы (документ без привязки не виден
        никому). Приводить документы «к единообразию» с `FloorPlan` — значит открыть
        эту утечку.

        Форма та же, что и у пространств (ADR 0001): суперпользователь видит всё,
        аноним — ничего, остальные — организации своих членств.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(org_id__in=user.memberships.values("org_id"))


class Document(CommonModel):
    """Файл, приложенный к сущности паспорта: акт, сертификат, протокол, разрешение.

    Из документа ничего не считают: то, у чего есть собственное состояние, заводится
    сущностью, а документ лишь прикладывается к ней. Поэтому договор аренды — сущность
    со своим предметом, а не документ вида `contract`, и поэтажный план — не документ:
    план показывает, документ удостоверяет.

    Виден по своей организации, а не по той сущности, к которой привязан (ADR 0006).
    Файл лежит в том же защищённом каталоге, что и чертежи, и `MEDIA_URL` не задан,
    так что прямую ссылку на него не собрать: раздавать его будет представление через
    тот же чокпоинт, каким документ и читается.
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

    #: Чей документ. Обязателен: документ без организации не отфильтруется ничем и
    #: покажется всем — это не смягчение правила видимости, а его отсутствие.
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="documents")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=512)
    doc_no = models.CharField(max_length=128, blank=True, null=True)
    #: Сам файл, а не путь к нему: путь строкой описывал бы место, о котором проект
    #: ничего не знает, тогда как чертежи уже лежат в защищённом каталоге и
    #: раздаются представлением. Двух рассказов о том, где лежит загруженное, быть
    #: не должно.
    #:
    #: Длина — как у названия, а не стандартные 100: в пути лежит `uuid` организации,
    #: и на само имя файла от него остаётся полсотни символов. Имена в папках УК
    #: длиннее, и обрезаны они были бы молча.
    file_uri = models.FileField(upload_to=document_file_path, max_length=512, blank=True)
    file_hash = models.CharField(max_length=128, blank=True, null=True)
    issued_at = models.DateField(blank=True, null=True)
    #: Поле без поведения: срок хранится и показывается, но ничем не грозит и ничего
    #: не считает — реестра сроков никто пока не заказывал.
    valid_until = models.DateField(blank=True, null=True)
    issuer_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="issued_documents")
    #: Тоже без поведения: связи «взамен такого-то» между документами нет, и с нулём
    #: хранимых документов любая её форма была бы догадкой.
    revision = models.CharField(max_length=32, blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True, db_default={})

    objects = DocumentQuerySet.as_manager()

    class Meta:
        # Порядок — по загрузке, а не по дате выдачи: пакет, который только что
        # перенесли, читатель ищет сверху, а акт 2019 года, загруженный сегодня,
        # уехал бы по дате выдачи в хвост списка.
        #
        # Название вторым ключом — не украшение: пакетом приезжают сотни файлов, и
        # у попавших в одно мгновение порядок иначе не определён вовсе, то есть
        # таблица меняла бы его от запроса к запросу. Внутри одного мгновения
        # «по загрузке» не значит ничего, и папка читается так же, как выглядела.
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

