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

"""
site      → building, territory
building  → wing, floor, roof, facade, shaft, stairwell
wing      → floor, shaft, stairwell
floor     → room, mezzanine, void, parking_spot
room      → room            (санузел или серверная внутри офиса арендатора)
roof      → room            (надстройки: венткамеры, машинные отделения)
territory → room, parking_spot

Для floor: типовой, технический, подземный, чердак, паркинг-уровень.

Для shaft: лифтовая, вентиляционная, дымоудаления, кабельная, сантехническая (стояки), мусоропровод.

Для room — арендопригодные: офис, стрит-ритейл, общепит (кафе/фудкорт), банк, медицина, фитнес, шоурум, склад арендатора, коворкинг.

Для room — МОП: лобби/вестибюль, ресепшн, коридор, лифтовой холл, санузел, терраса/балкон, курительная, входная группа/тамбур.

Для room — технические (самая длинная группа, и именно она кормит твой MEP-классификатор): ИТП, котельная, насосная, пожарная насосная, венткамера, электрощитовая/ГРЩ, трансформаторная (ТП/КТП), ДГУ, серверная, кроссовая/узел связи, водомерный узел, узел управления спринклерами, диспетчерская/пост охраны, мастерская, склад ЗИП (пригодится как локация остатков на этапе 2), КУИ (уборочный инвентарь), мусорокамера, бытовка персонала, архив, дебаркадер/зона разгрузки.

Для territory: открытая парковка, КПП, площадка ТБО, благоустройство/газоны.
"""

class Space(CommonModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, null=True, blank=True, on_delete=models.PROTECT, related_name="spaces")
    type = models.TextField(choices=DictSpaceType.choices)
    subtype = models.ForeignKey(DictSpaceSubtype, on_delete=models.CASCADE, null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name="subspace")
    building = models.ForeignKey(DictBuilding, on_delete=models.CASCADE, null=True, blank=True, related_name="subspace")
    code = models.CharField(max_length=255, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    floor_number = models.IntegerField(null=True, blank=True)
    level_elevation_m = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)

    area_m2 = models.DecimalField(max_digits=12, decimal_places=2)
    is_common = models.BooleanField(default=False)
    is_leasable = models.BooleanField(default=False)
    attrs = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Пространство {self.type} от {self.id}"


class BuildingPassport(CommonModel):
    class BuildingClass(models.TextChoices):
        A_PLUS = "A+", "A+"
        A = "A", "A"
        B_PLUS = "B+", "B+"
        B = "B", "B"
        C = "C", "C"
        INDUSTRIAL = "industrial", "Производственное"
        OTHER = "other", "Прочее"
 
    space = models.OneToOneField(Space, primary_key=True, on_delete=models.CASCADE, db_column="space_id", related_name="passport")
    cadastral_no = models.CharField("Кадастровый номер", max_length=64, blank=True, null=True)
    address = models.CharField(max_length=512, blank=True, null=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    year_built = models.IntegerField(blank=True, null=True)
    year_commissioned = models.IntegerField(blank=True, null=True)
    year_last_major_repair = models.IntegerField(blank=True, null=True)
    building_class = models.CharField(max_length=16, choices=BuildingClass.choices, blank=True, null=True)
    floors_above = models.IntegerField(blank=True, null=True)
    floors_below = models.IntegerField(blank=True, null=True)
    structural_scheme = models.CharField(max_length=64, blank=True, null=True, help_text="монолит | сборный каркас | панель | кирпич | металлокаркас")
    fire_resistance_degree = models.CharField("Степень огнестойкости", max_length=16, blank=True, null=True)
    functional_fire_class = models.CharField("Класс функциональной пожарной опасности", max_length=16, blank=True, null=True)
    structural_fire_class = models.CharField("Класс конструктивной пожарной опасности", max_length=16, blank=True, null=True)
    seismic_points = models.IntegerField("Расчётная сейсмичность, баллы", blank=True, null=True)
    energy_class = models.CharField(max_length=8, blank=True, null=True)
    design_occupancy = models.IntegerField(blank=True, null=True)
    owner_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name="owned_buildings")
    operator_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name="operated_buildings")
    designer_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name="designed_buildings")
    builder_party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name="built_buildings")
    commissioning_act_no = models.CharField(max_length=64, blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True, db_default={})
 
    class Meta:
        verbose_name = "паспорт здания"
        verbose_name_plural = "паспорта зданий"
 
    def __str__(self):
        return f"Паспорт: {self.space}"


class SpaceRequirement(CommonModel):
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="requirements")
    code = models.ForeignKey(DictRequirementCode, on_delete=models.PROTECT, related_name="+")
    value_num = models.DecimalField(max_digits=16, decimal_places=4, blank=True, null=True)
    value_text = models.TextField(blank=True, null=True)
    value_bool = models.BooleanField(blank=True, null=True)
    unit = models.CharField(max_length=32, blank=True, null=True)
    norm_ref = models.CharField(max_length=255, blank=True, null=True, help_text="Пункт норматива или ТЗ")
    actual_num = models.DecimalField(max_digits=16, decimal_places=4, blank=True, null=True)
    actual_text = models.TextField(blank=True, null=True)
    measured_at = models.DateField(blank=True, null=True)
    is_compliant = models.BooleanField(blank=True, null=True)
    #document = models.ForeignKey("Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(value_num__isnull=False)
                    | Q(value_text__isnull=False)
                    | Q(value_bool__isnull=False)
                ),
                name="sr_has_value",
            ),
            models.UniqueConstraint(fields=["space", "code"], name="space_requirement_uq"),
        ]
        indexes = [
            models.Index(
                fields=["space"], name="sr_noncompliant", condition=Q(is_compliant=False)
            )
        ]


class SpaceArea(CommonModel):
    class Source(models.TextChoices):
        BTI = "bti", "Обмер БТИ"
        AS_BUILT = "as_built", "Исполнительная"
        DESIGN = "design", "Проект"
        SURVEY = "survey", "Обмер на месте"
        BIM = "bim", "Модель BIM"
        LEASE = "lease_contract", "Договор аренды"
        ESTIMATE = "estimate", "Оценка"

    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="areas")
    kind = models.ForeignKey(DictAreaKind, on_delete=models.PROTECT, related_name="+")
    value_m2 = models.DecimalField(max_digits=12, decimal_places=2)
    measured_at = models.DateField(blank=True, null=True)
    source = models.CharField(max_length=32, choices=Source.choices, blank=True, null=True)
    #document = models.ForeignKey("Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(value_m2__gte=0), name="space_area_positive"
            ),
            models.UniqueConstraint(fields=["space", "kind"], name="space_area_uq"),
        ]


class SpaceCodeHistory(CommonModel):
    """Старые акты и планы должны продолжать находиться по прежнему коду."""

    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="code_history")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255, blank=True, null=True)
    valid_from = models.DateField()
    valid_to = models.DateField(blank=True, null=True)
    reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [models.Index(Lower("code"), name="space_code_hist_idx")]


class SpaceLink(CommonModel):
    """Шахта проходит через этаж, лестница соединяет уровни и т.п."""

    pk = models.CompositePrimaryKey("space_id", "related_id", "relation_id")
    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="links")
    related = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="links_in")
    relation = models.ForeignKey(DictSpaceRelationKind, on_delete=models.PROTECT, related_name="+")
    attrs = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(related_id=F("space_id")), name="space_link_no_self"
            )
        ]
        indexes = [models.Index(fields=["related", "relation"], name="space_link_rev")]

