"""Finding помещения among hundreds — what is asked of the полка, and how it narrows.

Eight conditions of one отбор, asked together and at one address: a text to find, a БЦ, a
вид, a назначение, an этаж, a range of площадь, and two statements about the record itself
— «площадь не заведена» and «вид не заведён». They travel in the address rather than in a
submission, so a narrowed полка can be reloaded, kept open in a tab and sent to a colleague
— and so that clearing the отбор is the address without it, which is the полка itself.

The search reaches название and код and no further. A word typed to find «каб101» must not
also answer with every помещение whose назначение happens to contain it; назначение has a
condition of its own, and вид has one, and they are asked when they are meant.

Every condition is checked before it is used, and one that checks out to nothing narrows
the полка to nothing rather than being dropped (ADR 0014). Dropped, the tampered address
naming another client's building would answer with the whole полка — the reader's own, so
nothing leaks, but the screen would state an отбор it did not perform.

There is deliberately no статус condition: `status` is filled on 0 of 583 помещения, and a
control that can only ever answer «ничего не нашлось» teaches the reader that the bar lies.
"""

import re

from django import forms
from django.db.models import Q

from building_passport import space_kind
from building_passport.models import Space
from dictionary.models import DictSpaceSubtype, DictSpaceType
from documents.building_choice import BuildingChoice

from .room_display import KIND_CHOICES


def matching(text):
    """Название or код containing the text, whatever the case of either.

    A regular expression over an escaped text, and not `icontains`: on SQLite `LIKE` folds
    case for ASCII alone, so «итп» would not find «ИТП» (ADR 0014). Whoever "tidies" this
    back into `icontains` breaks the search for Russian without breaking one ASCII test.

    A substring and not a whole word: «101» finds «каб101», «каб101вход» and «каб101вправо»
    together, and those three are one кабинет's parts — someone looking for the кабинет
    wants all of them.
    """
    wanted = re.escape(text)
    return Q(name__iregex=wanted) | Q(code__iregex=wanted)


class ShelfSearch(forms.Form):
    """The отбор as it was asked: what to find, where, of what вид and назначение, how big.

    One form for all eight conditions rather than one each. They are a single question —
    «санузлы Tokyo на третьем этаже» — and answered one at a time they would leave the
    screen deciding for itself how the eight combine.
    """

    q = forms.CharField(
        required=False,
        label="Поиск",
        # Said on the field, because the field cannot show it: an empty box gives no hint
        # that a код is looked for in it too, and whoever has a path id out of a план's
        # `unmatched_ids` would have nowhere to type it.
        widget=forms.TextInput(attrs={"placeholder": "Название или код"}),
    )
    building = BuildingChoice(
        queryset=Space.objects.none(),
        required=False,
        label="БЦ",
        empty_label="Любой БЦ",
        # One wording for both readings of an unreadable БЦ: a building that does not exist
        # and one belonging to another client answer the same, because telling them apart
        # would tell this reader what the other one has (ADR 0006).
        error_messages={"invalid_choice": "В адресе указан БЦ, которого нет в списке."},
    )
    kind = forms.ChoiceField(
        required=False,
        label="Вид",
        # The empty choice is the ordinary state of the condition and says so: «Любой вид»
        # is an answer, while «---------» is a gap in the list.
        choices=[("", "Любой вид"), *KIND_CHOICES],
        # An unreadable condition narrows the полка to nothing, and the screen has to say
        # why. Left to Django's own wording the reader is told «Выберите корректный
        # вариант» about a list they never touched: the value came from the address, not
        # from the select, and the select stands on «Любой вид» while it says so.
        error_messages={"invalid_choice": "В адресе указан вид, которого нет в списке."},
    )
    purpose = forms.ModelChoiceField(
        # Назначения of a помещение and of nothing else: the same dictionary also names
        # what a шахта and a прилегающая территория are for, and offering «Лифтовая шахта»
        # on a полка that holds no шахты is a condition answering «ничего не нашлось» by
        # construction.
        queryset=DictSpaceSubtype.objects.filter(type=DictSpaceType.ROOM).order_by("name"),
        required=False,
        label="Назначение",
        empty_label="Любое назначение",
        error_messages={
            "invalid_choice": "В адресе указано назначение, которого нет в списке."
        },
    )
    floor = forms.IntegerField(
        required=False,
        label="Этаж",
        # Across БЦ this means that floor of every building, which is the right reading for
        # a полка spanning the portfolio: «всё на третьем» is asked by someone planning a
        # round, and they walk the third floors of all five.
        error_messages={"invalid": "В адресе указан этаж, который не читается числом."},
    )
    area_from = forms.DecimalField(
        required=False,
        label="Площадь от",
        min_value=0,
        error_messages={"invalid": "В адресе указана площадь, которая не читается числом."},
    )
    area_to = forms.DecimalField(
        required=False,
        label="Площадь до",
        min_value=0,
        error_messages={"invalid": "В адресе указана площадь, которая не читается числом."},
    )
    no_area = forms.BooleanField(
        required=False,
        label="Площадь не заведена",
        # A condition of its own and not a hole in the range: «от» and «до» cannot find a
        # помещение whose площадь is not filled in, and silently that reads as «таких нет»
        # while the truth is «мы не знаем» (ADR 0015).
    )
    no_kind = forms.BooleanField(
        required=False,
        label="Вид не заведён",
        # Not a fourth value in the вид select: вид answers three things and only three,
        # and this is a statement about the record rather than about the building. That is
        # why the план may go on refusing a fourth colour while the полка offers this.
    )

    def __init__(self, data, *, user, **kwargs):
        # Always bound, even to an empty address: a полка nobody asked anything of is an
        # отбор with no conditions filled in, and a form left unbound there would need a
        # second way of saying "nothing was asked".
        super().__init__(data, **kwargs)
        # The BCs on offer are the reader's own (ADR 0001). Naming another client's
        # building on this screen would say what buildings they have.
        self.fields["building"].offer(Space.objects.buildings_visible_to(user))

    @property
    def asked(self):
        """Whether anything was asked of the полка at all.

        Read off what came in rather than off what came back: a полка can be empty and
        narrowed at the same time, and it is the отбор that decides whether an empty screen
        reads as «ничего не нашлось» or as «помещения не заведены».

        A condition that is present but unreadable counts as asked. It matched nothing, and
        that is what the reader is told — the alternative is a screen that silently ignores
        half of what was typed into it.
        """
        return any(self.data.get(name) for name in self.fields)

    def narrow(self, rooms):
        """The помещения that answer the отбор, out of the ones the reader may see.

        It narrows what it is handed and does not go looking for rows itself: whose
        помещения these are is decided by the chokepoint before this is called (ADR 0001),
        and a second place selecting rows would be a second place to one day disagree
        about whose they are.
        """
        if not self.is_valid():
            return rooms.none()
        asked = self.cleaned_data
        if text := asked["q"]:
            rooms = rooms.filter(matching(text))
        if building := asked["building"]:
            # A column comparison and not an ancestor walk: `building_id` is set on every
            # помещение, вложенное included, so «покажи всё по Tokyo» costs one condition.
            rooms = rooms.filter(building=building)
        if kind := asked["kind"]:
            rooms = rooms.filter(space_kind.being(kind))
        if purpose := asked["purpose"]:
            rooms = rooms.filter(subtype=purpose)
        # Checked against None and not for truth: the ground floor is 0, and «0 м² и
        # больше» is a question someone auditing the площади would ask on purpose.
        if (floor := asked["floor"]) is not None:
            rooms = rooms.filter(floor_number=floor)
        if (area_from := asked["area_from"]) is not None:
            rooms = rooms.filter(area_m2__gte=area_from)
        if (area_to := asked["area_to"]) is not None:
            rooms = rooms.filter(area_m2__lte=area_to)
        if asked["no_area"]:
            rooms = rooms.filter(area_m2__isnull=True)
        if asked["no_kind"]:
            rooms = rooms.filter(space_kind.unrecorded())
        return rooms
