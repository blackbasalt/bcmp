"""Аренда — кто занимает часть помещения, с какого дня по какой и по какой ставке.

An app of its own, with no `urls.py` and no menu item. ADR 0016 made a раздел a Django app
because the sidebar works out the open раздел from `request.resolver_match.app_name`;
аренда gets no раздел, so that argument does not carry over and the app stands on its own
ground: аренда is a subject area with rules of its own, and `building_passport/models.py`
already holds the паспорт, the план, the контур and seven dictionaries. `rooms` is not an
option — its `models.py` carries a comment explaining precisely why it is empty.

The import goes one way only: `leases` takes `Space`, `Party` and the период rule the way
`documents` and `rooms` take what they need, and nothing in `building_passport.models`
reaches back. It stays one-way when the screens arrive: the occupancy rule they read will
live here, so they will import from `leases` rather than the other way round.
"""

import uuid

from django.db import models

from building_passport.models import Space
from building_passport.period import refuse_a_period_that_ends_before_it_begins

# `CommonModel` is the stamp of who wrote a row and when. It is imported rather than copied
# out a fourth time: it is abstract, so nothing about the table depends on which app the
# base is spelled out in.
from parties.models import CommonModel, Party


class Lease(CommonModel):
    """One арендатор, one помещение, a number of metres, a срок and a ставка.

    Flat: there is no договор above the аренды (ADR 0017). A договор is a piece of paper
    that may cover several помещения with one срок, and BCMP does not hold it — the номер
    договора is a free field here and the скан is attached as a документ.

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
    #: A free field: «по договору №17» is written down without BCMP pretending to hold the
    #: договор itself.
    contract_no = models.CharField(
        max_length=128, blank=True, null=True, verbose_name="номер договора"
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

    def save(self, *args, **kwargs):
        """The refusal sits on the model, so a script gets it in the same words as the form.

        A период that ends before it begins is the one thing checked, and it is checked by
        the rule the план already rejects by — one refusal in one wording. Everything that
        is *not* checked is a decision rather than an omission:

        - **пересечение периодов** is not checked at all: overlap is the normal case
          (ADR 0017), and the same арендатор twice on one помещение is how taking another
          20 м² in the middle of a срок is expressed;
        - **the sum of арендуемые площади against the площадь of the помещение** is not
          checked: the share of the МОП is inside the арендуемая, so the check would refuse
          correct data;
        - **арендопригодность of the помещение** is not checked: the банкомат in the лобби
          is a real аренда, and a венткамера let by mistake surfaces as a находка on the
          полка rather than as a refusal at the moment of entry.
        """
        refuse_a_period_that_ends_before_it_begins(self.valid_from, self.valid_to)
        super().save(*args, **kwargs)
