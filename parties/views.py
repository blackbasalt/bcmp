from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView

from documents.models import Document
from leases.occupancy import rooms_of_each_record

from . import occasions
from .models import Org, PartyRecord
from .party_display import parties_shown
from .party_page import (
    contacts_of,
    documents_issued_by,
    leases_of,
    occasions_said,
    particulars,
    payment_details_of,
)
from .shelf_search import ShelfSearch


def naming_the_organisation(user) -> bool:
    """Нужно ли называть организацию на экранах раздела — вопрос о читателе, а не о данных.

    Ведущий одного клиента получил бы колонку и строку, повторяющие на каждом экране то, что
    он и так знает; ведущий двух спрашивает «чья это карточка» о каждой строке — и спрашивает
    тем чаще, чем меньше у второго клиента загружено.

    Один раз на весь раздел, потому что читают это оба его экрана: полка — колонкой, экран
    Стороны — строкой шапки, — и два места, считающих, сколько у читателя клиентов, были бы
    двумя ответами на один вопрос. Сами организации спрашиваются у `Org.objects.handled_by`,
    где и живёт довод о том, чьи они.
    """
    return Org.objects.handled_by(user).count() > 1


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
        # The ближайший повод of every row, worked out once for the whole полка and hung on
        # the rows the table is about to print. One reading for the screen: the same rows the
        # count line is worked out over, so what the column says and what is on screen cannot
        # differ. Not an annotation like «Арендует» beside it — «второе воскресенье августа»
        # is resolved in python and not by a query (ADR 0027) — but the same promise: two
        # queries for the whole полка and none per row.
        nearest = occasions.nearest_for_each_record(records, self.today)
        for record in records:
            record.nearest_occasion = nearest.get(record.pk)
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
        # The reason is `naming_the_organisation`'s, above, and it is asked there rather than
        # here because the экран Стороны asks the very same question of the very same reader.
        context["organisation_named"] = naming_the_organisation(self.request.user)
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
        """What was asked of the полка — read once and used by both the rows and the bar.

        The reader and the день are handed in rather than reached for inside the отбор: which
        БЦ may be offered is a question about who is asking (ADR 0001), and «сегодня» is
        decided once for the whole screen, above.
        """
        return ShelfSearch(self.request.GET, user=self.request.user, day=self.today)


class PartyDetailView(LoginRequiredMixin, DetailView):
    """Экран Стороны — то, что организация знает об одной Стороне, пятью блоками.

    То, что мы о ней знаем, получает собственный экран, а не рейку на чужой странице: до
    этого тикета Сторона появлялась только полем в чужой строке — именем в колонке «Кем
    выдан», названием на паспорте БЦ, арендатором на аренде.

    Экран стоит на учётной карточке, а не на Стороне (ADR 0020): платёжные реквизиты,
    контактные лица, поводы, аренды и документы висят на паре «Сторона + организация», и
    Сторона, которую знают два клиента одного читателя, дала бы один адрес с двумя ответами.
    Отсюда же и 404 на чужую карточку: привратник просто не находит строки, и отсутствие
    чужих данных выходит неотличимым от отсутствия (ADR 0006).

    Блока «Роли» на экране нет вовсе, пока `PartyRole` держит ноль строк и не имеет читателя:
    всегда пустой блок учил бы читателя, что у Сторон ролей не бывает. Створок заведения,
    правки и удаления этим тикетом тоже не появляется — они следующего.
    """

    template_name = "parties/party_detail.html"
    context_object_name = "record"

    def get_queryset(self):
        """Чужая карточка отвечает 404, а не 403, — привратник учётных карточек (ADR 0020).

        Ответ не должен подтверждать, что карточка существует: отличив «нельзя» от «нет
        такой», читатель узнал бы, с кем работает другой клиент платформы.

        Сторона и организация едут в том же запросе, что и карточка: обе названы на экране, а
        спрошенные разметкой — это два запроса на каждый разворот.

        Контактные лица берутся наперёд, потому что их читают дважды: блок под шапкой
        перечисляет людей, а поводы складывают их дни рождения с профессиональным праздником.
        Два чтения одного списка — два запроса, из которых второй ничего нового не узнаёт.
        """
        return (
            PartyRecord.objects.visible_to(self.request.user)
            .select_related("party__line_of_business", "org__party")
            .prefetch_related("contacts")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["particulars"] = particulars(
            self.object,
            # Тем же условием, каким полка заводит свою колонку «Организация»: один вопрос —
            # один ответ, и задан он там, где написан довод.
            naming_the_organisation=naming_the_organisation(self.request.user),
        )
        # Поводы — тем же правилом, каким полка считает свою колонку. «Сегодня» спрашивается
        # у часов один раз: на экране один список, и второе чтение часов было бы вторым днём,
        # о котором говорит одна и та же страница.
        context["occasions"] = occasions_said(self.object, timezone.localdate())
        # Ничего, а не пустой список, если Сторона физлицо: у неё блока контактных лиц нет
        # вовсе, и решается это в `party_page`, где стоит и вторая половина того же правила —
        # день рождения физлица в шапке.
        context["contacts"] = contacts_of(self.object)
        context["payment_details"] = payment_details_of(self.object)
        context["leases"] = leases_of(self.object)
        # Документы берутся через свой привратник и сужаются картой: документ виден по своей
        # организации, а не по Стороне, к которой привязан (ADR 0006), так что оба вопроса
        # задаются порознь — один о бумаге, другой о том, чья это карточка.
        context["documents"] = documents_issued_by(
            self.object, Document.objects.visible_to(self.request.user)
        )
        return context
