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
from .period import refuse_a_period_that_ends_before_it_begins
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
room      → room            (a toilet or a server room inside a tenant's office)
roof      → room            (rooftop structures: air handling rooms, lift machine rooms)
territory → room, parking_spot

For floor: typical, technical, underground, attic, parking level.

For shaft: lift, ventilation, smoke extraction, cable, plumbing (risers), refuse chute.

For room — leasable: office, street retail, food service (café/food court), bank, medical, fitness, showroom, tenant storage, co-working.

For room — common areas: lobby/entrance hall, reception, corridor, lift hall, toilet, terrace/balcony, smoking room, entrance group/vestibule.

For room — technical (the longest group, and the one that feeds the MEP classifier): individual heating substation (ИТП), boiler room, pump room, fire pump room, air handling room, switchboard room (ГРЩ), transformer substation (ТП/КТП), diesel generator (ДГУ), server room, telecom cross-connect room, water metering unit, sprinkler control unit, control room/security post, workshop, spare parts store (ЗИП — useful as a stock location in stage 2), cleaning equipment room (КУИ), refuse chamber, staff room, archive, loading dock.

For territory: open parking, checkpoint, waste collection area, landscaping/lawns.
"""

class SpaceQuerySet(models.QuerySet):
    def visible_to(self, user):
        """The spaces available to the user — the single place where filtering happens."""
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(org_id__in=user.memberships.values("org_id"))

    def administered_by(self, user):
        """The spaces the user may maintain — the write checkpoint (ADR 0005).

        A separate question from `visible_to`: reading an organisation's data and
        creating it are different rights, and the second is granted by a flag on the
        membership rather than by a global `is_staff`. There is still only one place,
        as with reading: the write path asks it instead of assembling a filter itself.

        Which organisations those are is not worked out here but asked of the
        organisations themselves: documents are written into the same organisations as
        spaces, and the right belongs to the pair "employee + organisation" rather than
        to either of the things being written.

        A superuser administers everything for the same reason they see everything:
        they already write through the Django admin, so a ban here would close nothing
        and would only split one question into two answers. It is said here as well as
        in `Org`: a space may belong to no organisation at all, and going through the
        filter would hide such a space from the very user who sees all of them.
        """
        if user.is_superuser:
            return self
        return self.filter(org_id__in=Org.objects.administered_by(user))

    def buildings_visible_to(self, user):
        """The business centres available to the user: a BC is a space of type building."""
        return self.visible_to(user).filter(type=DictSpaceType.BUILDING)

    def buildings_administered_by(self, user):
        """The business centres the user may maintain the data of — the ones a batch of
        documents may be attached to."""
        return self.administered_by(user).filter(type=DictSpaceType.BUILDING)

    def floors_of(self, building):
        """The floors of a building bottom to top — the card's "Этажи" section and the switcher.

        It does no filtering by organisation: that is done by `visible_to`, through
        which this method is called — otherwise there would be a second place deciding
        whose data to show.
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
        """The project above a space — shown as a label rather than as a navigation level.

        There are exactly two levels above a BC, the site and the project, so the chain
        of parents is unwound in two steps: that also keeps a looping `parent` from
        hanging the request.
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
    """Drawings are stored by floor: the directory shows what a file belongs to."""
    return f"floor_plans/{instance.floor_id}/{filename}"


class FloorPlanQuerySet(models.QuerySet):
    def visible_to(self, user):
        """A plan is visible wherever its floor is — the checkpoint stays single (ADR 0001).

        There is deliberately no filtering by organisation of its own here: a plan has
        no `org`, and a second place deciding whose data to show is a way for the two
        to drift apart one day.
        """
        return self.filter(floor__in=Space.objects.visible_to(user))

    def overlapping(self, begin, end):
        """Plans whose periods touch the range from `begin` to `end` inclusive.

        Both ends belong to the period, so a plan starting on the day the range closes
        overlaps it. An open end — of the plan or of the range — means "to this day"
        and never finishes, so any start after such a plan falls inside it.

        One query shape for two questions: which plan is in force on a given day is an
        overlap with a range of one day, and non-overlapping periods are the same thing
        over the range of the new plan.
        """
        began_by_the_end = Q() if end is None else Q(valid_from__lte=end)
        not_ended_before_the_begin = Q(valid_to__isnull=True) | Q(valid_to__gte=begin)
        return self.filter(began_by_the_end).filter(not_ended_before_the_begin)

    def in_force_on(self, day):
        """Plans in force on this day: the period has begun and has not ended yet.

        The periods of one floor's plans do not overlap, so a floor has at most one
        such plan.

        Not "the latest by start date": the plan of a future rebuild is already on
        record while the floor still looks different today, and work is planned against
        today's one.
        """
        return self.overlapping(day, day)


class FloorPlan(CommonModel):
    """A floor plan: the drawing of a floor and the coordinate system its contours live in.

    Not a document: a document certifies and carries a number, a date and an issuing
    party, whereas a plan shows — and is the coordinate system for the spaces. Nor is
    it a field of a space: a plan belongs to a floor and relates to a period, and after
    a rebuild the previous one is kept (ADR 0003).

    The file sits in a protected directory and is served by a view through the same
    checkpoint as everything else: `MEDIA_URL` is not set, so no direct link to it can
    be assembled.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    floor = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="floor_plans", verbose_name="этаж"
    )
    file = models.FileField(upload_to=plan_file_path, verbose_name="файл SVG")
    #: The `viewBox` of the drawing: the contours on top are drawn with it too,
    #: otherwise they drift away from it.
    view_box = models.CharField(max_length=128, editable=False, verbose_name="viewBox")
    #: The `id`s of paths in the drawing that found no space on the floor. They are
    #: noticed while parsing but shown on the floor screen — between those two moments
    #: they have to be kept somewhere, and the plan keeps them itself: the drawing is
    #: parsed once (ADR 0003) and is never re-matched against today's tree of spaces.
    unmatched_ids = models.JSONField(
        default=list, editable=False, verbose_name="непривязанные пути"
    )
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
        """The `viewBox` aspect ratio for CSS: the drawing and the contours keep one frame."""
        _, _, width, height = self.view_box.split()
        return f"{width} / {height}"

    def clean(self):
        """The reason for a rejection is named on the form, not thrown as a 500 on save."""
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
        """A plan and its contours appear in one operation: separately they do not appear at all.

        Parsing happens before writing: an unreadable file leaves behind neither a row
        in the database nor a file in storage. Saving again does not rebuild the
        contours — the drawing is parsed once and stays with the spaces it was drawn
        with (ADR 0003), so editing the period does not move the plan onto today's tree
        of spaces. A new layout is a new plan, not a new file on the old one.
        """
        self._validate_period()
        if not self._state.adding:
            super().save(*args, **kwargs)
            return
        reading, contours = self._read_contours()
        self.view_box = reading.view_box
        self.unmatched_ids = list(reading.unmatched)
        with transaction.atomic():
            super().save(*args, **kwargs)
            Contour.objects.bulk_create(contours)

    def _validate_period(self):
        """A period must be a period and must not touch a neighbouring period of the floor.

        The rule stands on the plan itself rather than on a form: the admin, the future
        upload form and code all write through the same path and get the same
        rejection. Otherwise "the plan in force" would stop being definite — there
        would be two plans for today, and which of them to show would be decided by the
        sort order.

        The previous plan is not closed by itself either: dating a rebuild by the day of
        the upload invents a fact, the same in nature as the `year_built = 1900` stage 1
        was moving away from. The date is named by the uploader, and the system rejects.
        """
        if self.valid_from is None or self.floor_id is None:
            return
        refuse_a_period_that_ends_before_it_begins(self.valid_from, self.valid_to)
        conflicting = self._conflicting_plans().first()
        if conflicting is not None:
            closes = f"{conflicting.valid_to:%d.%m.%Y}" if conflicting.valid_to else "по сей день"
            raise ValidationError(
                f"Период пересекается с планом этажа за {conflicting.valid_from:%d.%m.%Y} — "
                f"{closes}. У этажа не бывает двух действующих планов: закройте прежний "
                f"период датой перепланировки."
            )

    def _conflicting_plans(self):
        """Plans of the same floor whose periods touch this one — there must be none.

        An adjacent plan is not a conflict: the one that overlaps starts on the day the
        previous one closes, not on the day after it.
        """
        return (
            FloorPlan.objects.filter(floor_id=self.floor_id)
            .exclude(pk=self.pk)
            .overlapping(self.valid_from, self.valid_to)
        )

    def _read_contours(self):
        """The parsed drawing and its contours, already matched with the spaces of the floor.

        The reading is handed back whole: what remains from the plan is not only the
        geometry but also the paths that found no space — those are the finding of the
        parse.
        """
        spaces = self._spaces_by_code()
        reading = read_plan(b"".join(self.file.chunks()), spaces.keys())
        return reading, [
            Contour(plan=self, space=spaces[contour.code], path_d=contour.path_d)
            for contour in reading.contours
        ]

    def _spaces_by_code(self):
        """The spaces of the floor by code — what the paths of the drawing are matched against.

        The interior of the building arrives in one query and is walked by the same
        descent as the tree on the screen: the plan and the tree must count the same
        thing as the spaces of a floor.
        """
        inside = Space.objects.filter(building_id=self.floor.building_id)
        return {space.code: space for space in spaces_under(self.floor, inside) if space.code}


class Contour(CommonModel):
    """The boundary of a space on a particular plan — the pair "plan + space" (ADR 0003).

    The path is stored as text rather than as a separate file: a contour is a few
    hundred bytes, and as files they would cost a floor 82 requests, while nothing
    would check that their `viewBox` matches the plan's.
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
    """Old certificates and plans must keep being found by the former code."""

    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="code_history")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255, blank=True, null=True)
    valid_from = models.DateField()
    valid_to = models.DateField(blank=True, null=True)
    reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [models.Index(Lower("code"), name="space_code_hist_idx")]


class SpaceLink(CommonModel):
    """A shaft passes through a floor, a staircase connects levels, and so on."""

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

