from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import OuterRef, Subquery
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import ListView

from building_passport.models import Space
from dictionary.models import DictSpaceType
from leases.occupancy import free_of_each_room, tenants_of_each_room
from parties.models import Org

from .room_display import rooms_shown
from .shelf_search import ShelfSearch


class RoomListView(LoginRequiredMixin, ListView):
    """The «Помещения» section — every помещение an organisation has, on one screen.

    A finder, not a form. The questions a сотрудник УК arrives with cross buildings and
    cross floors — «где каб101», «покажи все санузлы», «какие офисы больше 100 м²
    свободны» — and walking down Бизнес-центры → БЦ → этаж → дерево answers only "what is
    on this floor". Nothing is created, edited or deleted here: a row leads to the экран
    этажа, which answers «где» once the полка has answered «которое».

    It also counts what it has not got. «Показано 47 из 583 помещений · площадь не заведена
    у 5» — the same device as «нанесено 47 из 82» beneath a план, applied to a полка that
    is full rather than empty: the gap is not missing rows but missing fields in the rows
    that are there.
    """

    template_name = "rooms/room_list.html"
    context_object_name = "rooms"

    def get_queryset(self):
        """The data is taken through the spaces chokepoint (ADR 0001) and narrowed after
        it, never instead of it.

        The order of the two is the whole point: whose помещения these are is decided first
        and by one place, and what the reader asked of them can only take rows away from
        that answer.
        """
        return self.search.narrow(self.shelf)

    @cached_property
    def shelf(self):
        """The whole полка: every помещение the reader may see, before any отбор.

        `type=room` and nothing else — шахты, лестничные клетки, кровли, площадки and
        машиноместа are not помещения on this screen. Every помещение is a row, the 218
        that sit inside another one included: the полка is a finder, and a кабина inside a
        уборная is looked for on it exactly as a кабинет is.

        The order is БЦ → этаж → код, so that reading top to bottom walks the portfolio the
        way one would walk it. The БЦ is ordered by the name it is shown under, with the
        код standing in where a building has no name — the same rule the list of БЦ in the
        отбор is ordered by, so the table and the control agree about what comes first.
        """
        return (
            Space.objects.visible_to(self.request.user)
            .filter(type=DictSpaceType.ROOM)
            # Everything a row names travels in the same query as the row: the БЦ, the
            # помещение it lies inside, its назначение and its организация. Asked row by
            # row this would be four queries per помещение over hundreds of them.
            .select_related("org__party", "building", "parent", "subtype")
            # The этаж each row leads to, in the same query as the rows — the same device
            # as `has_plan` on the floor switcher and `has_twin` on the полка документов.
            # Asked row by row this would be a query per помещение over hundreds of them.
            .annotate(leads_to_floor=Subquery(self.floor_of_the_row.values("pk")[:1]))
            # Кто сидит в каждом помещении сегодня, in the same query again. Both what
            # «действующая» means and what the column may say are asked of `leases`: the
            # карточка помещения answers the same question, and two places working out who
            # is in force today would one day disagree about it.
            .annotate(**tenants_of_each_room(self.today))
            # And whether each помещение stands free today, in that same query — the very
            # condition the «свободно» отбор narrows by, hung on the row as a column so that
            # the figure under the table and the отбор its link sets are one answer.
            .annotate(**free_of_each_room(self.today))
            .order_by("building__name", "building__code", "floor_number", "code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The rows are fixed here rather than left as a queryset: the count beneath the
        # table, the count of the gaps in it and the address each row leads to are all
        # worked out over exactly the rows that will be printed. A queryset asked again in
        # the markup would be a second reading of the database and a second chance to
        # disagree with the number underneath it.
        rooms = context["rooms"]
        # Counted rather than asked of the database again: `len` fills the queryset's cache,
        # which the table then reads. The count beneath the table and the rows within it are
        # then the same rows by construction, and not two readings that must agree.
        shown = len(rooms)
        # «Показано 47 из 583 помещений»: everything after «Показано» describes what is on
        # screen, and only «из 583» refers to the whole полка — a narrowed screen still has
        # to say the size of what was narrowed.
        # How big the whole полка is, asked once and used three times: it is the second
        # figure of the count line, and it is also what tells an empty полка from one an
        # отбор emptied. Which of the two the screen is looking at cannot be read off the
        # отбор — a полка with no помещения at all can be questioned just as one full of
        # them can — so it is read off the полка itself.
        whole = self.shelf.count()
        context["whole"] = whole
        context["shown"] = rooms_shown(shown, whole)
        # The second figure of the same line, and the reason ADR 0015 gives for it: the
        # площадь range cannot find a помещение whose площадь is not filled in, and silently
        # that reads as «таких нет» while the truth is «мы не знаем». It counts only what is
        # on screen — a figure about the whole полка under a narrowed table would contradict
        # the table above it.
        context["without_area"] = sum(1 for room in rooms if room.area_m2 is None)
        # And it is a link: the gap in the data is found from the same полка as everything
        # else, one click away, with the rest of the отбор left standing.
        context["without_area_url"] = self.also_without_area
        # «Свободно N»: the answer to «что стоит пустым», counted over exactly the rows that
        # are printed — a figure about the whole полка under a narrowed table would
        # contradict the table above it. Named in помещениях because that is what it counts:
        # there is no итог in metres beside it, since 107 арендопригодных помещений stand
        # inside another one and metres would count them twice (ADR 0019).
        context["free_rooms"] = sum(1 for room in rooms if room.free_here)
        # A link, like the figure beside it: the отбор it sets leads to the work rather than
        # reporting it, and the rest of the question is kept.
        context["free_rooms_url"] = self.also_free
        # The отбор, back on the screen it was typed into: it says both what was asked and
        # whether anything was, and the markup asks it for both. Handed over as one thing
        # rather than unpacked here, because the two answers must not drift — an empty
        # screen reads as «ничего не нашлось» or «помещения не заведены» by exactly the
        # question the bar above it is showing.
        context["search"] = self.search
        # The организация is named for whoever handles more than one client: for them the
        # полка is shared, and "whose помещение is this" is a question they ask of every
        # row. Asked about the reader and not about what is shown — the same condition the
        # полка документов uses, and for the same reason.
        context["organisation_named"] = Org.objects.handled_by(self.request.user).count() > 1
        return context

    @cached_property
    def today(self):
        """The день the screen speaks about, taken once for the whole request.

        The «Арендатор» column and the «свободно» condition are two readings of one
        «сегодня», and two calls to the clock a moment apart could straddle midnight —
        leaving a помещение counted as свободное in a row that names who sits in it.
        """
        return timezone.localdate()

    @cached_property
    def search(self):
        """What was asked of the полка — read once and used by both the rows and the bar."""
        return ShelfSearch(self.request.GET, user=self.request.user, day=self.today)

    @cached_property
    def floor_of_the_row(self):
        """The этаж a row leads to: the этаж of its БЦ bearing its номер этажа.

        A помещение names its floor by `floor_number`, and that is the one account of which
        этаж it is on: the «Этаж» column prints it, the отбор narrows by it, and the link
        follows it. Walking up `parent` instead would be a second account — a вложенное
        помещение would reach its этаж one way while the column named it another, and
        nothing would keep the two in step.

        Through the same chokepoint as the rows: an этаж of another client must not become a
        row's address. A помещение whose номер этажа matches no этаж leads nowhere, and the
        row stays plain text — a link opening the wrong этаж is worse than no link.
        """
        return (
            Space.objects.visible_to(self.request.user)
            .filter(
                type=DictSpaceType.FLOOR,
                building=OuterRef("building"),
                floor_number=OuterRef("floor_number"),
            )
        )

    @cached_property
    def also_without_area(self):
        """The same отбор with «площадь не заведена» ticked — the address, not a new screen.

        The rest of the question is kept: someone who narrowed the полка to Tokyo and then
        asks where the площадь is missing means "in Tokyo", and an address that dropped the
        БЦ would answer about the whole portfolio.
        """
        return self.also("no_area")

    @cached_property
    def also_free(self):
        """The same отбор with «свободно» ticked — the figure sets the condition and keeps
        the rest of the question.

        Someone who narrowed the полка to Tokyo and then asks what stands empty means "in
        Tokyo", exactly as they do about the помещения with no площадь.
        """
        return self.also("free")

    def also(self, condition):
        """This screen's address with one more condition ticked on it.

        The figures under the table are links, and each adds its own condition to the
        question already being asked rather than replacing it. Assigned and not `update`d: a
        `QueryDict` holds a list of values per name and its `update` extends that list, so
        the link on a полка already narrowed by this very condition would carry it twice, and
        every further click would add another copy.
        """
        asked = self.request.GET.copy()
        asked[condition] = "1"
        return f"{reverse('rooms:room_list')}?{asked.urlencode()}"
