from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import ListView

from leases.occupancy import rooms_of_each_record

from .models import Org, PartyRecord
from .party_display import parties_shown
from .shelf_search import ShelfSearch


class PartyListView(LoginRequiredMixin, ListView):
    """The «Стороны» section — everything an organisation knows it deals with, on one screen.

    A finder, and the fourth раздел beside «Бизнес-центры», «Документы» and «Помещения»: the
    question «с кем мы имеем дело» is asked across the whole portfolio and gets an address of
    its own (ADR 0016). Nothing is created, edited or deleted here.

    The полка is a полка учётных карточек, not of Стороны: a Сторона is on it because this
    организация keeps a карточка on her, and not because she has an аренда or a роль. The
    rule that derives the полка from связи gives the УК an empty screen while 637 of those
    Стороны are its own поставщики — 0 rows in `PartyRole`, 35 аренды, 699 Сторон (ADR 0020).
    """

    template_name = "parties/party_list.html"
    context_object_name = "records"

    def get_queryset(self):
        """The data is taken through the карточки chokepoint (ADR 0020) and narrowed after
        it, never instead of it.

        The order of the two is the whole point: whose карточки these are is decided first
        and by one place, and what the reader asked of them can only take rows away from that
        answer.
        """
        return self.search.narrow(self.shelf)

    @cached_property
    def shelf(self):
        """The whole полка: every учётная карточка the reader may see, before any отбор.

        The Сторона a row is about, her сфера деятельности and the организация whose карточка
        it is all travel in the same query as the row — asked row by row that would be three
        queries per карточка over 637 of them.

        The order is the alphabet of the названия: the полка is read by eye, hunting for a
        Сторона on it, and the order in which the выгрузка happened to load 637 поставщиков
        helps nobody. The организация is the second key rather than decoration — a Сторона
        two of the reader's clients both know is two rows, and without it the table would
        decide their order from request to request.
        """
        return (
            PartyRecord.objects.visible_to(self.request.user)
            .select_related("party__line_of_business", "org__party")
            # Сколько помещений арендует каждая Сторона сегодня, in the same query as the
            # rows — the same device as `tenants_of_each_room` on the полка помещений. Both
            # what «действующая» means and what the column counts are asked of `leases`: the
            # карточка помещения answers the same question, and two places working out who
            # is in force today would one day disagree about it.
            .annotate(**rooms_of_each_record(self.today))
            .order_by("party__name", "org__party__name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The rows are fixed here rather than left as a queryset: the count beneath the table
        # is worked out over exactly the rows that will be printed. A queryset asked again in
        # the markup would be a second reading of the database and a second chance to
        # disagree with the number underneath it.
        records = context["records"]
        # Counted rather than asked of the database again: `len` fills the queryset's cache,
        # which the table then reads.
        shown = len(records)
        # How big the whole полка is, asked once and used twice: it is the second figure of
        # the count line, and it is also what tells an empty полка from one an отбор emptied.
        # Which of the two the screen is looking at cannot be read off the отбор — a полка
        # with no Стороны at all can be questioned just as one full of them can — so it is
        # read off the полка itself. The полка follows помещения here and not документы: a
        # reader whose организация has nothing loaded must not be sent to fix a question that
        # was never the problem.
        whole = self.shelf.count()
        context["whole"] = whole
        context["shown"] = parties_shown(shown, whole)
        # The отбор, back on the screen it was typed into: it says both what was asked and
        # whether anything was, and the markup asks it for both. Handed over as one thing
        # rather than unpacked here, because the two answers must not drift.
        context["search"] = self.search
        # The организация is named for whoever handles more than one client: for them the
        # полка is shared, and "whose карточка is this" is a question they ask of every row.
        # Asked about the reader and not about what is shown — the same condition the полки
        # документов and помещений use, and for the same reason: the column has to hold on
        # even when the second client has nothing loaded, which is exactly when whoever
        # handles two of them most needs to know whose полка they are looking at.
        context["organisation_named"] = Org.objects.handled_by(self.request.user).count() > 1
        return context

    @cached_property
    def today(self):
        """The день the screen speaks about, taken once for the whole request.

        One reading of «сегодня» for the whole полка: two calls to the clock a moment apart
        could straddle midnight, and two rows of one table would then be counted on two
        different days.
        """
        return timezone.localdate()

    @cached_property
    def search(self):
        """What was asked of the полка — read once and used by both the rows and the bar."""
        return ShelfSearch(self.request.GET)
