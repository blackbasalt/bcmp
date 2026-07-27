import uuid

from django.contrib.auth.models import User
from django.db import models

from dictionary.models import *
from building_passport.models import *
from parties.models import *



class CommonModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')

    class Meta:
        abstract = True



class Zone(CommonModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, null=True, blank=True, on_delete=models.PROTECT, related_name="zones")
    building = models.ForeignKey(Space, null=True, blank=True, on_delete=models.CASCADE, related_name="zones")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children", help_text="Отсек → секция → подзона")
    kind = models.ForeignKey(DictZoneKind, on_delete=models.PROTECT, related_name="zones")
    code = models.CharField(max_length=64, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(parent_id=F("id")), name="zone_no_self"),
            models.UniqueConstraint(
                F("building_id"),
                F("kind"),
                Lower("code"),
                condition=Q(code__isnull=False, valid_to__isnull=True),
                name="zone_code_uq",
            ),
        ]
        indexes = [models.Index(fields=["building", "kind"], name="zone_kind_idx")]

    def __str__(self):
        return f"{self.kind_id}: {self.code or self.name}"


class ZoneSpace(CommonModel):
    pk = models.CompositePrimaryKey("zone_id", "space_id")
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="spaces")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="zone_links")
    coverage = models.DecimalField(max_digits=5, decimal_places=4, default=1, help_text="Доля вхождения: помещение может лежать на границе двух отсеков")
    note = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(coverage__gt=0, coverage__lte=1), name="zone_space_coverage"
            )
        ]
        indexes = [models.Index(fields=["space"], name="zone_space_rev")]


class AssetServesZone(CommonModel):
    """asset_id — ссылка на реестр оборудования платформы, FK включается в 0004."""

    pk = models.CompositePrimaryKey("asset_id", "zone_id", "role")

    asset_id = models.UUIDField()
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="serving_assets")
    role = models.CharField(max_length=16, choices=DictServiceRole.choices, default=DictServiceRole.PRIMARY)
    coverage = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["primary", "backup", "partial"]), name="asz_role_check"
            )
        ]
        indexes = [models.Index(fields=["zone"], name="asz_zone_idx")]


class AssetServesSpace(CommonModel):
    """Фанкойл обслуживает конкретную комнату, а не зону целиком."""

    pk = models.CompositePrimaryKey("asset_id", "space_id", "role")

    asset_id = models.UUIDField(db_column="asset_id")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="serving_assets")
    role = models.CharField(max_length=16, choices=DictServiceRole.choices, default=DictServiceRole.PRIMARY)
    coverage = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "asset_serves_space"
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["primary", "backup", "partial"]), name="ass_role_check"
            )
        ]
        indexes = [models.Index(fields=["space"], name="ass_space_idx")]


class AssetLink(CommonModel):
    """Топология: без неё агент не ответит, что погаснет при снятии ЩС-3."""

    class Medium(models.TextChoices):
        ELECTRICITY = "electricity", "Электроэнергия"
        WATER = "water", "Вода"
        SEWAGE = "sewage", "Стоки"
        HEAT = "heat", "Тепло"
        COLD = "cold", "Холод"
        AIR = "air", "Воздух"
        GAS = "gas", "Газ"
        SIGNAL = "signal", "Сигнал"
        NETWORK = "network", "Сеть"
        FUEL = "fuel", "Топливо"

    pk = models.CompositePrimaryKey("from_asset_id", "to_asset_id", "relation_id")

    from_asset_id = models.UUIDField()
    to_asset_id = models.UUIDField()
    relation = models.ForeignKey(DictAssetRelationKind, on_delete=models.PROTECT, related_name="+")
    medium = models.CharField(max_length=16, choices=Medium.choices, blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(to_asset_id=F("from_asset_id")), name="asset_link_no_self"
            )
        ]
        indexes = [models.Index(fields=["to_asset_id", "relation"], name="asset_link_rev")]

