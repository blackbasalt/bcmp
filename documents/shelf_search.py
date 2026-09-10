"""Finding one документ on a shelf of hundreds — what is asked of it, and how it narrows.

Three conditions of one отбор, asked together and at one address: a text to find, a вид
документа and a БЦ. They travel in the address rather than in a submission, so a narrowed
shelf can be reloaded, kept open in a tab and sent to a colleague — and so that clearing
the отбор is the address without it, which is the shelf itself.

The search is over название and номер only. Nothing in BCMP reads the inside of a документ:
the близнец exists for the ИИ-управляющий and is not indexed here (ADR 0007), and a search
that also matched the вид or the issuing Сторона would answer «нашлось сорок» to a text
typed to find one paper.

Every condition is checked before it is used, and one that checks out to nothing narrows
the shelf to nothing rather than being dropped (ADR 0014) — that is `bcmp.shelf`'s doing and
not this shelf's, and so is the reading of whether anything was asked at all. What this
screen makes of that reading is its own: it is what tells «ничего не нашлось» from «ничего не
загружено».
"""

import re

from django import forms
from django.db.models import Q

from bcmp import shelf
from building_passport.models import Space

from .building_choice import BuildingChoice
from .models import Document, DocumentLink


def matching(text):
    """Название or номер containing the text, whatever the case of either.

    A regular expression over an escaped text, and not `icontains`: on SQLite `LIKE` folds
    case for ASCII alone, so «акт» would not find «Акт» (ADR 0014). Whoever "tidies" this
    back into `icontains` breaks the search for Russian without breaking one ASCII test.
    """
    wanted = re.escape(text)
    return Q(title__iregex=wanted) | Q(doc_no__iregex=wanted)


class ShelfSearch(shelf.Search):
    """The отбор as it was asked: what to find, of what вид, on what БЦ.

    One form for all three conditions rather than one each. They are a single question —
    «покажи сертификаты по Manhattan, где встречается „насос“» — and answered one at a time
    they would leave the screen deciding for itself how the three combine.
    """

    q = forms.CharField(
        required=False,
        label="Поиск",
        # Said on the field, because the field cannot show it: an empty box gives no hint
        # that a номер is looked for in it too, and whoever has the номер to hand would
        # type it into the search of a system that never told them it was searched.
        widget=forms.TextInput(attrs={"placeholder": "Название или номер"}),
    )
    kind = forms.ChoiceField(
        required=False,
        label="Вид документа",
        # The empty choice is the ordinary state of the condition and says so: «Любой вид»
        # is an answer, while «---------» is a gap in the list.
        choices=[("", "Любой вид"), *Document.Kind.choices],
        # An unreadable condition narrows the shelf to nothing, and the screen has to say
        # why. Left to Django's own wording the reader is told «Выберите корректный
        # вариант» about a list they never touched: the value came from the address, not
        # from the select, and the select stands on «Любой вид» while it says so.
        error_messages={"invalid_choice": "В адресе указан вид, которого нет в списке."},
    )
    building = BuildingChoice(
        queryset=Space.objects.none(),
        required=False,
        label="БЦ",
        empty_label="Любой БЦ",
        # The same for a БЦ, and one wording for both readings of it: a building that does
        # not exist and one that belongs to another client are the same answer here,
        # because telling them apart would tell this reader what the other one has
        # (ADR 0006).
        error_messages={"invalid_choice": "В адресе указан БЦ, которого нет в списке."},
    )

    def __init__(self, data, *, user, **kwargs):
        # Always bound, even to an empty address: a shelf nobody asked anything of is an
        # отбор with no conditions filled in, and a form left unbound there would need a
        # second way of saying "nothing was asked".
        super().__init__(data, **kwargs)
        # The BCs on offer are the reader's own (ADR 0001) — a narrower list than the
        # upload's, which offers only those they may write to. Naming another client's
        # building on this screen would say what buildings they have.
        self.fields["building"].offer(Space.objects.buildings_visible_to(user))

    def answering(self, documents):
        """The documents that answer the отбор, out of the ones the reader may see.

        Which документы reach here at all — whose they are — is decided by the chokepoint
        before `narrow` is called (ADR 0006); the three conditions can only take rows away
        from that answer.
        """
        if text := self.cleaned_data["q"]:
            documents = documents.filter(matching(text))
        if kind := self.cleaned_data["kind"]:
            documents = documents.filter(kind=kind)
        if building := self.cleaned_data["building"]:
            # The привязка holds a type and an identifier, and both are asked of the same
            # link: a документ attached to a зона of that identifier is not attached to the
            # building. One привязка per building per документ is guaranteed by the unique
            # constraint, so a документ on two buildings' папки is still one row on each.
            documents = documents.filter(
                links__entity_type=DocumentLink.EntityType.SPACE,
                links__entity_id=building.pk,
            )
        return documents
