from django.contrib.auth.models import User
from django.db import models

from dictionary.models import *
from zones.models import *
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


class BuildingSystem(CommonModel):
    class Status(models.TextChoices):
        DESIGN = "design", "Проект"
        INSTALLED = "installed", "Смонтирована"
        COMMISSIONING = "commissioning", "Пусконаладка"
        OPERATING = "operating", "В работе"
        STANDBY = "standby", "Резерв"
        DECOMMISSIONED = "decommissioned", "Выведена"

    building = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="systems")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children", help_text="П-1 ⊂ приточная вентиляция ⊂ ОВиК")
    catalog = models.ForeignKey(DictSystem, null=True, blank=True, on_delete=models.PROTECT, related_name="instances")
    code = models.CharField(max_length=64, blank=True, null=True, help_text="П-1, ЩС-3, ИТП-1")
    name = models.CharField(max_length=255, blank=True, null=True)
    criticality = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, blank=True, null=True)
    responsible_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="responsible_systems")
    attrs = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(criticality__gte=1, criticality__lte=5), name="bs_criticality_range"
            ),
            models.UniqueConstraint(
                F("building_id"), Lower("code"),
                condition=Q(code__isnull=False), name="bs_code_uq",
            ),
        ]
        indexes = [models.Index(fields=["catalog"], name="bs_catalog_idx")]

    def __str__(self):
        return f"{self.code or ''} {self.name or ''}".strip()


class SystemServesZone(models.Model):
    #pk = models.CompositePrimaryKey("system_id", "zone_id", "role")

    system = models.ForeignKey(BuildingSystem, on_delete=models.CASCADE, related_name="served_zones")
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, db_column="zone_id", related_name="serving_systems")
    role = models.CharField(max_length=16, choices=DictServiceRole.choices, default=DictServiceRole.PRIMARY)


class SystemServesSpace(models.Model):
    #pk = models.CompositePrimaryKey("system_id", "space_id", "role")

    system = models.ForeignKey(BuildingSystem, on_delete=models.CASCADE, related_name="served_spaces")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="serving_systems")
    role = models.CharField(max_length=16, choices=DictServiceRole.choices, default=DictServiceRole.PRIMARY)

