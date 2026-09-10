from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CommonModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')

    class Meta:
        abstract = True


class DictionaryCommonModel(CommonModel):
    code = models.CharField(max_length=256, unique=True, null=True, blank=True)
    slug = models.CharField(max_length=256, unique=True, null=True, blank=True)
    name = models.CharField(max_length=1024, unique=True)
    short_name = models.CharField(max_length=1024, unique=True)
    sort_order = models.IntegerField(unique=True, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    external_id = models.CharField(max_length=1024, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True


class DictSpaceType(models.TextChoices):
    PROJECT = "project", "Проект"
    SITE = "site", "Площадка"
    BUILDING = "building", "Здание"
    WING = "wing", "Блок / секция / крыло"
    FLOOR = "floor", "Этаж"
    MEZZANINE = "mezzanine", "Антресоль"
    ROOM = "room", "Помещение"
    SHAFT = "shaft", "Шахта"
    STAIRWELL = "stairwell", "Лестничная клетка"
    ROOF = "roof", "Кровля"
    FACADE = "facade", "Фасад"
    TERRITORY = "territory", "Прилегающая территория"
    PARKING_SPOT = "parking_spot", "Машиноместо"
    VOID = "void", "Проём второго света / атриум"
    OTHER = "other", "Прочее"


class DictServiceRole(models.TextChoices):
    PRIMARY = "primary", "Основное"
    BACKUP = "backup", "Резерв"
    PARTIAL = "partial", "Частичное"


class DictSpaceSubtype(DictionaryCommonModel):
    type = models.TextField(choices=DictSpaceType.choices)
    grp = models.CharField(max_length=256, null=True, blank=True)
    pass

    def __str__(self):
        return f"{self.name}"


class DictSystem(DictionaryCommonModel):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    is_leaf = models.BooleanField(null=True, blank=True)
    pass

    def __str__(self):
        return self.name


class DictBuilding(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictRequirementCode(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictAreaKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictSpaceRelationKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictSpaceStatus(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictZoneKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictAssetRelationKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictElementCategory(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictConditionGrade(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictDocumentRole(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictBank(DictionaryCommonModel):
    """Банк, чтобы «Каспи» и «Kaspi Bank» были одним банком: БИК и название, и ничего больше.

    The БИК lives in the base's `code`, the column that already means «чем эта строка
    названа в мире за пределами BCMP», so the справочник adds no column of its own — which
    is the whole decision. `bank.csv` also carries `is_license_revocation` and
    `bik_end_date_bvu`, and those do not come across: BCMP has nowhere to learn that a
    licence was revoked, so a year from now the screen would state a revoked one as valid —
    the very thing a близнец is attached whole or not at all for (ADR 0011, ADR 0022). An
    absent answer sends the reader to check; a confidently wrong one does not.

    Банки без БИК — сорок три ликвидированных из семидесяти шести — остаются в справочнике:
    комплект платёжных реквизитов, заведённый при АТФБанке, называет АТФБанк, и вычеркнутый
    из списка банк сделал бы позавчерашнюю платёжку нечитаемой. Their `code` stays empty,
    which is what «этим БИК уже никто не платит» looks like.
    """

    class Meta:
        verbose_name = "банк"
        verbose_name_plural = "банки"

    def __str__(self):
        return self.name


class DictLineOfBusiness(DictionaryCommonModel):
    """Сфера деятельности Стороны — около двадцати пяти отраслей, составленных от календаря.

    Государственный ОКЭД не используется. Справочник заведён ради одного вывода — из сферы
    получается профессиональный повод (ADR 0023), — а ОКЭД перечисляет полторы тысячи
    позиций, у которых праздника почти ни у одной нет: 99% списка ничего не выводят, зато
    администратор УК, выбирая из полутора тысяч строк, выберет не ту (ADR 0024).

    Отрасль без праздника — обычное дело, а не пробел: общепит сидит в БЦ этажами, и своего
    дня в перечне у него нет. Список отвечает на свой вопрос целиком и умещается в один
    `<select>`; цена — расхождение с тем, что записано у Стороны в свидетельстве, и она
    принята.
    """

    class Meta:
        verbose_name = "сфера деятельности"
        verbose_name_plural = "сферы деятельности"

    def __str__(self):
        return self.name


class DictProfessionalHoliday(DictionaryCommonModel):
    """Профессиональный праздник — правило, по которому день вычисляется, а не сам день.

    Двух форм: либо число и месяц — День работников связи семнадцатого мая, — либо
    «n-й такой-то день недели такого-то месяца»: День строителя во второе воскресенье
    августа. Ровно одна заполнена, и это утверждает `CheckConstraint`, потому что строка о
    двух правилах — это два ответа на вопрос «когда», и второй прочитают ровно так же
    уверенно, как первый.

    Года нет нигде. Разложенные по годам даты читать проще, но это величина, которая тихо
    устаревает: в первый же год, который никто не дозаполнил, экран скажет, что праздников
    нет, — то самое, из-за чего в справочник банков не переносятся отзывы лицензий
    (ADR 0022, ADR 0027).

    Справочник поставляется с системой и администратору организации не принадлежит:
    календарь РК одинаков у всех клиентов, и отданный на ведение каждому он дал бы у трёх
    управляющих компаний три разных Дня строителя.
    """

    class Weekday(models.IntegerChoices):
        """Дни недели по ISO, как их считает `date.isoweekday()`.

        Не нумерация Django (`__week_day`, где единица — воскресенье): правило разрешается
        в дату питоном, на полке и на экране Стороны, а не запросом, и две нумерации в одном
        проекте разошлись бы на воскресенье — то есть ровно на том дне, на который приходится
        большинство профессиональных праздников РК.
        """

        MONDAY = 1, "понедельник"
        TUESDAY = 2, "вторник"
        WEDNESDAY = 3, "среда"
        THURSDAY = 4, "четверг"
        FRIDAY = 5, "пятница"
        SATURDAY = 6, "суббота"
        SUNDAY = 7, "воскресенье"

    class WeekOfMonth(models.IntegerChoices):
        """Какая по счёту неделя месяца — и «последняя» отдельным значением.

        «Последнее» — не «пятое» и не «четвёртое». Перечень РК различает их сам: День
        работников торговли — четвёртое воскресенье июля, День шахтёра — последнее
        воскресенье августа. В августе воскресений бывает и четыре, и пять, так что
        свернуть одно в другое значит сдвинуть день шахтёра на неделю в половине лет.
        """

        FIRST = 1, "первая"
        SECOND = 2, "вторая"
        THIRD = 3, "третья"
        FOURTH = 4, "четвёртая"
        LAST = -1, "последняя"

    class Month(models.IntegerChoices):
        JANUARY = 1, "январь"
        FEBRUARY = 2, "февраль"
        MARCH = 3, "март"
        APRIL = 4, "апрель"
        MAY = 5, "май"
        JUNE = 6, "июнь"
        JULY = 7, "июль"
        AUGUST = 8, "август"
        SEPTEMBER = 9, "сентябрь"
        OCTOBER = 10, "октябрь"
        NOVEMBER = 11, "ноябрь"
        DECEMBER = 12, "декабрь"

    #: Праздник принадлежит отрасли, а не Стороне: «День строителя» у трёхсот арендаторов —
    #: это триста копий одной даты, которые разойдутся (ADR 0023). `CASCADE`: убранная из
    #: справочника отрасль уносит свой праздник, которому больше некого поздравлять.
    line_of_business = models.ForeignKey(
        DictLineOfBusiness,
        on_delete=models.CASCADE,
        related_name="holidays",
        verbose_name="сфера деятельности",
    )
    #: Общий у обеих форм: месяц называют и «двадцать восьмое июня», и «второе воскресенье
    #: августа».
    month = models.PositiveSmallIntegerField(choices=Month.choices, verbose_name="месяц")
    day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name="число",
    )
    week_of_month = models.SmallIntegerField(
        choices=WeekOfMonth.choices, null=True, blank=True, verbose_name="неделя месяца"
    )
    weekday = models.SmallIntegerField(
        choices=Weekday.choices, null=True, blank=True, verbose_name="день недели"
    )

    class Meta:
        verbose_name = "профессиональный праздник"
        verbose_name_plural = "профессиональные праздники"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(day__isnull=False, week_of_month__isnull=True, weekday__isnull=True)
                    | models.Q(
                        day__isnull=True, week_of_month__isnull=False, weekday__isnull=False
                    )
                ),
                name="professional_holiday_one_rule",
            ),
        ]

    def clean(self):
        """Причина отказа называется на форме, а не прилетает пятисоткой из базы.

        The constraint stays the database's last word — a скрипт, писавший мимо формы, must
        meet the same refusal — but the человек in the admin meets it in words, and next to
        the field just filled in. Same shape as the период of an аренда.
        """
        super().clean()
        by_day = self.day is not None
        week, weekday = self.week_of_month is not None, self.weekday is not None

        if by_day and (week or weekday):
            raise ValidationError(
                {"day": "Праздник задаётся либо числом месяца, либо днём недели, но не обоими."}
            )
        if not by_day and not (week or weekday):
            raise ValidationError({"day": "Укажите число месяца — либо день недели и неделю."})
        # Названо на той половине, которой не хватает: «второе августа» — не правило, и
        # человеку надо дописать день недели, а не переписывать неделю.
        if week and not weekday:
            raise ValidationError({"weekday": "Неделя месяца без дня недели ничего не задаёт."})
        if weekday and not week:
            raise ValidationError(
                {"week_of_month": "День недели без недели месяца ничего не задаёт."}
            )

    def __str__(self):
        return self.name
