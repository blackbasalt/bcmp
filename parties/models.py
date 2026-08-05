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


class Org(CommonModel):
    """Арендатор платформы. Тонкий слой над Party, не дубль."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.OneToOneField(Party, on_delete=models.PROTECT, related_name="tenancy")
    plan = models.CharField(max_length=32, blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True, db_default={})
    is_active = models.BooleanField(default=True, db_default=True)

    @property
    def name(self):
        return self.party.name

    def __str__(self):
        return self.name


class PartyRole(CommonModel):
    """Роль стороны в конкретном контексте и в конкретный период."""
    class Role(models.TextChoices):
        OWNER = "owner", "Собственник"
        OPERATOR = "operator", "Управляющая компания"
        CONTRACTOR = "contractor", "Подрядчик"
        TENANT = "tenant", "Арендатор"
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
