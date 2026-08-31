"""Форма заведения аренды — то, что спрашивают на карточке помещения, и то, чего не спрашивают.

The form stands in the аренда block on the карточка помещения and is submitted to the
карточка's own address: заведение happens where the помещение is already open in front of
the reader, and a refusal has the карточка to come back onto — the rule the плана upload and
the близнец already follow (ADR 0005). No address is added by this stage.

**Обязательны арендатор и дата начала, и больше ничего.** Every other field is left empty on
purpose rather than by omission:

- **арендодатель** — so that one and the same company is not chosen 324 times;
- **арендуемая площадь** — so that «весь кабинет, метраж в бумаге не указан» is recordable.
  An empty площадь means «не заведено» and never «всё помещение»: one empty field must not
  carry two opposite meanings, and the карточка prints a dash for it and counts it nowhere;
- **ставка** — so that an аренда whose бумага is lost still reaches the system;
- **номер договора** — a free field, and BCMP holds no договор to fill it from.

The помещение is not a field: it is the карточка the form stands on, and the right to write
is checked on that помещение. A field would put a second answer to «куда» beside the address.

Checks of its own the form has none. The период is verified by the аренда itself, so the
admin, this form and any script get the same refusal in the same words — and what is
deliberately *not* checked (пересечение периодов, the sum of площади, арендопригодность of
the помещение) is stated on the model, where whoever comes looking for the missing check
will read it.
"""

from django import forms

from parties.models import Party

from .models import Lease
from .party_choice import PartyChoice, found

#: The names a поиск Стороны travels under in the address. Nothing else in an address opens
#: a filled-in form, and this is the list that says so.
SEARCHES = ("tenant_q", "landlord_q")


def carried_back(address) -> dict:
    """What an address puts back into the form — and nothing at all unless it asks a поиск.

    The поиск redraws the whole карточка and sends the form along with it, so what had
    already been typed has to come back: looking up the арендатор must not cost the срок and
    the ставка entered before it.

    An address that asks no поиск fills in nothing, and that is the point of the gate:
    `…/card/?valid_from=2020-01-01` would otherwise open the карточка with a дата начала
    nobody typed, and a pre-filled date is accepted without a glance — the very thing the
    плана upload refuses to do (ADR 0004). A form is filled in by whoever is entering the
    аренда, not by whoever sent them the link.
    """
    if not any(address.get(name) for name in SEARCHES):
        return {}
    return address.dict()


class LeaseForm(forms.ModelForm):
    """Аренда as it is entered: a Сторона found by поиск, a срок, and three optional terms."""

    #: The Стороны are searched for, not scrolled to: the реестр holds 699 of them, mostly
    #: поставщики. What may be chosen is the whole реестр and what is offered is what the
    #: поиск found — `PartyChoice` states why the two differ.
    #: The queryset is the whole реестр, because that is what a submitted key is checked
    #: against; what stands on the list is set by `offer` from the поиск.
    tenant = PartyChoice(queryset=Party.objects.all(), label="Арендатор")
    landlord = PartyChoice(queryset=Party.objects.all(), required=False, label="Арендодатель")
    #: The поиск itself, standing in the form rather than beside it: it travels in the
    #: address on a GET and back in the submission on a POST, so a refusal redraws the same
    #: list the Сторона was picked from and does not cost the reader the choice they made.
    tenant_q = forms.CharField(required=False, label="Найти арендатора")
    landlord_q = forms.CharField(required=False, label="Найти арендодателя")

    class Meta:
        model = Lease
        fields = ("tenant", "landlord", "area_m2", "rate", "contract_no", "valid_from", "valid_to")
        labels = {
            # «Арендуемая площадь» and not «Площадь»: a term of an agreement is not a
            # measurement of the building, and the карточка prints both a few lines apart.
            "area_m2": "Арендуемая площадь, м²",
            "rate": "Ставка за м² в месяц",
            "contract_no": "Номер договора",
            "valid_from": "Действует с",
            "valid_to": "Действует по",
        }

    def __init__(self, data=None, *, space, already_typed=None, **kwargs):
        """The помещение comes from the карточка the form stands on, the rest from the address.

        `already_typed` is what stood in the fields when the поиск was sent: the поиск redraws
        the whole карточка, and without it a reader who filled in the срок and the ставка
        before looking up the арендатор would get them back empty. It is put in as initial
        rather than bound as data — nothing was submitted, and a form that answered
        «обязательное поле» to a поиск would refuse a question nobody asked.
        """
        super().__init__(data, initial=already_typed, **kwargs)
        self.instance.space = space
        # The реестр Сторон is system-wide: the isolation of the platform's clients stands
        # on the помещение and is decided before this form is reached (ADR 0018).
        asked = self.data if self.is_bound else self.initial
        for field, query in (("tenant", "tenant_q"), ("landlord", "landlord_q")):
            self.fields[field].offer(found(asked.get(query)), chosen=asked.get(field))
