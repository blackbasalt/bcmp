import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower, Now
from django.utils import timezone


from dictionary.models import *
from parties.models import *

from .floor_plan_svg import PlanUnreadable, read_plan
from .space_tree import spaces_under

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

class SpaceQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Пространства, доступные пользователю, — единственное место фильтрации."""
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(org_id__in=user.memberships.values("org_id"))

    def buildings_visible_to(self, user):
        """Доступные пользователю бизнес-центры: БЦ — это пространство типа building."""
        return self.visible_to(user).filter(type=DictSpaceType.BUILDING)

    def floors_of(self, building):
        """Этажи здания снизу вверх — и раздел «Этажи» карточки, и переключатель.

        Фильтрацию по организации не делает: её делает `visible_to`, через который
        этот метод и вызывается, — иначе появилось бы второе место, где решается,
        чьи данные показывать.
        """
        return self.filter(type=DictSpaceType.FLOOR, building=building).order_by(
            "floor_number", "code"
        )


class Space(CommonModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Org, null=True, blank=True, on_delete=models.PROTECT, related_name="spaces")
    type = models.TextField(choices=DictSpaceType.choices)
    subtype = models.ForeignKey(DictSpaceSubtype, on_delete=models.CASCADE, null=True, blank=True, related_name="spaces")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name="subspace")
    building = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name="buildings_spaces")
    code = models.CharField(max_length=255, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    floor_number = models.IntegerField(null=True, blank=True)
    level_elevation_m = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    status = models.ForeignKey(DictSpaceStatus, on_delete=models.PROTECT, blank=True, null=True, related_name="spaces")

    area_m2 = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    is_common = models.BooleanField(default=False,blank=True, null=True)
    is_leasable = models.BooleanField(default=False,blank=True, null=True)
    attrs = models.JSONField(default=dict, blank=True)

    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)

    objects = SpaceQuerySet.as_manager()

    def __str__(self):
        return f"{self.code} ({self.type})"

    @property
    def project(self):
        """Проект над пространством — он показывается подписью, а не уровнем навигации.

        Выше БЦ ровно два уровня, площадка и проект, поэтому цепочка родителей
        разматывается на два шага: заодно зациклённый `parent` не подвесит запрос.
        """
        ancestor = self.parent
        for _ in range(2):
            if ancestor is None:
                return None
            if ancestor.type == DictSpaceType.PROJECT:
                return ancestor
            ancestor = ancestor.parent
        return None


def plan_file_path(instance, filename):
    """Чертежи лежат по этажам: в каталоге видно, к чему относится файл."""
    return f"floor_plans/{instance.floor_id}/{filename}"


class FloorPlanQuerySet(models.QuerySet):
    def visible_to(self, user):
        """План виден там же, где виден его этаж, — чокпоинт остаётся один (ADR 0001).

        Своей фильтрации по организации здесь нет намеренно: у плана нет `org`, и
        второе место, решающее чьи данные показывать, — это способ их однажды разойтись.
        """
        return self.filter(floor__in=Space.objects.visible_to(user))

    def overlapping(self, begin, end):
        """Планы, чьи периоды задевают отрезок от `begin` до `end` включительно.

        Оба конца входят в период, поэтому план, начинающийся в день закрытия
        отрезка, с ним пересекается. Открытый конец — что у плана, что у отрезка —
        означает «по сей день» и не кончается никогда, так что любое начало после
        такого плана в него попадает.

        Одна форма запроса на два вопроса: какой план действует в этот день — это
        пересечение с отрезком из одного дня, а непересечение периодов — то же
        самое на отрезке нового плана.
        """
        began_by_the_end = Q() if end is None else Q(valid_from__lte=end)
        not_ended_before_the_begin = Q(valid_to__isnull=True) | Q(valid_to__gte=begin)
        return self.filter(began_by_the_end).filter(not_ended_before_the_begin)

    def in_force_on(self, day):
        """Планы, действующие в этот день: период начался и ещё не закончился.

        Периоды планов одного этажа не пересекаются, поэтому у этажа таких планов
        не больше одного.

        Не «самый поздний по дате начала»: план будущей перепланировки уже заведён,
        а этаж сегодня выглядит ещё не так, и работы планируют по сегодняшнему.
        """
        return self.overlapping(day, day)


class FloorPlan(CommonModel):
    """Поэтажный план: чертёж этажа и система координат, в которой лежат контуры.

    Не документ: документ удостоверяет и несёт номер, дату и выдавшую сторону, а план
    показывает — и является системой координат для помещений. И не поле помещения:
    план принадлежит этажу и относится к периоду, после перепланировки прежний
    сохраняется (ADR 0003).

    Файл лежит в защищённом каталоге и раздаётся представлением через тот же чокпоинт,
    что и всё остальное: `MEDIA_URL` не задан, так что прямую ссылку на него не собрать.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    floor = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="floor_plans", verbose_name="этаж"
    )
    file = models.FileField(upload_to=plan_file_path, verbose_name="файл SVG")
    #: `viewBox` чертежа: с ним же рисуются контуры поверх, иначе они с ним разъедутся.
    view_box = models.CharField(max_length=128, editable=False, verbose_name="viewBox")
    valid_from = models.DateField(verbose_name="действует с")
    valid_to = models.DateField(blank=True, null=True, verbose_name="действует по")

    objects = FloorPlanQuerySet.as_manager()

    class Meta:
        ordering = ("-valid_from",)
        verbose_name = "поэтажный план"
        verbose_name_plural = "поэтажные планы"

    def __str__(self):
        return f"План {self.floor} от {self.valid_from}"

    @property
    def aspect_ratio(self):
        """Соотношение сторон `viewBox` для CSS: чертёж и контуры держат одну рамку."""
        _, _, width, height = self.view_box.split()
        return f"{width} / {height}"

    def clean(self):
        """Причина отказа называется на форме, а не падает пятисоткой при сохранении."""
        super().clean()
        if self.floor_id is not None and self.floor.type != DictSpaceType.FLOOR:
            raise ValidationError({"floor": "План принадлежит этажу, а не помещению в нём."})
        self._validate_period()
        if self.floor_id is None or not self.file:
            return
        try:
            self._read_contours()
        except PlanUnreadable as error:
            raise ValidationError({"file": str(error)}) from error

    def save(self, *args, **kwargs):
        """План и его контуры появляются одной операцией: порознь они не появляются.

        Разбор идёт до записи: непрочитанный файл не оставляет за собой ни строки в
        базе, ни файла в хранилище. Повторное сохранение контуры не пересобирает —
        чертёж разобран один раз и остаётся с теми помещениями, с которыми был
        нарисован (ADR 0003), поэтому правка периода не переносит план на сегодняшнее
        дерево помещений. Новая планировка — это новый план, а не новый файл у старого.
        """
        self._validate_period()
        if not self._state.adding:
            super().save(*args, **kwargs)
            return
        self.view_box, contours = self._read_contours()
        with transaction.atomic():
            super().save(*args, **kwargs)
            Contour.objects.bulk_create(contours)

    def _validate_period(self):
        """Период должен быть периодом и не должен задевать соседний период этажа.

        Правило стоит на самом плане, а не на форме: админка, будущая форма загрузки
        и код пишут одним и тем же путём и получают один и тот же отказ. Иначе
        «действующий план» перестал бы быть определённым — сегодняшних планов
        оказалось бы два, и какой из них показывать, решал бы порядок сортировки.

        Прежний план при этом не закрывается сам: назначить перепланировку днём
        загрузки — выдумать факт, тот же по природе, что и `year_built = 1900`,
        от которого этап 1 уходил. Дату называет загружающий, а система отказывает.
        """
        if self.valid_from is None or self.floor_id is None:
            return
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "Период заканчивается раньше, чем начинается."})
        conflicting = self._conflicting_plans().first()
        if conflicting is not None:
            closes = f"{conflicting.valid_to:%d.%m.%Y}" if conflicting.valid_to else "по сей день"
            raise ValidationError(
                f"Период пересекается с планом этажа за {conflicting.valid_from:%d.%m.%Y} — "
                f"{closes}. У этажа не бывает двух действующих планов: закройте прежний "
                f"период датой перепланировки."
            )

    def _conflicting_plans(self):
        """Планы того же этажа, чьи периоды задевают этот, — их не должно быть ни одного.

        Смежный план конфликтом не считается: пересекается тот, что начинается в день
        закрытия предыдущего, а не на следующий день после него.
        """
        return (
            FloorPlan.objects.filter(floor_id=self.floor_id)
            .exclude(pk=self.pk)
            .overlapping(self.valid_from, self.valid_to)
        )

    def _read_contours(self):
        """Разобранный чертёж: его `viewBox` и контуры, уже сведённые с помещениями."""
        spaces = self._spaces_by_code()
        reading = read_plan(b"".join(self.file.chunks()), spaces.keys())
        return reading.view_box, [
            Contour(plan=self, space=spaces[contour.code], path_d=contour.path_d)
            for contour in reading.contours
        ]

    def _spaces_by_code(self):
        """Помещения этажа по кодам — то, с чем сводятся пути чертежа.

        Нутро здания приезжает одним запросом и разбирается тем же спуском, что и
        дерево на экране: план и дерево должны считать помещениями этажа одно и то же.
        """
        inside = Space.objects.filter(building_id=self.floor.building_id)
        return {space.code: space for space in spaces_under(self.floor, inside) if space.code}


class Contour(CommonModel):
    """Граница помещения на конкретном плане — пара «план + помещение» (ADR 0003).

    Путь лежит текстом, а не отдельным файлом: контур — это несколько сотен байт, и
    файлами они стоили бы этажу 82 запроса, а совпадение их `viewBox` с планом ничем
    бы не проверялось.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        FloorPlan, on_delete=models.CASCADE, related_name="contours", verbose_name="план"
    )
    space = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="contours", verbose_name="помещение"
    )
    path_d = models.TextField(verbose_name="данные пути")

    class Meta:
        verbose_name = "контур"
        verbose_name_plural = "контуры"
        constraints = [
            models.UniqueConstraint(fields=["plan", "space"], name="contour_uq"),
        ]

    def __str__(self):
        return f"Контур {self.space}"


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


    building_passport_naming = models.CharField(max_length=512, blank=True, null=True) #
    region = models.CharField(max_length=512, blank=True, null=True) #1
    region_district = models.CharField(max_length=512, blank=True, null=True) #2
    settlement = models.CharField(max_length=512, blank=True, null=True) #3
    settlement_district = models.CharField(max_length=512, blank=True, null=True) #4
    address = models.CharField(max_length=512, blank=True, null=True) #5
    cadastral_no = models.CharField("Кадастровый номер", max_length=64, blank=True, null=True) #6
    inventory_number = models.CharField(max_length=512, blank=True, null=True) #7
    intended_purpose = models.CharField(max_length=512, blank=True, null=True) #8
    property_category = models.CharField(max_length=512, blank=True, null=True) #9

    series_project_type = models.CharField(max_length=512, blank=True, null=True) #1
    number_of_floors = models.CharField(max_length=512, blank=True, null=True) #2
    building_footprint = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True) #3
    building_volume = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True) #4
    total_area = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True) #5
    balcony_loggia_area = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True) #6
    living_area = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True) #7
    non_residential_area = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True) #8
    apartments_number = models.IntegerField(blank=True, null=True) #9
    total_rooms = models.IntegerField(blank=True, null=True) #10
    wall_material = models.CharField(max_length=512, blank=True, null=True) #11
    year_built = models.IntegerField(blank=True, null=True) #12
    physical_wear_tear = models.CharField(max_length=512, blank=True, null=True) #13
    registry_number = models.CharField(max_length=512, blank=True, null=True) #
    passport_prepared = models.DateField(blank=True, null=True) #
    signer_name = models.CharField(max_length=512, blank=True, null=True) #

    lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
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

