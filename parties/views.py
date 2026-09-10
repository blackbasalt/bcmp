from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView

from documents.models import Document
from leases.occupancy import rooms_of_each_record

from . import occasions
from .models import Org, PartyRecord
from .party_display import entry_said, parties_shown
from .party_entry import PartyEntryForm
from .party_page import (
    contacts_of,
    documents_issued_by,
    leases_of,
    occasions_said,
    particulars,
    payment_details_of,
    stands_for_herself,
)
from .record_keeping import BirthdayForm, ContactPersonForm, PaymentDetailsForm
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

    Створка заведения стоит здесь и отправляется на этот же адрес: Сторону заводят там, где о
    ней читают, и отказ возвращается на экран, с которого форму отправляли, — то же
    устройство, что пакетная загрузка на полке документов и загрузка плана на экране этажа
    (ADR 0005). Заведённая Сторона на этот экран не возвращается: следом открывается её
    собственный (ADR 0021).
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
        # Створка достаётся только тому, кто вправе заводить: действия, которое сотруднику не
        # выполнить, ему и не предлагают — показанная форма, отклоняющая отправку, читается
        # как сломанный экран (ADR 0005). Отказ приносит свою, уже заполненную, так что пустая
        # ставится только на её место.
        if not self.administers_anything:
            context["entry"] = None
        else:
            context.setdefault("entry", PartyEntryForm(user=self.request.user))
        return context

    def post(self, request, *args, **kwargs):
        """Заведение Стороны: тот же адрес, что и у раздела, — створка стоит на нём.

        Отказ возвращает тот же экран с причиной на форме, а заведение уводит на экран
        заведённой Стороны: перезагруженный экран и есть подтверждение, а то единственное, чего
        на нём не прочесть — что БИН был занят, — сказано словами над ним.
        """
        if not self.administers_anything:
            # 403, а не 404: раздел этому сотруднику показан, и «его нет» было бы неправдой о
            # том, что уже на экране. Скрывают чужие данные, а не собственную нехватку прав
            # (ADR 0005).
            raise PermissionDenied("Заводить Стороны может администратор организации.")
        form = PartyEntryForm(request.POST, user=request.user)
        if not form.is_valid():
            self.object_list = self.get_queryset()
            return self.render_to_response(self.get_context_data(entry=form))
        entered = form.save()
        said = entry_said(entered)
        if said is not None:
            messages.add_message(request, *said)
        return redirect("parties:party_detail", entered.record.pk)

    @cached_property
    def administers_anything(self):
        """Ведёт ли этот сотрудник данные хоть какой-нибудь организации (ADR 0005).

        Тот же вопрос, что задаётся на записи: показанная форма и принятый запрос обязаны
        отвечать на него одинаково, иначе экран предлагает то, в чём потом отказывает. Какой
        именно организации достанется карточка, решает сама форма — здесь только о том, есть
        ли створка вообще.
        """
        return Org.objects.administered_by(self.request.user).exists()

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
    всегда пустой блок учил бы читателя, что у Сторон ролей не бывает.

    Три створки стоят в блоках, которые они пополняют, и отправляются на адрес самого экрана:
    комплект платёжных реквизитов, контактное лицо и день рождения физлица — то, что висит на
    карточке и что её организация ведёт всегда (ADR 0021). Общая половина Стороны ими не
    трогается: её правка замирает, когда Сторону знает кто-то ещё, и это другое правило с
    другим радиусом (ADR 0028).
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
        # Створки достаются только тому, кто вправе вести данные этой организации: действия,
        # в котором сотруднику откажут, ему и не предлагают — показанная форма, отклоняющая
        # отправку, читается как сломанный экран (ADR 0005). Отказ приносит свою, уже
        # заполненную, так что пустая ставится только на её место.
        if not self.administers_the_record:
            context["payment_entry"] = None
            context["contact_entry"] = None
            context["birthday_entry"] = None
        else:
            context.setdefault("payment_entry", PaymentDetailsForm(record=self.object))
            # Ничего, а не форма, если Сторона физлицо, — той же половиной правила, какой
            # решается сам блок контактных лиц: «не бывает» и «не заведено» отвечаются на этом
            # экране одинаково, и створка над отсутствующим блоком сказала бы второе.
            context.setdefault(
                "contact_entry",
                None
                if stands_for_herself(self.object.party)
                else ContactPersonForm(record=self.object),
            )
            # И вторая половина того же правила: день рождения ведут там, где его некому
            # отдать, — на карточке физлица. У юрлица створки нет вовсе, потому что его дни
            # рождения принадлежат его людям и заводятся в блоке контактных лиц.
            context.setdefault(
                "birthday_entry",
                BirthdayForm(instance=self.object)
                if stands_for_herself(self.object.party)
                else None,
            )
        return context

    def post(self, request, *args, **kwargs):
        """Ведение карточки — отправки по адресу самого экрана, на котором стоят створки.

        Один адрес, потому что все они стоят на этой карточке и с неё же читаются: отказ
        возвращается на тот экран, с которого форму отправляли, вместе со Стороной вокруг
        него (ADR 0005). Тот же порядок, что у страницы документа с её пятью отправками.
        """
        self.object = self.get_object()
        if not self.administers_the_record:
            # 403, а не 404: экран этой карточки сотруднику показан, и «её нет» было бы
            # неправдой о том, что уже перед ним. Чужая карточка отвечает 404 выше, и
            # отвечает им записи по той же причине, по какой чтению (ADR 0006, ADR 0005).
            raise PermissionDenied("Вести учётную карточку может администратор организации.")
        # Створка комплекта реквизитов себя не называет: она стоит на всякой карточке, у
        # юрлица и у физлица, и всё, что не назвалось, есть она. Остальные называют — то же
        # правило, по которому страница документа различает свои пять отправок.
        submitted = request.POST.get("submitted")
        if submitted == "contact":
            return self.enter_a_contact_person(request)
        if submitted == "birthday":
            return self.mark_the_birthday(request)
        return self.enter_payment_details(request)

    def enter_payment_details(self, request):
        """Завести комплект платёжных реквизитов — счёт рядом с прежним, а не вместо него.

        Отказ возвращает тот же экран с причиной на форме и набранным в ней, а заведённое
        подтверждается перезагруженным экраном: комплект стоит в своём блоке, и сказать о нём
        словами было бы нечего.
        """
        form = PaymentDetailsForm(request.POST, record=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(payment_entry=form))
        form.save()
        return redirect("parties:party_detail", self.object.pk)

    def enter_a_contact_person(self, request):
        """Завести контактное лицо — человека внутри Стороны, а не вторую Сторону.

        У физлица створки нет, и отправка мимо неё отвечает 404: не «нельзя», а «такого не
        бывает» — представителя физлицу не заводят вовсе (ADR 0025), и 403 сказал бы, что
        право на это существует и кому-то принадлежит. Тем же кодом отвечает карточка помещения
        отправке, называющей чужую аренду: набранный руками адрес и промах створки не стоят
        двух разных экранов.
        """
        if stands_for_herself(self.object.party):
            raise Http404("Контактных лиц у физлица не бывает.")
        form = ContactPersonForm(request.POST, record=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(contact_entry=form))
        form.save()
        return redirect("parties:party_detail", self.object.pk)

    def mark_the_birthday(self, request):
        """Записать день рождения физлица — единственное, что ведут на самой карточке.

        У юрлица створки нет, и отправка мимо неё отвечает 404 — тем же ответом и по тому же
        доводу, что и контактное лицо на физлице: не «нельзя», а «такого не бывает».
        """
        if not stands_for_herself(self.object.party):
            raise Http404("День рождения юрлица — это дни рождения его людей.")
        form = BirthdayForm(request.POST, instance=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(birthday_entry=form))
        form.save()
        return redirect("parties:party_detail", self.object.pk)

    @cached_property
    def administers_the_record(self):
        """Ведёт ли этот сотрудник данные организации, чья это карточка (ADR 0005).

        Уже названной организации, а не какой-нибудь: чья карточка перед читателем, сказано
        адресом, и вопрос «ведёт ли он хоть что-нибудь», которым обходится полка, предложил бы
        здесь администратору одного клиента створки над данными другого. Тот же вопрос, каким
        страница документа проверяет право на свою бумагу.
        """
        return (
            Org.objects.administered_by(self.request.user)
            .filter(pk=self.object.org_id)
            .exists()
        )
