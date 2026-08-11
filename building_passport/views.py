from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView, View

from dictionary.models import DictSpaceType
from leases.models import Lease, LeaseSubject

from . import plan_completeness, plan_layer, screen_date, vacancy
from .models import FloorPlan, Space
from .passport_sections import sections
from .plan_upload import FloorPlanForm
from .space_tree import spaces_under, tree_under


class BCListView(LoginRequiredMixin, ListView):
    """Список БЦ — the бизнес-центры the signed-in user has access to."""

    template_name = "building_passport/bc_list.html"
    context_object_name = "buildings"

    def get_queryset(self):
        """Данные берутся через единый чокпоинт (ADR 0001), фильтр здесь не собирается."""
        # Помещения БЦ ссылаются на него и как на родителя, и денормализованным
        # `building`; для значка достаточно любой из связей. Подзапрос тоже идёт
        # через чокпоинт: чужая строка не должна снимать значок.
        spaces = Space.objects.visible_to(self.request.user).filter(
            Q(parent=OuterRef("pk")) | Q(building=OuterRef("pk"))
        )
        return (
            Space.objects.buildings_visible_to(self.request.user)
            # `parent__parent` — те же два уровня над БЦ, что разматывает `Space.project`.
            .select_related("passport", "parent__parent")
            .annotate(has_spaces=Exists(spaces))
            .order_by("name")
        )


class BCDetailView(LoginRequiredMixin, DetailView):
    """Карточка БЦ — the паспорт здания of a single бизнес-центр."""

    template_name = "building_passport/bc_detail.html"
    context_object_name = "building"

    def get_queryset(self):
        """Чужой БЦ отвечает 404, а не 403: ответ не подтверждает, что он существует."""
        return (
            Space.objects.buildings_visible_to(self.request.user)
            # Стороны показываются именами, поэтому едут тем же запросом, что и паспорт.
            .select_related(
                "passport__owner_party",
                "passport__operator_party",
                "passport__designer_party",
                "passport__builder_party",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Паспорт может быть ещё не заведён — это состояние данных, а не ошибка экрана.
        context["sections"] = sections(getattr(self.object, "passport", None))
        visible = Space.objects.visible_to(self.request.user)
        # Вход внутрь здания: у БЦ без нутра список пуст и раздел не показывается.
        floors = visible.floors_of(self.object)
        context["floors"] = floors
        # День, на который считается ответ, — из адреса, как и на экране этажа: вопрос
        # «что освобождается к январю» задают зданию не реже, чем этажу, и переходят с
        # карточки прямо на этаж, где тот же `?date=` уже понимают. Второй оси времени
        # здесь нет: чертежа на карточке не стоит, и подменять ответом нечего
        # (ADR 0010), — поэтому и предупреждения о выходе за период плана здесь нет.
        today = timezone.localdate()
        chosen_day = screen_date.named_by(self.request.GET, today)
        context["as_of"] = screen_date.as_of(chosen_day, today)
        # Вакансия всего здания: тот же счёт, что и на этаже, по более широкому набору
        # помещений — не второй счёт того же, поэтому этажи и здание складываются.
        #
        # Набор — объединение наборов этажей, помещение в помещение: ровно то, что
        # считает каждый экран этажа, и ничего сверх. Спуск от самого здания был бы
        # короче на строку и складываться перестал бы: под БЦ лежат не только этажи, и
        # `man-roof` с тех помещениями под ней уже есть в данных — арендопригодной её
        # делает одна правка. Такое помещение прибавилось бы к числу здания, не попав
        # ни в один из этажей, а сами этажи вошли бы в счёт своей площадью поверх
        # площади помещений на них. Мимо этажа при этом ничего арендопригодного лежать
        # и не должно: помещение — часть здания внутри этажа.
        #
        # Всё нутро одним запросом, как и на этаже: обход по узлам стоил бы запроса на
        # каждое помещение. Запрос этот ленив, и у четырёх БЦ без нутра, где этажей
        # нет, он не выполняется вовсе.
        inside = visible.filter(building=self.object)
        context["vacancy"] = vacancy.vacancy_on(
            chosen_day,
            tuple(space for floor in floors for space in spaces_under(floor, inside)),
            Lease.objects.visible_to(self.request.user),
        )
        return context


class FloorView(LoginRequiredMixin, DetailView):
    """Экран этажа — дерево помещений слева, план в центре, карточка помещения справа.

    Он же принимает загрузку плана: форма стоит на этом экране, и отправляется она
    по его же адресу. Отдельный адрес для записи означал бы второе место, которое
    собирает тот же этаж и то же право на него, а отказ формы возвращался бы на
    страницу без дерева и без чертежа, с которыми загрузившему и надо сверяться.
    """

    template_name = "building_passport/floor.html"
    context_object_name = "floor"

    def get_queryset(self):
        """Чужой этаж, этаж чужого БЦ и не-этаж отвечают одинаково — 404.

        Признаков у этажа три, и все три проверяются запросом: он виден
        пользователю, он именно этаж и он принадлежит зданию из адреса. Ответ,
        различающий эти случаи, рассказывал бы о данных другого клиента.
        """
        return (
            Space.objects.visible_to(self.request.user)
            .filter(type=DictSpaceType.FLOOR, building_id=self.kwargs["bc_pk"])
            .select_related("building")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible = Space.objects.visible_to(self.request.user)
        plans = FloorPlan.objects.visible_to(self.request.user)
        building = self.object.building
        context["building"] = building
        # Сегодняшний день берётся один раз на весь экран: значок в переключателе и
        # чертёж в центре должны говорить об одном и том же дне, даже если запрос
        # пришёлся на полночь.
        today = timezone.localdate()
        in_force = plans.in_force_on(today)
        # Значок плана в переключателе: иначе по этажам щёлкают в надежде найти чертёж.
        # Подзапрос идёт через тот же чокпоинт — чужая строка не должна ставить значок.
        # Обещает он ровно то, что откроется: этаж с одним лишь будущим планом чертежа
        # сегодня не покажет, и значка на нём нет.
        context["floors"] = visible.floors_of(building).annotate(
            has_plan=Exists(in_force.filter(floor=OuterRef("pk")))
        )
        # Планировку показывает действующий план, а не последний загруженный: работы
        # планируют по сегодняшнему чертежу, и назначенная на будущее перепланировка
        # до своей даты на экран не выходит.
        plan = in_force.filter(floor=self.object).first()
        context["plan"] = plan
        # Контуры отбираются тем же чокпоинтом, что и дерево: помещение другого клиента,
        # оказавшееся под этим этажом, не должно проехать на экран именем и формой.
        # Его помещение едет тем же запросом — по нему слой и красит контур.
        contours = (
            plan.contours.filter(space__in=visible).select_related("space").order_by("space__code")
            if plan
            else ()
        )
        # Цвет контура и легенда к нему — правило слоя, посчитанное здесь, а не набор
        # классов в разметке: следующий слой встанет на это же место, и экрану для него
        # ничего не потребуется. Слой на плане один за раз, и какой — сказано адресом:
        # ссылку на вид пересылают коллеге, и открыться у него должно ровно то же.
        # День, на который смотрит экран, — из адреса, сегодняшний по умолчанию: «что
        # освобождается к январю» спрашивают ссылкой, которую можно переслать. Сегодня
        # берётся то же самое, которым выбран чертёж: осей времени две (ADR 0010), и
        # разъезжаться на полуночном запросе им нельзя.
        chosen_day = screen_date.named_by(self.request.GET, today)
        # Экран отдаётся слою целиком: собирается слой тем, что ему нужно — днём, на
        # который экран смотрит, и договорами, видимыми спросившему, — и что именно,
        # его дело, а не экрана. Переключатель приходит из того же реестра, что и слой
        # из адреса: разойтись список слоёв и выбранный слой не могут.
        layer = plan_layer.chosen_by(self.request.GET)
        screen = plan_layer.Screen(day=chosen_day, user=self.request.user)
        context["painting"] = layer.build(screen).apply(contours)
        context["layers"] = plan_layer.choices(self.request.GET)
        # День принадлежит экрану, а не слою: счёт свободного считается на него при
        # любом слое, и «на 1 января» рядом со счётом — не украшение подписи, а часть
        # ответа. Называет его экран по тому же правилу, что и Карточка БЦ, — и потому
        # правило спрашивается, а не переписывается здесь во второй раз. Там, где
        # выбранный день выпал из периода плана, экран говорит и это: чертёж на экране
        # сегодняшний, а ответ посчитан на другой день (ADR 0010).
        context["as_of"] = screen_date.as_of(chosen_day, today)
        context["outside_the_plan"] = screen_date.outside_the_plan(plan, chosen_day)
        # Всё нутро здания одним запросом: дерево вложено на произвольную глубину,
        # и обход по узлам стоил бы запроса на каждое помещение. Лишнее отсекает
        # само дерево: под этажом оказывается только то, что связано с ним через
        # `parent`.
        inside = visible.filter(building=building).order_by("code", "name")
        context["tree"] = tree_under(self.object, inside)
        under = spaces_under(self.object, inside)
        # Вакансия: сколько арендопригодных помещений этажа свободно, сколько это
        # метров и на скольких договорах счёт стоит. Считается на тот же день, что и
        # слой, и по тем же помещениям, что и дерево: разойдись они, экран показывал
        # бы одни помещения, а считал другие.
        #
        # Чертежа счёт не спрашивает и без него не молчит, в отличие от полноты:
        # вакансия — свойство этажа, а не плана, и этаж, чей план не загружен, должен
        # отвечать на первый вопрос, который управляющей компании задают.
        context["vacancy"] = vacancy.vacancy_on(
            chosen_day, under, Lease.objects.visible_to(self.request.user)
        )
        # Полнота: сколько помещений этажа нанесено, какие остались без контура и
        # какие пути чертежа не нашли помещения. Одним счётом на весь экран — им же
        # помечаются узлы дерева, потому что метка в дереве и число под планом
        # говорят об одном и том же и разойтись не должны.
        #
        # Считается только против действующего плана: без него не нанесено вообще
        # ничего, и «0 из 82» с меткой на каждом узле сообщали бы ровно то же, что и
        # пустой центр экрана.
        context["completeness"] = plan_completeness.completeness_of(
            under if plan else (),
            contours,
            plan.unmatched_ids if plan else (),
        )
        # Форма загрузки — только тому, кто вправе загружать: действия, которого
        # сотруднику не совершить, ему и не предлагают. Отказ приносит с собой уже
        # заполненную форму, поэтому пустая ставится только на её место.
        if not self.administers_the_floor:
            context["upload"] = None
        else:
            context.setdefault("upload", FloorPlanForm(floor=self.object))
        return context

    def post(self, request, *args, **kwargs):
        """Загрузка плана: тот же адрес, что и у экрана, — форма стоит именно на нём.

        Отказ возвращает тот же экран с причиной на форме, а успех — переход на него
        же: перезагруженный экран и есть подтверждение, и новый действующий план
        встаёт на место прежнего сам.
        """
        self.object = self.get_object()
        if not self.administers_the_floor:
            # 403, а не 404: этаж этот сотрудник видит, и отвечать «его нет» значило
            # бы соврать о том, что уже показано. Скрывать здесь нечего — скрывают
            # чужие данные, а не собственную нехватку прав (ADR 0005).
            raise PermissionDenied("Загружать планы этой организации может её администратор.")
        form = FloorPlanForm(request.POST, request.FILES, floor=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(upload=form))
        plan = form.save()
        messages.success(request, self.upload_report(plan))
        return redirect("building_passport:floor", self.object.building_id, self.object.pk)

    @cached_property
    def administers_the_floor(self):
        """Вправе ли этот пользователь вести данные организации этого этажа (ADR 0005).

        Спрашивается тот же чокпоинт, что и на записи: показанная кнопка и принятый
        запрос должны отвечать на один вопрос одинаково, иначе форма предлагает то,
        что потом отклоняется. Ответ на запрос один, поэтому и спрашивается он один
        раз: отказ формы иначе задавал бы тот же вопрос дважды.
        """
        return Space.objects.administered_by(self.request.user).filter(pk=self.object.pk).exists()

    @staticmethod
    def upload_report(plan):
        """Что сказать о загруженном плане: с какого дня он действует и виден ли уже.

        План с будущей датой на экран сегодня не выходит — и загрузивший должен
        узнать это от нас, а не из неизменившегося экрана, который он примет за
        потерянный файл. Про прежний план фраза при этом молчит: его может и не
        быть вовсе, и обещать чертёж, которого нет, — та же выдумка, что и дата.

        Действует ли план сегодня, спрашивается у того же `in_force_on`, которым
        экран выбирает чертёж: второе сравнение дат разошлось бы с первым.
        """
        loaded = f"План загружен. Планировка действует с {plan.valid_from:%d.%m.%Y}"
        in_force = FloorPlan.objects.in_force_on(timezone.localdate())
        if in_force.filter(pk=plan.pk).exists():
            return f"{loaded}."
        return f"{loaded} — до этого дня экран этажа его не показывает."


class SpaceCardView(LoginRequiredMixin, DetailView):
    """Карточка помещения — правая панель экрана этажа, а не отдельный экран.

    Ответ — кусок разметки, который HTMX кладёт в панель: план при этом остаётся на
    экране, и пространственный контекст, приведший читателя к помещению, не тратится
    на чтение о нём.
    """

    template_name = "building_passport/_space_card.html"
    context_object_name = "space"

    def get_queryset(self):
        """Чужое помещение отвечает 404 — тем же чокпоинтом, что и экраны (ADR 0001)."""
        return Space.objects.visible_to(self.request.user).select_related("subtype")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Соседи по дереву едут тем же чокпоинтом, что и само помещение, — и тот, что
        # выше, тоже: пройти по `parent` напрямую значило бы завести второе место, где
        # решается, чьи данные показывать (ADR 0001). Чужая строка не должна проехать
        # в панель именем, как не проезжает в дерево и на план.
        visible = Space.objects.visible_to(self.request.user)
        context["children"] = visible.filter(parent=self.object).order_by("code", "name")
        parent_id = self.object.parent_id
        parent = visible.filter(pk=parent_id).first() if parent_id else None
        context["parent"] = parent
        # Этаж над помещением называется, но карточкой не открывается: он не узел
        # дерева, а сам экран, на котором панель и стоит, — ссылка вела бы на месте.
        context["parent_is_a_space"] = parent is not None and parent.type != DictSpaceType.FLOOR
        # Аренда: кто занимает помещение, на какой срок и по какой ставке — то, ради
        # чего с точки на плане и приходят. Без этого сотрудник УК видит, что
        # помещение 301 арендопригодно, и не видит, кто в нём сидит.
        context["subject"] = self.subject_in_force_today()
        return context

    def subject_in_force_today(self):
        """Предмет договора, действующего на это помещение сегодня, — или ничего.

        Спрашивается предмет, а не договор: ставка стоит на предмете, и договор,
        называющий офис и склад, называет две разные. Договор при этом едет тем же
        запросом — им карточка называет арендатора, срок и адрес самого договора.

        Считается на сегодня, а не на день из адреса экрана этажа, — так сказано в
        #30. С ADR 0010 это расходится: день там принадлежит экрану, и на выбранный
        день считается всё, что стоит рядом с чертежом, — а панель стоит именно там.
        Расхождение видно глазами: на `?date=2027-01-01` слой красит контур свободным,
        а карточка того же помещения называет сегодняшнего арендатора. Своего адреса
        с днём у панели при этом нет вовсе — она приезжает по `space/<uuid>/card/`, —
        так что дальше это либо день в её адресе, либо день, названный на ней самой.

        Договор на помещение в этот день ровно один: периоды по одному помещению не
        пересекаются, и стоит это правило на модели (ADR 0007). Мимо него проходит то
        же, что и мимо правила слоя, — `update()`, `bulk_create()` и SQL руками; на
        разъехавшихся так данных карточка назовёт произвольный из двух, и чинить их
        придётся тем же способом, каким сломали.

        Договоры отбираются тем же чокпоинтом, что и всё остальное (ADR 0009):
        карточка не заводит второго места, где решается, чьи данные показывать.
        """
        return (
            LeaseSubject.objects.filter(
                space=self.object, lease__in=Lease.objects.visible_to(self.request.user)
            )
            .in_force_on(timezone.localdate())
            .select_related("lease__tenant")
            .first()
        )


class FloorPlanSVGView(LoginRequiredMixin, View):
    """Файл чертежа — тот же путь чтения, что и экраны, а не отдельная дверь.

    Раздача через nginx мимо приложения отдала бы чертёж клиента любому, кто знает
    адрес: это ровно та утечка, ради которой заведён чокпоинт (ADR 0001). Поэтому
    файл едет через `visible_to`, а чужой план отвечает 404, а не 403.
    """

    def get(self, request, pk):
        plan = get_object_or_404(FloorPlan.objects.visible_to(request.user), pk=pk)
        response = FileResponse(plan.file.open("rb"), content_type="image/svg+xml")
        # SVG — исполняемый формат, а раздаётся он с домена приложения: открытый по
        # адресу напрямую, он выполнялся бы как наша страница. Песочница лишает его
        # нашего происхождения, а `nosniff` — возможности назваться другим типом.
        response["Content-Security-Policy"] = "sandbox"
        response["X-Content-Type-Options"] = "nosniff"
        return response
