"""Finding a Сторона among hundreds — what is asked of the полка, and how it narrows.

One condition for now: a text to find, looked for in the название and in the БИН/ИИН at
once. It travels in the address rather than in a submission, so a narrowed полка can be
reloaded, kept open in a tab and sent to a colleague — and so that clearing the отбор is the
address without it, which is the полка itself.

Название and БИН are one box and not two. They are one question — «кто это» — asked with
whatever the reader has in front of them: a name heard on the phone, or a БИН copied out of
a счёт. Two boxes would make the reader decide which of them their string is before typing
it, and the answer is the same row either way.

The search reaches название and БИН and no further. A word typed to find a Сторона must not
also answer with every Сторона whose сфера деятельности happens to contain it; сфера has a
condition of its own on the way, and it is asked when it is meant.

The condition is checked before it is used, and one that checks out to nothing narrows the
полка to nothing rather than being dropped (ADR 0014) — that is `bcmp.shelf`'s doing and not
this полка's, and so is the reading of whether anything was asked at all. Which of the two
empty screens this one shows is decided elsewhere and by the size of the un-narrowed полка
(`PartyListView`); the reading is asked here only for whether «Сбросить» has anything to
drop.
"""

import re

from django import forms
from django.db.models import Q

from bcmp import shelf


def matching(text):
    """Название or БИН containing the text, whatever the case of either.

    A regular expression over an escaped text, and not `icontains`: on SQLite `LIKE` folds
    case for ASCII alone, so «крепеж» would not find «КРЕПЕЖ» (ADR 0014). Whoever "tidies"
    this back into `icontains` breaks the search for Russian without breaking one ASCII test.

    A substring and not a whole word: the names come out of the УК's own выгрузка with their
    ОПФ, their quotes and their spelling, and nobody retypes «ТОО «Центр крепежных систем»»
    in full to find it. The same substring answers for the БИН, where the first digits are
    what a reader has when they are reading one off a счёт.

    `leases.party_choice.matching` asks the same two fields the same way and is deliberately
    a separate condition: that one picks one Сторона out of the whole реестр while an аренда
    is entered, and stays system-wide precisely so that an арендатор nobody has met yet is
    findable (ADR 0020); this one narrows a полка of учётные карточки, which is the reader's
    own. They are a condition on `Party` and a condition on `PartyRecord` — one query away
    from each other — and joining them would mean a prefix passed in from the caller, which
    is a knob for a need neither of them has. Their fates differ too: whoever narrows the
    other one breaks заведение аренды without breaking this полка.
    """
    wanted = re.escape(text)
    return Q(party__name__iregex=wanted) | Q(party__bin_iin__iregex=wanted)


class ShelfSearch(shelf.Search):
    """The отбор as it was asked: what to find.

    A form for one condition, and a form rather than a bare string because the other
    conditions of this отбор — сфера деятельности, род, только арендаторы, БЦ — arrive at the
    same bar and are one question with this one. A polka answering them one at a time would
    be left deciding for itself how they combine.
    """

    q = forms.CharField(
        required=False,
        label="Поиск",
        # A text longer than the longest thing it could be looking for did not read: 255 is
        # the length of `Party.name`, and a БИН is twelve digits, so nothing beyond that is a
        # название or a БИН. It is refused rather than searched for — the address is public,
        # the search is a regular expression run per row on SQLite (ADR 0014), and a полка of
        # 637 rows should not scan itself against a kilobyte from a query string.
        max_length=255,
        # Said on the field, because the field cannot show it: an empty box gives no hint
        # that the БИН is looked for in it too, and whoever has one in front of them would
        # have nowhere to type it.
        widget=forms.TextInput(attrs={"placeholder": "Название или БИН/ИИН"}),
        # An unreadable condition narrows the полка to nothing, and the screen has to say
        # why. Left to Django's own wording the reader is told «Убедитесь, что это значение
        # содержит не более 255 символов» about a box they never typed into: the value came
        # from the address.
        error_messages={
            "max_length": "В адресе указан текст длиннее любого названия и БИН/ИИН."
        },
    )

    def answering(self, records):
        """The учётные карточки that answer the отбор, out of the ones the reader may see.

        Which карточки reach here at all — whose they are — is decided by the chokepoint
        before `narrow` is called (ADR 0020); the condition can only take rows away from that
        answer.
        """
        if text := self.cleaned_data["q"]:
            records = records.filter(matching(text))
        return records
