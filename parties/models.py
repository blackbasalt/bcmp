import uuid

from django.contrib.auth.models import User
from django.db import models

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


class Party(CommonModel):
    """Любая сторона: юрлицо или физлицо. Один раз на всю систему."""
    class Kind(models.TextChoices):
        COMPANY = "company", "Организация"
        PERSON = "person", "Физлицо"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=255)
    bin_iin = models.CharField(unique=True, max_length=32, blank=True, null=True)
    contacts = models.JSONField(default=dict, blank=True, db_default={})
    external_id = models.CharField(max_length=1024, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class OrgQuerySet(models.QuerySet):
    def administered_by(self, user):
        """Организации, данные которых пользователь вправе вести (ADR 0005).

        Отвечает на вопрос «чьи данные», тогда как `Space.objects.administered_by` и
        `Lease.objects.administered_by` — на вопрос «какие строки»: последний
        спрашивает этот, а не собирает членства во второй раз. Спрашивают его же и
        форма договора, предлагающая выбор организации, и экран, решающий, показать
        ли её вообще: показанная кнопка и принятый запрос должны отвечать одинаково.

        Суперпользователь администрирует всё по той же причине, по которой всё
        видит: он и так пишет через админку Django.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(memberships__user=user, memberships__is_admin=True)


class Org(CommonModel):
    """Арендатор платформы. Тонкий слой над Party, не дубль."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.OneToOneField(Party, on_delete=models.PROTECT, related_name="tenancy")
    plan = models.CharField(max_length=32, blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True, db_default={})
    is_active = models.BooleanField(default=True, db_default=True)

    objects = OrgQuerySet.as_manager()

    @property
    def name(self):
        return self.party.name

    def __str__(self):
        return self.name


class OrgMembership(CommonModel):
    """Доступ пользователя к организации. Один сотрудник может состоять в нескольких."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    #: Право вести данные этой организации из приложения, а не только читать их.
    #: Стоит на членстве, а не на пользователе: администраторство принадлежит паре
    #: «сотрудник + организация», и сотрудник, ведущий одного клиента, остаётся
    #: обычным читателем у другого. Глобальный `is_staff` этого не выражает — тот же
    #: довод, что и у самой изоляции по организациям (ADR 0001, ADR 0005).
    is_admin = models.BooleanField(
        default=False, db_default=False, verbose_name="администратор организации"
    )

    class Meta:
        db_table = "org_membership"
        verbose_name = "членство в организации"
        verbose_name_plural = "членства в организациях"
        constraints = [
            models.UniqueConstraint(fields=["user", "org"], name="org_membership_uq"),
        ]

    def __str__(self):
        return f"{self.user} → {self.org}"


class PartyRole(CommonModel):
    """Роль стороны в конкретном контексте и в конкретный период.

    Арендатора среди ролей нет намеренно: им Сторону делает договор аренды и
    только он (ADR 0008). Роль `tenant` знала одно помещение на строку, не знала
    ставки и не проверяла пересечений, поэтому оставленная рядом с договором она
    была бы вторым ответом на вопрос «кто здесь арендатор».
    """
    class Role(models.TextChoices):
        OWNER = "owner", "Собственник"
        OPERATOR = "operator", "Управляющая компания"
        CONTRACTOR = "contractor", "Подрядчик"
        SUPPLIER = "supplier", "Поставщик"
        EXPERT = "expert", "Эксперт"
        DESIGNER = "designer", "Проектировщик"
        BUILDER = "builder", "Подрядчик СМР"

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=32, choices=Role.choices)
    scope_type = models.CharField(max_length=32, blank=True, null=True)  # space|zone|building_system|org
    scope_id = models.UUIDField(blank=True, null=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)

    class Meta:
        db_table = "party_role"
