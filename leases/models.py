"""Договор аренды: факты, которыми красят план и считают свободное (ADR 0006)."""

import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from building_passport.models import Space
from parties.models import Org, Party

from . import lease_display


class CommonModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')

    class Meta:
        abstract = True


class LeaseQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Договоры, доступные пользователю, — единственное место фильтрации аренды.

        Третий чокпоинт рядом с `visible_to` и `administered_by` у пространств и
        устроен так же: фильтрация в одном месте, а не собранная в каждом
        представлении. Спрашивается своя организация договора, а не организации
        помещений предмета — вывод видимости из предмета отклонён (ADR 0009): «видно,
        если видно любое» отдаёт клиенту A предметы и ставки клиента B, а «видно,
        если видны все» прячет договор от обоих сразу.

        Суперпользователь видит всё по той же причине, что и у пространств: проблема
        клиента должна воспроизводиться без выписывания себе членства.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(org_id__in=user.memberships.values("org_id"))

    def administered_by(self, user):
        """Договоры, которые пользователь вправе вести, — чокпоинт записи (ADR 0005).

        Отдельный от `visible_to` вопрос, как и у пространств: читать договоры
        организации и заводить их — разные права, и второе даётся флагом на
        членстве. Спрашивается он у организаций, а не у членств напрямую: тот же
        ответ нужен форме, которая предлагает выбор организации, и два способа его
        получить однажды разошлись бы.
        """
        return self.filter(org__in=Org.objects.administered_by(user))


class Lease(CommonModel):
    """Соглашение, по которому сторона занимает помещения на срок за плату.

    Не документ: скан подшивается к договору `Document`'ом, но фактами служит сам
    договор — слой «сроки договоров» красит контуры запросом к периодам, а счёт
    свободного — запросом к предмету, и ни то, ни другое не вынимается из JSON
    внутри вложения (ADR 0006).

    Обязательны арендатор, дата начала и хотя бы один предмет (ADR 0007). Первые
    два стоят на самой модели, а третий — единственное правило аренды, которое на
    ней стоять не может: предмет ссылается на договор, то есть заводится строкой
    позже, и проверка на `save()` отказала бы самому первому сохранению. Держит
    его тот, кто заводит договор целиком, — сейчас инлайн админки, дальше форма
    (#28). `Lease.objects.create()` без предметов при этом проходит: договор без
    предмета, заведённый скриптом, останется молчаливо пустой записью.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    #: Своя организация, а не выведенная из помещений предмета: договор называет
    #: несколько помещений и не привязан к зданию вовсе, поэтому вывод перестаёт
    #: быть выводом и становится выбором между утечкой и тихо исчезающей записью
    #: (ADR 0009). Отступление от образца `FloorPlan` намеренное.
    org = models.ForeignKey(
        Org, on_delete=models.PROTECT, related_name="leases", verbose_name="организация"
    )
    #: Арендатором Сторону делает договор и только он: отдельной роли «арендатор»
    #: у Стороны нет, иначе на вопрос «кто здесь арендатор» нашлось бы два ответа
    #: (ADR 0008).
    tenant = models.ForeignKey(
        Party, on_delete=models.PROTECT, related_name="leases", verbose_name="арендатор"
    )
    valid_from = models.DateField(verbose_name="действует с")
    valid_to = models.DateField(blank=True, null=True, verbose_name="действует по")
    number = models.CharField(max_length=128, blank=True, null=True, verbose_name="номер")
    signed_at = models.DateField(blank=True, null=True, verbose_name="дата подписания")
    #: Пролонгация — новый договор со ссылкой на прежний, а не передвинутый конец
    #: прежнего: при продлении меняется ставка, и правка на месте стёрла бы ответ
    #: на «по какой ставке помещение сдавалось в марте» (ADR 0007). Прежний договор
    #: удалением не пропадает: цепочку рвать молча нечем, и снять ссылку придётся
    #: руками.
    prolongs = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="prolonged_by",
        verbose_name="пролонгирует договор",
    )

    objects = LeaseQuerySet.as_manager()

    class Meta:
        ordering = ("-valid_from",)
        verbose_name = "договор аренды"
        verbose_name_plural = "договоры аренды"

    def __str__(self):
        named = f"№{self.number}" if self.number else f"от {self.valid_from:%d.%m.%Y}"
        return f"Договор {named} — {self.tenant}"

    def clean(self):
        """Причина отказа называется на форме, а не падает пятисоткой при сохранении."""
        super().clean()
        self._validate_period()

    def save(self, *args, **kwargs):
        """Срок проверяется и здесь, а не только на предмете.

        Пересечение зависит от двух вещей — периода договора и помещения предмета,
        — и заводятся они порознь. Стой проверка только на предмете, правка срока
        уже заведённого договора прошла бы мимо неё и наложила бы его на соседний.
        """
        self._validate_period()
        super().save(*args, **kwargs)

    def _validate_period(self):
        """Период должен быть периодом и не должен задевать соседний по каждому предмету.

        Отказ предмета переносится сюда без привязки к полю: на странице договора
        поля «помещение» нет — оно живёт в предмете, — и адресованный ему отказ
        уронил бы форму вместо того, чтобы на ней показаться. Помещение при этом
        не теряется: оно названо в самом сообщении.
        """
        if self.valid_from is None:
            return
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValidationError(
                {"valid_to": "Период заканчивается раньше, чем начинается."}
            )
        if self._state.adding:
            return
        for subject in self.subjects.select_related("space"):
            try:
                subject._validate(lease=self)
            except ValidationError as refusal:
                raise ValidationError(refusal.messages) from refusal


class LeaseSubjectQuerySet(models.QuerySet):
    def overlapping(self, begin, end):
        """Предметы, чьи договоры задевают отрезок от `begin` до `end` включительно.

        Оба конца входят в период, поэтому договор, начинающийся в день окончания
        отрезка, с ним пересекается: в этот день действовали бы оба. Открытый конец
        — что у договора, что у отрезка — означает «по сей день» и не кончается
        никогда, так что любое начало после такого договора в него попадает.

        Форма запроса та же, что у периодов планов этажа (`FloorPlanQuerySet`), и по
        той же причине: правило аренды — прямое продолжение ADR 0004 (ADR 0007).
        Общего кода у них нет намеренно: там период лежит на самой строке, здесь —
        на договоре над ней, и склейка ради четырёх строк стоила бы дороже.
        """
        began_by_the_end = Q() if end is None else Q(lease__valid_from__lte=end)
        not_ended_before_the_begin = Q(lease__valid_to__isnull=True) | Q(
            lease__valid_to__gte=begin
        )
        return self.filter(began_by_the_end).filter(not_ended_before_the_begin)


class LeaseSubject(CommonModel):
    """Помещение, названное договором, вместе со своей ставкой и площадью.

    Ставка и договорная площадь стоят на предмете, а не на договоре: офис и склад
    одним соглашением не обязаны идти по одной ставке. Договорная площадь — это
    полезная плюс доля МОП по коэффициенту, то есть условие соглашения, а не обмер
    здания, поэтому ни `Space.area_m2`, ни `SpaceArea` отсюда не пишутся никогда
    (ADR 0006).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lease = models.ForeignKey(
        Lease, on_delete=models.CASCADE, related_name="subjects", verbose_name="договор"
    )
    space = models.ForeignKey(
        Space,
        on_delete=models.PROTECT,
        related_name="lease_subjects",
        verbose_name="помещение",
    )
    rate = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="ставка"
    )
    area_m2 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="договорная площадь",
    )

    objects = LeaseSubjectQuerySet.as_manager()

    class Meta:
        verbose_name = "предмет договора"
        verbose_name_plural = "предметы договора"
        constraints = [
            models.UniqueConstraint(fields=["lease", "space"], name="lease_subject_uq"),
        ]

    def __str__(self):
        return f"{self.space} по {self.lease}"

    def clean(self):
        """Причина отказа называется на форме, а не падает пятисоткой при сохранении."""
        super().clean()
        self._validate()

    def save(self, *args, **kwargs):
        """Правило стоит на модели, а не на форме (ADR 0007).

        Админка, будущая форма договора и любой скрипт пишут одним путём и получают
        один и тот же отказ теми же словами. Иначе «сдано ли помещение сегодня»
        перестало бы иметь один ответ, а слой красил бы контур тем договором,
        который выбрала сортировка.
        """
        self._validate()
        super().save(*args, **kwargs)

    def _validate(self, lease=None):
        """Отказы предмета: чужая организация, неарендопригодное и пересечение.

        Договор передаётся отдельно там, где он ещё не в базе: в админке предметы
        проверяются раньше, чем сохранён сам договор, и спрашивать его по ссылке
        в этот момент нечем.
        """
        lease = lease or self._lease_in_hand()
        if lease is None or self.space_id is None:
            return
        if self.space.org_id != lease.org_id:
            raise ValidationError(
                {
                    "space": f"Помещение {lease_display.space_named(self.space)} принадлежит другой "
                    f"организации. Договор называет помещения только своей: "
                    f"предмет и организация договора расходиться не должны."
                }
            )
        if not self.space.is_leasable:
            raise ValidationError(
                {
                    "space": f"Помещение {lease_display.space_named(self.space)} не арендопригодно и "
                    f"предметом договора не бывает: МОП и техническое помещение "
                    f"арендатору не сдаются."
                }
            )
        if lease.valid_from is None:
            return
        conflicting = self._conflicting_subjects(lease).select_related("lease").first()
        if conflicting is not None:
            raise ValidationError(
                {
                    "space": f"Помещение {lease_display.space_named(self.space)} уже сдано: "
                    f"{conflicting.lease}, "
                    f"{lease_display.period(conflicting.lease)}. "
                    f"У помещения не бывает двух арендаторов на один день: "
                    f"закройте прежний период датой расторжения."
                }
            )

    def _conflicting_subjects(self, lease):
        """Предметы чужих договоров на то же помещение, чьи периоды задевают этот.

        Проверка ведётся по помещению, а не по договору: договор на три помещения
        может конфликтовать ровно по одному из них, и назвать надо именно его.
        Свой договор из выборки исключён — иначе правка предмета спорила бы сама с
        собой, а не с соседним договором.
        """
        others = LeaseSubject.objects.filter(space_id=self.space_id)
        if lease.pk is not None:
            others = others.exclude(lease_id=lease.pk)
        return others.overlapping(lease.valid_from, lease.valid_to)

    def _lease_in_hand(self):
        """Договор предмета, если он вообще известен, — хоть из памяти, хоть из базы.

        Спрашивается именно ссылкой, а не по `lease_id`: у незаписанного договора
        ключа ещё нет — админка обнуляет его, пока родитель не сохранён, — но сам
        объект уже есть, и период с организацией берутся с него. Иначе проверка
        молча отступала бы ровно там, где договор заводят.
        """
        try:
            return self.lease
        except Lease.DoesNotExist:
            return None
