"""Finding a Сторона among hundreds — what is asked of the полка, and how it narrows.

Five conditions of one отбор, asked together and at one address: a text to find, a сфера
деятельности, юрлицо or физлицо, «только арендаторы», and a БЦ. They travel in the address
rather than in a submission, so a narrowed полка can be reloaded, kept open in a tab and
sent to a colleague — and so that clearing the отбор is the address without it, which is the
полка itself.

Название and БИН are one box and not two. They are one question — «кто это» — asked with
whatever the reader has in front of them: a name heard on the phone, or a БИН copied out of
a счёт. Two boxes would make the reader decide which of them their string is before typing
it, and the answer is the same row either way.

The search reaches название and БИН and no further. A word typed to find a Сторона must not
also answer with every Сторона whose сфера деятельности happens to contain it; сфера has a
condition of its own on the way, and it is asked when it is meant.

Two of the five are not about the Сторона at all but about an аренда standing today —
«только арендаторы» and «БЦ» — and neither works out «действующая на день» here. Both ask
`leases.occupancy`, which the карточка помещения and the «Арендатор» column are read through
as well: a second place deciding who is in force today would be a second answer to one
question, and on the day they disagreed nobody would know which screen was lying. The день
they speak about is decided once by the screen and handed in (`PartyListView.today`) — two
readings of the clock a moment apart could straddle midnight, and one condition would then
answer about yesterday while the other answered about today.

There is deliberately no «поставщики» condition beside «только арендаторы». It would mean
«не арендатор», which the предметная область does not agree with: a Сторона can be both at
once — an арендатор who also services our lifts — and a бывший арендатор is neither. Whom we
pay is the question `PartyRole` will answer when it has rows and a reader.

Every condition is checked before it is used, and one that checks out to nothing narrows the
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
from building_passport.models import Space
from dictionary.models import DictLineOfBusiness
from documents.building_choice import BuildingChoice
from leases import occupancy

from .models import Party


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
    """The отбор as it was asked: what to find, of what сфера, юрлицо or физлицо, and where.

    One form for all five conditions rather than one each. They are a single question —
    «наши строители-арендаторы в Tokyo» — and answered one at a time they would leave the
    screen deciding for itself how the five combine.
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
    line_of_business = forms.ModelChoiceField(
        # The справочник whole, in its own alphabet: about twenty-five сферы, and every one
        # of them is something a Сторона may be — unlike the назначения on the полка
        # помещений, where the same dictionary also names what a шахта is for. A сфера
        # nobody has been given yet answers «ничего не нашлось», which is an honest answer
        # about the data rather than a condition that cannot work.
        queryset=DictLineOfBusiness.objects.order_by("name"),
        required=False,
        label="Сфера деятельности",
        empty_label="Любая сфера",
        error_messages={
            "invalid_choice": "В адресе указана сфера деятельности, которой нет в списке."
        },
    )
    kind = forms.ChoiceField(
        required=False,
        # «Юрлицо / физлицо» and not «Род»: the two values name the question between them,
        # and a word for the pair would be a word the словарь does not carry. The model's
        # own label for a юрлицо is «Организация», which on this screen is the column saying
        # whose карточка a row is — one word for two things the reader has to tell apart.
        label="Юрлицо / физлицо",
        # The empty choice is the ordinary state of the condition and says so: «Любая
        # Сторона» is an answer, while «---------» is a gap in the list.
        choices=[
            ("", "Любая Сторона"),
            (Party.Kind.COMPANY, "Юрлицо"),
            (Party.Kind.PERSON, "Физлицо"),
        ],
        # An unreadable condition narrows the полка to nothing, and the screen has to say
        # why. Left to Django's own wording the reader is told «Выберите корректный вариант»
        # about a list they never touched: the value came from the address, not from the
        # select, and the select stands on «Любая Сторона» while it says so.
        #
        # The wording names the two values rather than the pair, for the reason the label
        # does: the словарь carries no word for «юрлицо или физлицо», and a refusal is the
        # worst place to coin one — the reader meets the new word for the first time while
        # being told something went wrong.
        error_messages={"invalid_choice": "В адресе указано не юрлицо и не физлицо."},
    )
    tenants_only = forms.BooleanField(
        required=False,
        label="Только арендаторы",
        # One of the two conditions about today rather than about the Сторона, and the БЦ
        # below is the other: this one asks whether she rents anything of ours at all, that
        # one where. 637 of the 699 Стороны are поставщики, and without this «наши
        # арендаторы» is a question the полка cannot be asked. It carries no «поставщики»
        # opposite — see the module's own note about why the bar does not grow a second
        # handle for it.
    )
    building = BuildingChoice(
        queryset=Space.objects.none(),
        label="БЦ",
        required=False,
        empty_label="Любой БЦ",
        # One wording for both readings of an unreadable БЦ: a building that does not exist
        # and one belonging to another client answer the same, because telling them apart
        # would tell this reader what the other one has (ADR 0006).
        error_messages={"invalid_choice": "В адресе указан БЦ, которого нет в списке."},
    )

    def __init__(self, data, *, user, day, **kwargs):
        # Always bound, even to an empty address: a полка nobody asked anything of is an
        # отбор with no conditions filled in, and a form left unbound there would need a
        # second way of saying "nothing was asked".
        super().__init__(data, **kwargs)
        # The день the отбор speaks about, handed in and not taken from the clock here: the
        # screen decides once what «сегодня» is, and says why (`PartyListView.today`).
        self.day = day
        # The BCs on offer are the reader's own (ADR 0001). Naming another client's building
        # on this screen would say what buildings they have.
        self.fields["building"].offer(Space.objects.buildings_visible_to(user))

    def answering(self, records):
        """The учётные карточки that answer the отбор, out of the ones the reader may see.

        Which карточки reach here at all — whose they are — is decided by the chokepoint
        before `narrow` is called (ADR 0020); the five conditions can only take rows away
        from that answer.
        """
        asked = self.cleaned_data
        if text := asked["q"]:
            records = records.filter(matching(text))
        if line_of_business := asked["line_of_business"]:
            # On the Сторона and not on the карточка: what a Сторона does is a public fact
            # with one version, and 637 private opinions about it would diverge for nothing
            # (ADR 0020).
            records = records.filter(party__line_of_business=line_of_business)
        if kind := asked["kind"]:
            records = records.filter(party__kind=kind)
        if asked["tenants_only"]:
            # What «действующая сегодня» means is asked of `leases`, which the карточка
            # помещения and the «Арендатор» column are read through as well.
            records = records.filter(occupancy.renting_on(self.day))
        if building := asked["building"]:
            # The БЦ answers through an аренда standing today, which is what ties a Сторона
            # to a building at all: a поставщик falls out of this condition entirely, and
            # that is the honest answer rather than a gap.
            records = records.filter(occupancy.renting_on(self.day, building))
        return records
