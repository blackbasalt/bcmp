import uuid

from django.contrib.auth.models import User
from django.db import models

from dictionary.models import DictBank, DictLineOfBusiness

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
    """Any party: a legal entity or a natural person. Once for the whole system."""
    class Kind(models.TextChoices):
        COMPANY = "company", "Организация"
        PERSON = "person", "Физлицо"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=255)
    bin_iin = models.CharField(unique=True, max_length=32, blank=True, null=True)
    #: Чем Сторона занимается — единственное, что организация записывает не в учётную
    #: карточку, а на саму Сторону. Публичный факт без двух версий: 637 частных мнений о том,
    #: чем занимается «Центр крепежных систем», разошлись бы ни за чем и сломали бы вывод
    #: профессионального повода, ради которого справочник и заведён (ADR 0020, ADR 0023).
    #:
    #: Необязательное: 699 Сторон уже заведены и ни у одной сферы не проставлено, а полка,
    #: требующая её заполнить, не показала бы ни одной. `PROTECT` — убрать из справочника
    #: отрасль, на которую кто-то ссылается, значит стереть сферу у Стороны молча.
    line_of_business = models.ForeignKey(
        DictLineOfBusiness,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="parties",
        verbose_name="сфера деятельности",
    )
    external_id = models.CharField(max_length=1024, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


def stands_for_herself(party) -> bool:
    """Физлицо: представителя у неё нет и быть не может.

    Одно правило, читаемое отовсюду, и потому написанное один раз: у физлица нет блока
    контактных лиц вовсе (ADR 0025), и оттого же её день рождения стоит на карточке — повесить
    личный повод больше не на кого. Тем же правилом решается, какие створки достанутся её
    экрану, какая отправка отвечает 404 и чьи дни рождения становятся поводами. Сказанное в
    двух местах, оно однажды показало бы физлицу блок, в котором никого не бывает, или назвало
    бы поводом день рождения человека, которого на экране уже нет.

    Стоит здесь, а не на экране Стороны, где читалось прежде: род решает не только вёрстку, и
    `occasions` — второй его читатель, которому до экрана не дотянуться.
    """
    return party.kind == Party.Kind.PERSON


class OrgQuerySet(models.QuerySet):
    def administered_by(self, user):
        """The organisations whose data the user may maintain — the write checkpoint (ADR 0005).

        The question lives here, where the right itself does: administratorship belongs to
        the pair "employee + organisation", and everything written is written into some
        organisation's data. Spaces and documents ask this one place rather than each
        assembling the same filter over memberships — two of them would be two answers to
        one question, and the second one to drift would let a reader write.

        A superuser administers everything for the same reason they see everything: they
        already write through the Django admin, so a ban here would close nothing.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(pk__in=user.memberships.filter(is_admin=True).values("org_id"))

    def handled_by(self, user):
        """The organisations the reader handles — a question about them, not about data.

        It disposes of no permissions and selects no rows: whose data to show is decided by
        the chokepoints (ADR 0001, ADR 0006), and what is worked out here is only whether a
        screen needs an «Организация» column at all. One employee handling two clients asks
        "whose is this" of every row; one handling a single client would get a column
        repeating one word down the whole table.

        It is asked about the reader and not about what is shown, so the column holds on
        even when the second client has nothing loaded yet — which is exactly when whoever
        handles two of them most needs to know whose shelf they are looking at.

        A superuser reads on everyone's behalf, so all the organisations are theirs.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(pk__in=user.memberships.values("org_id"))


class Org(CommonModel):
    """A tenant of the platform. A thin layer over Party, not a duplicate."""
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
    """A user's access to an organisation. One employee may belong to several."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    #: The right to maintain this organisation's data from the application, not merely to
    #: read it. It sits on the membership rather than on the user: being an administrator
    #: belongs to the pair "employee + organisation", and an employee who maintains one
    #: client stays an ordinary reader for another. A global `is_staff` does not express
    #: that — the same argument as for the isolation by organisation itself (ADR 0001,
    #: ADR 0005).
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
    """A party's role in a particular context and over a particular period."""
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


class PartyRecordQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Учётные карточки, доступные читателю, — единственное место отбора (ADR 0020).

        Той же формы, что `SpaceQuerySet.visible_to` и `DocumentQuerySet.visible_to`, и по
        той же причине: суперпользователь видит всё, аноним ничего, остальные — организации
        своих членств. Третья полка — первая, чья изоляция не достаётся даром: у Стороны
        колонки `org` нет и не будет, потому что арендатор, которого ещё никто не встречал,
        должен оставаться находимым при заведении аренды (`leases/party_choice.py`).
        Изолирована не Сторона, а знание о ней, и вот здесь оно и отбирается.

        Договор обеих полок держится и здесь: привратник первым, отбор после него, никогда
        вместо (ADR 0006).
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(org_id__in=user.memberships.values("org_id"))

    def administered_by(self, user):
        """Карточки, которые читатель вправе вести, — контрольная точка записи (ADR 0005).

        Вопрос, отдельный от `visible_to`: читать данные организации и вести их — разные
        права. Какие это организации, здесь не выводится, а спрашивается у самих
        организаций — довод целиком в `OrgQuerySet.administered_by`, включая и то, почему
        суперпользователь ведёт всё.
        """
        if user.is_superuser:
            return self
        return self.filter(org_id__in=Org.objects.administered_by(user))


class PartyRecord(CommonModel):
    """Учётная карточка: что организация знает о Стороне, на паре «Сторона + организация».

    Существование Стороны — публичный факт, знание о ней — нет (ADR 0020). Название, БИН и
    сфера деятельности остаются одной строкой на всю систему, находимой любым, кто заводит
    аренду; платёжные реквизиты, контактные лица и поводы висят здесь и второй управляющей
    компании, знакомой с тем же юрлицом, не показываются.

    Кроме пары и дня рождения физлица на карточке нет ничего: она и есть пара, а всё
    остальное — отдельными строками на ней, потому что и контактных лиц, и комплектов
    реквизитов бывает сколько угодно.

    Названа `PartyRecord`, а не `PartyDossier`: «досье» стоит в словаре под _Избегать_.
    Экранное слово «карточка» в имя модели не попадает намеренно — карточкой на экранах
    зовут и карточку помещения, которая ничего общего с этой не имеет.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    #: `CASCADE`, а не `PROTECT`: карточка — это знание о Стороне, и без Стороны оно ни о
    #: чём. Из приложения Сторона не удаляется вовсе (ADR 0028), а администратор платформы
    #: удаляет её в админке, где страница подтверждения перечисляет всё, что уйдёт следом, —
    #: `PROTECT` вместо этого запретил бы удаление насовсем и оставил бы ADR без исполнителя.
    party = models.ForeignKey(
        Party, on_delete=models.CASCADE, related_name="records", verbose_name="сторона"
    )
    #: Чья карточка. `PROTECT`, как `Space.org` и `Document.org`: организация из-под своих
    #: же данных не удаляется, и уход клиента с платформы — решение, а не побочный эффект.
    org = models.ForeignKey(
        Org, on_delete=models.PROTECT, related_name="party_records", verbose_name="организация"
    )
    #: День рождения физлица — личный повод там, где повесить его не на кого: контактных лиц
    #: у физлица нет (ADR 0025). Лежит на карточке, а не на Стороне, потому что дата рождения
    #: есть персональные данные и второй управляющей компании их не показывают (ADR 0023).
    born_on = models.DateField(null=True, blank=True, verbose_name="день рождения")

    objects = PartyRecordQuerySet.as_manager()

    class Meta:
        verbose_name = "учётная карточка"
        verbose_name_plural = "учётные карточки"
        constraints = [
            models.UniqueConstraint(fields=["party", "org"], name="party_record_uq"),
        ]

    def __str__(self):
        return f"{self.party} — {self.org}"


class ContactPerson(CommonModel):
    """Человек внутри Стороны, с которым организация имеет дело: руководитель, бухгалтер.

    Стороной не является: он ни с кем не в отношениях, аренду на него не заводят и БИН ему
    не нужен, а заведённый Стороной он встал бы в один список со своим же ТОО. Тот же
    человек, зарегистрированный как ИП, — отдельная Сторона: ИП может кончиться, а человек
    остаться.

    Живёт в учётной карточке, а не на Стороне: мобильный директора, который дали одной
    управляющей компании, второй не показывают (ADR 0020).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(
        PartyRecord,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="учётная карточка",
    )
    full_name = models.CharField(max_length=255, verbose_name="ФИО")
    #: Свободным текстом: справочник должностей был бы словарём привычек одного клиента —
    #: у одного «главный инженер», у второго «технический директор», — и заводить его
    #: пришлось бы каждому заново, чтобы получить те же строки.
    position = models.CharField(max_length=255, blank=True, null=True, verbose_name="должность")
    phone = models.CharField(max_length=64, blank=True, null=True, verbose_name="телефон")
    email = models.EmailField(blank=True, null=True, verbose_name="почта")
    #: Личный повод. Необязательный: «кому звонить» и «кого поздравить» — один список, и
    #: инженер, чей день рождения неизвестен, из него не выпадает.
    born_on = models.DateField(null=True, blank=True, verbose_name="день рождения")

    class Meta:
        # По имени, а не по заведению: список читают глазами, разыскивая в нём человека, и
        # порядок, в котором его когда-то вписали, для этого не значит ничего. Без ordering
        # порядок решала бы таблица от запроса к запросу.
        ordering = ("full_name",)
        verbose_name = "контактное лицо"
        verbose_name_plural = "контактные лица"

    def __str__(self):
        return self.full_name


class PaymentDetails(CommonModel):
    """Куда платить Стороне: банк, счёт, КБе. Комплектами, сколько нужно.

    Реквизитами документа не являются: те — учётные поля документа, эти — платёжные
    Стороны. Проводкой тоже: BCMP хранит, куда платить, и не хранит, сколько заплатили.

    Закрытый комплект не затирается новым, а остаётся рядом: платёжка, выписанная
    позавчера, должна сходиться с тем, что на экране. Оттого же и `PROTECT` на банк.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(
        PartyRecord,
        on_delete=models.CASCADE,
        related_name="payment_details",
        verbose_name="учётная карточка",
    )
    #: Из справочника, а не строкой: «Каспи» и «Kaspi Bank» — один банк, и БИК говорит об
    #: этом, а написание нет. `PROTECT`: банк, вычеркнутый из справочника из-под заведённого
    #: комплекта, сделал бы позавчерашнюю платёжку нечитаемой (ADR 0022).
    bank = models.ForeignKey(
        DictBank, on_delete=models.PROTECT, related_name="payment_details", verbose_name="банк"
    )
    account = models.CharField(max_length=64, verbose_name="счёт (IBAN)")
    kbe = models.CharField(max_length=8, blank=True, null=True, verbose_name="КБе")
    #: Основной — флаг на комплекте, а не указатель на карточке: закрывая счёт, переписывают
    #: комплект, а карточку не трогают вовсе. Один он или их два, база не утверждает: правка
    #: «этот теперь основной» шла бы тогда в два сохранения, из которых первое отказывают, —
    #: экран берёт первый по порядку, а порядок держит основной наверху.
    is_primary = models.BooleanField(default=False, db_default=False, verbose_name="основной")

    class Meta:
        # Основной первым: обычный случай отвечается, ничего не разворачивая (спека,
        # история 21). Второй ключ — не украшение: комплектов на карточке бывает несколько,
        # и без него порядок непомеченных решала бы таблица.
        ordering = ("-is_primary", "created_at")
        verbose_name = "комплект платёжных реквизитов"
        verbose_name_plural = "платёжные реквизиты"

    def __str__(self):
        return f"{self.bank} — {self.account}"
