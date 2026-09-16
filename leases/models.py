"""Аренда — кто занимает часть помещения, с какого дня по какой и по какой ставке.

An app of its own, with no `urls.py` and no menu item. ADR 0016 made a раздел a Django app
because the sidebar works out the open раздел from `request.resolver_match.app_name`;
аренда gets no раздел, so that argument does not carry over and the app stands on its own
ground: аренда is a subject area with rules of its own, and `building_passport/models.py`
already holds the паспорт, the план, the контур and seven dictionaries. `rooms` is not an
option — its `models.py` carries a comment explaining precisely why it is empty.

The import goes one way only: `leases` takes `Space`, `Party`, the период rule and the
`Document` an аренда hangs on the way `documents` and `rooms` take what they need, and
neither `building_passport.models` nor `documents.models` reaches back. It stays one-way
when the screens arrive: the occupancy rule they read lives here, so they import from
`leases` rather than the other way round.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from building_passport.models import Space
from building_passport.period import refuse_a_period_that_ends_before_it_begins
from documents.models import Document

# `CommonModel` is the stamp of who wrote a row and when. It is imported rather than copied
# out a fourth time: it is abstract, so nothing about the table depends on which app the
# base is spelled out in.
from parties.models import CommonModel, Party


class Lease(CommonModel):
    """One арендатор, one помещение, a number of metres, a срок and a ставка.

    Flat: the аренда may hang on a договор and is not held up by one (ADR 0032). A договор
    is a piece of paper covering several помещения with one срок, and an аренда is always
    about one — so the арендатор, the арендодатель and the срок stay here, and an аренда
    with no договор is a whole record rather than half of one.

    A помещение carries as many аренды as it has арендаторы sitting in it, and their
    периоды overlap freely: a часть is a number of metres and not a piece of the building,
    so it has no boundary to collide with another one.

    There is no `org` column: who sees the помещение sees its аренды, and the isolation of
    the platform's clients is decided once, on the помещение (ADR 0018). A second place
    deciding whose data to show is a way for the two to drift apart.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    #: The аренда goes with the помещение it is about: a помещение that is gone is not let
    #: to anybody, and a row pointing at nothing answers no question.
    space = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="leases", verbose_name="помещение"
    )
    #: A юрлицо as readily as a физлицо — an ИП in the стрит-ритейл is not made to register
    #: a fictitious ТОО. `PROTECT` rather than a cascade: a Сторона is entered once for the
    #: whole system, and deleting one must not quietly take the аренды with it.
    tenant = models.ForeignKey(
        Party, on_delete=models.PROTECT, related_name="leases", verbose_name="арендатор"
    )
    #: The Сторона in whose name the помещение is let, and not necessarily the собственник:
    #: a УК letting under доверительное управление lets in its own name, which is how all
    #: five БЦ actually stand. Optional, because the УК's table does not always say.
    landlord = models.ForeignKey(
        Party,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="leases_let",
        verbose_name="арендодатель",
    )
    #: A term of the agreement, not a measurement: it includes a share of the МОП by a
    #: coefficient, so the аренды of one помещение may add up to more than its площадь. It
    #: is never written into `Space.area_m2` — two арендаторы would give one помещение two
    #: "real" площади.
    area_m2 = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="арендуемая площадь, м²"
    )
    #: За м² в месяц, so that two аренды of different size compare without arithmetic. A
    #: term of the agreement and not a provodka: начисления, оплаты and задолженность live
    #: in the accounting system, and a second truth about money would part from the first
    #: by the first payment.
    rate = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="ставка за м² в месяц"
    )
    #: Бумага, на которой аренда висит, — документ вида «Договор» с условиями сбоку
    #: (ADR 0030). Необязательная: в выгрузке УК колонки с номером договора нет вовсе, и
    #: требовать бумагу значило бы выдумать тридцать шесть неподписанных (ADR 0032).
    #: Свободный «номер договора» ушёл вместе с появлением связи — рядом с ней он стал бы
    #: второй правдой о том, к какой бумаге аренда относится.
    #:
    #: `SET_NULL`, а не каскад: удаление одного скана унесло бы записи о том, кто и по какой
    #: ставке сидел в помещении, — историю, которой в бумаге нет и которую взять больше
    #: неоткуда (ADR 0034). Аренда после этого стоит ровно в том состоянии, которое
    #: ADR 0032 объявил верным, а пробел называет полка помещений.
    contract = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leases",
        verbose_name="договор",
    )
    valid_from = models.DateField(verbose_name="действует с")
    #: An empty end reads «по сей день» — the same reading the поэтажный план already gives
    #: (ADR 0004). A досрочный выезд is recorded by moving it to the actual day; a
    #: продление на новый срок is a new аренда, so that «по какой ставке сдавалось в марте»
    #: keeps its answer.
    valid_to = models.DateField(blank=True, null=True, verbose_name="действует по")

    class Meta:
        # Newest first: what is in force today is asked about far more often than what was
        # in force in 2019. The second key is not decoration — two аренды of one помещение
        # starting on the same day are the ordinary case here, and without it the order
        # would be undefined, that is, decided by the table from request to request.
        ordering = ("-valid_from", "-created_at")
        verbose_name = "аренда"
        verbose_name_plural = "аренды"

    def __str__(self):
        return f"{self.tenant} — {self.space}"

    def clean(self):
        """The reason for a refusal is named on the form, not thrown as a 500 on save."""
        super().clean()
        refuse_a_period_that_ends_before_it_begins(self.valid_from, self.valid_to)
        self._refuse_a_contract_this_lease_cannot_hang_on()

    def save(self, *args, **kwargs):
        """The refusals sit on the model, so a script gets them in the same words as the form.

        Four things are checked. A период that ends before it begins is checked by the rule
        the план already rejects by — one refusal in one wording — and the other three are
        about the договор an аренда hangs on, each stated beside itself below.

        Everything that is *not* checked is a decision rather than an omission:

        - **пересечение периодов** is not checked at all: overlap is the normal case
          (ADR 0017), and the same арендатор twice on one помещение is how taking another
          20 м² in the middle of a срок is expressed;
        - **the sum of арендуемые площади against the площадь of the помещение** is not
          checked: the share of the МОП is inside the арендуемая, so the check would refuse
          correct data;
        - **арендопригодность of the помещение** is not checked: the банкомат in the лобби
          is a real аренда, and a венткамера let by mistake surfaces as a находка on the
          полка rather than as a refusal at the moment of entry;
        - **that the срок of the аренда lies inside the срок of its договор** is not checked
          and must not be: a договор on автопролонгация outlives its stated end (ADR 0031),
          and a tenant leaving one помещение of four ends early. Both directions are correct
          data, and a check would refuse them both (ADR 0032).
        """
        refuse_a_period_that_ends_before_it_begins(self.valid_from, self.valid_to)
        self._refuse_a_contract_this_lease_cannot_hang_on()
        super().save(*args, **kwargs)

    def _refuse_a_contract_this_lease_cannot_hang_on(self):
        """Три отказа вокруг необязательной связи — и все три о договоре, на котором висят.

        Отсутствие договора не проверяется ничем: аренда без бумаги — верная запись, а не
        половина (ADR 0032), и пробел называет полка помещений числом на строке счёта.

        Условия спрашиваются здесь и раздаются отказам, а не спрашиваются каждым: порядок
        двух последних несущий — контрагента сличает тот, кто уже знает, что условия есть,
        потому что документ без них отвергнут отказом перед ним. Общая строка делает эту
        опору видимой: отказ, получающий условия на руки, не может оказаться первым.

        Ни одно из трёх на поле не встаёт, в отличие от отказа периоду, называющего «по»:
        поля «договор» на форме аренды нет и не будет — прицепляют аренду на экране договора,
        — а отказ, назвавший поле, которого форма не знает, роняет карточку пятисоткой вместо
        того, чтобы сказать, что не так. Карточка держит место под такой отказ с того дня,
        как форма заведена.
        """
        if self.contract_id is None:
            return
        terms = self.contract.attached_terms()
        self._refuse_a_contract_of_another_organisation()
        self._refuse_a_contract_that_is_not_about_letting_rooms(terms)
        self._refuse_a_tenant_who_did_not_sign_it(terms)

    def _refuse_a_contract_of_another_organisation(self):
        """Договор ведёт та же организация, чьё помещение (ADR 0018).

        Своей `org` у аренды нет, и второго ответа на «чья аренда» быть не должно: кто видит
        помещение, видит его аренды, а договор приносит свою организацию с собой (ADR 0006).
        Разойдись они — и аренду читал бы один клиент платформы, а её бумагу другой.
        """
        if self.contract.org_id == self.space.org_id:
            return
        raise ValidationError(
            f"Договор ведёт другая организация — «{self.contract.org.name}», "
            f"а помещение принадлежит «{self.space.org.name}»."
        )

    def _refuse_a_contract_that_is_not_about_letting_rooms(self, terms):
        """Вид договора — «Аренда помещений», и никакой другой.

        Аренда под поставкой ТМЦ — это опечатка выпадающего списка, и поймать её можно
        только здесь: прочитанная потом, она читается уверенно и неверно. Скан, которому
        вида ещё не проставили, отвергается тем же отказом и по той же причине — «Аренда
        помещений» о нём не сказано (ADR 0035): на полке договоров пустой вид обычен, а
        аренда вешается на бумагу, про которую уже известно, что она за бумага.

        Сам вопрос задан не здесь, а на условиях: тем же `about_letting_rooms` экран договора
        решает, стоять ли на нём блоку аренд, и два написания одного условия разошлись бы
        молча — блок обещал бы аренды там, где этот отказ их не пускает.

        Документ, у которого условий нет вовсе, — не договор, и отвергается он здесь же:
        отказ, стоящий следом, сличает контрагента и на пустоте сломался бы.
        """
        if terms is None:
            raise ValidationError(
                f"«{self.contract.title}» — не договор, а "
                f"{self.contract.get_kind_display().lower()}: "
                "аренда висит только на договоре вида «Аренда помещений»."
            )
        if terms.about_letting_rooms():
            return
        named = terms.get_kind_display() if terms.kind else "вид не заведён"
        raise ValidationError(
            "Аренда висит только на договоре вида «Аренда помещений», "
            f"а у «{self.contract.title}» — {named}."
        )

    def _refuse_a_tenant_who_did_not_sign_it(self, terms):
        """Арендатор аренды и контрагент договора — одна Сторона (ADR 0032).

        Расхождение здесь — это два ответа на «кто сидит по этой бумаге», и разъехавшиеся
        строки потом мирят руками. Незаведённый контрагент отвергается тем же отказом:
        пустота — не «любой», сойтись с арендатором ей пока нечем.

        Спрашивается ключ, а не Сторона: сравнение объектов стоило бы запроса на каждую
        сторону, а ключ уже лежит в обеих строках. Условия приходят на руки заполненными
        хотя бы видом: документ без них отвергнут отказом перед этим.
        """
        if terms.counterparty_id == self.tenant_id:
            return
        if terms.counterparty_id is None:
            raise ValidationError(
                f"У договора «{self.contract.title}» контрагент не заведён — "
                "заведите его, и это будет арендатор аренды."
            )
        raise ValidationError(
            f"Арендатор аренды — «{self.tenant.name}», а контрагент договора — "
            f"«{terms.counterparty.name}»: по одной бумаге сидит тот, кто её подписал."
        )
