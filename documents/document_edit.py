"""Filling in a document's реквизиты — the other half of the bulk transfer.

A batch arrives with nothing but a name (ADR 0008): the вид is chosen once for the whole
folder, the название comes from the file name, and номер, дата выдачи, кем выдан, срок and
ревизия stay empty because whoever carries the archive across does not have them to hand.
This form is where they arrive later, one document at a time, from the document's own page.

Exactly those five fields, and not the вид or the название: those two were answered when
the file was stored, and a batch of a hundred filed under one вид is corrected by moving
the batch, not by editing a hundred pages. Nothing here is required — the point of the form
is that a document is enriched over time, and a form demanding all five at once would keep
a known номер out until a дата выдачи is found for it.

«Кем выдан» is the one of the five that is not typed but chosen, and what it is chosen from
is the Стороны this reader's учётные карточки name (ADR 0020). Which of them are on the list
at any moment is what the поиск found — by название and by БИН, the same поиск the форма
аренды is filled in by — and the поиск travels as a parameter on the документ's own address,
because the stage adds no address and отбор in the address is what the словарь says about
every other screen.
"""

from django import forms
from django.db.models import Q

# A date read back into `type="date"` is not this section's rule: the правка аренды reads
# one back the same way, and the widget stands where both of them reach it.
from building_passport.date_entered import DateEntered

# Сторону выбирают поиском в двух местах, и оба раза одинаково: заведение аренды
# написало это первым, и второе описание того же выбора разошлось бы с первым в тот день,
# когда одно из них научилось бы чему-то новому. Что в них различается — набор, из которого
# выбирают, — решает форма, а не поле: у аренды это весь реестр, здесь — свои карточки.
from leases.party_choice import PartyChoice, matching
from parties.models import Party, PartyRecord

from .models import Document

#: The name the поиск Стороны travels under in the address. Nothing else in an address opens
#: a filled-in form, and this is what says so.
SEARCH = "issuer_q"


def carried_back(address) -> dict:
    """What an address puts back into the form — and nothing at all unless it asks a поиск.

    The поиск redraws the form, so what had already been typed has to come back with it:
    looking up «кем выдан» must not cost the номер and the дата выдачи entered before it.

    An address that asks no поиск fills in nothing, and that is the point of the gate:
    `…/documents/<pk>/?doc_no=АКТ-12/2024` would otherwise open the form with a номер nobody
    typed, and a pre-filled field is saved without a glance — the very thing the загрузка
    плана refuses to do (ADR 0004).

    Второй такой же гейт стоит в `leases/lease_form.py`, и они порознь: там имён поиска два,
    здесь одно, и общий на двоих принимал бы список имён — ради чего, кроме самой общности,
    неизвестно. Довод же у них один, и переписан он будет тоже один раз: это решение ADR
    0004, а не решение формы.
    """
    if not address.get(SEARCH):
        return {}
    return address.dict()


def known_to(user, kept=None):
    """The Стороны the reader's учётные карточки name — plus the one already recorded.

    «Чьи это подрядчики» is answered by the учётная карточка and by nothing else (ADR 0020),
    so the set is taken through that полка's own chokepoint rather than assembled here: a
    second place deciding whose knowledge this is would be a second answer to one question.

    Читателя, а не организации документа. Тот, кто ведёт двух клиентов, знаком с Сторонами
    обоих, и «кем выдан» — это подрядчик, которого он знает; отобрать здесь по организации
    документа значило бы задать вопрос «чьё это знание» второй раз и по-своему, рядом с
    привратником, который уже на него ответил. Право писать в этот документ — вопрос
    отдельный, и он проверен до формы, на самом документе (ADR 0005).

    `kept` is the Сторона already standing on the документ, and she is in the set whatever
    the карточки say. 62 Стороны came in without anybody's карточка and some of them are
    written on papers already loaded; narrowing them away would erase «кем выдан» from the
    document with whoever came to fill in the номер — a сужение costing the one field nobody
    complained about.
    """
    known = Q(pk__in=PartyRecord.objects.visible_to(user).values("party_id"))
    if kept is not None:
        known |= Q(pk=kept)
    return Party.objects.filter(known)


def found_among(parties, text):
    """The Стороны a поиск turned up on this form — and none at all until something is asked.

    An empty поиск is not a поиск over everything, for the reason the форма аренды states:
    hundreds of rows are a scroll rather than a choice, which is what the поиск exists
    instead of.

    A condition of its own and not `leases.party_choice.found`: that one searches the реестр
    whole, and deliberately so — an арендатор nobody has met yet must stay findable while an
    аренда is entered. Passing it a set to search in would move that decision out to its
    callers, and the argument for it would no longer be written anywhere. The condition
    itself is shared, because «по названию и по БИН, свернув регистр» is one reading.
    """
    text = (text or "").strip()
    if not text:
        return parties.none()
    return parties.filter(matching(text)).order_by("name")


class DocumentParticularsForm(forms.ModelForm):
    """The реквизиты of one document. The document itself comes from the page, not a field."""

    #: Сторона ищется, а не пролистывается: in the реестр 699 of them, mostly поставщики, and
    #: narrowed to this reader's карточки it is still hundreds. What may be chosen is set by
    #: the queryset and what is offered by `offer` — `PartyChoice` states why the two differ.
    issuer_party = PartyChoice(
        queryset=Party.objects.none(),
        required=False,
        label="Кем выдан",
        # Одни слова на оба чтения непринятого ключа: такой Стороны нет вовсе или её нет на
        # полке этой организации. Различить их значило бы сказать читателю, что есть у
        # другого клиента (ADR 0006). Django сказал бы «Выберите корректный вариант» о
        # списке, которого читатель не касался: ключ пришёл из отправки, а не из выбора.
        error_messages={
            "invalid_choice": "Такой Стороны среди ваших нет — «кем выдан» выбирают из раздела «Стороны»."
        },
    )
    #: Сам поиск — в форме, а не рядом с ней: он едет параметром в адресе на GET и обратно в
    #: отправке на POST, так что отказ перерисовывает тот же список, из которого Сторону
    #: выбрали, и выбора читателю не стоит.
    issuer_q = forms.CharField(required=False, label="Найти Сторону")

    class Meta:
        model = Document
        fields = ("doc_no", "issued_at", "issuer_party", "valid_until", "revision")
        labels = {
            "doc_no": "Номер",
            "issued_at": "Дата выдачи",
            # A field without behaviour: the date is stored and shown, and threatens
            # nothing — there is no register of deadlines and no screen counting what is
            # overdue. Naming it «Действителен до» would promise exactly such a watch.
            "valid_until": "Срок действия",
            "revision": "Ревизия",
        }
        widgets = {"issued_at": DateEntered(), "valid_until": DateEntered()}

    def __init__(self, data=None, *, user, already_typed=None, **kwargs):
        """Кто читает — из запроса, что уже набрано — из адреса, остальное — из документа.

        `already_typed` is what stood in the fields when the поиск was sent. It is put in as
        initial rather than bound as data: nothing was submitted, and a form that answered
        with refusals to a поиск would refuse a question nobody asked.
        """
        super().__init__(data, initial=already_typed, **kwargs)
        issuer = self.fields["issuer_party"]
        issuer.queryset = known_to(user, kept=self.instance.issuer_party_id)
        # On a submission the поиск and the choice come back in the submission itself; on a
        # request they come from the address, or — the ordinary case — from the документ.
        asked = self.data if self.is_bound else self.initial
        standing = list(found_among(issuer.queryset, asked.get(SEARCH)))
        #: Нашлось ли что-нибудь — вопрос о поиске, а не о длине списка: уже проставленная
        #: Сторона стоит в списке и тогда, когда поиск не нашёл никого, и «не нашлось» должно
        #: сказаться и над ней. Иначе набравший БИН и не нашедший ничего решит, что спросил
        #: не так, хотя Стороны на его полке просто нет.
        #:
        #: Сосчитано здесь, а на форме аренды — в разметке, и порознь они не по недосмотру:
        #: там два поиска на одной форме, и ответ на каждый пришлось бы держать по имени
        #: поля, здесь поиск один и ответ у него один.
        self.nothing_found = bool((asked.get(SEARCH) or "").strip()) and not standing
        issuer.offer(standing, chosen=asked.get("issuer_party"))
