from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView, View

from dictionary.models import DictSpaceType

from .models import FloorPlan, Space
from .passport_sections import sections
from .space_tree import tree_under


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
        # Вход внутрь здания: у БЦ без нутра список пуст и раздел не показывается.
        context["floors"] = Space.objects.visible_to(self.request.user).floors_of(self.object)
        return context


class FloorView(LoginRequiredMixin, DetailView):
    """Экран этажа — дерево помещений слева, план в центре, карточка помещения справа."""

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
        # Значок плана в переключателе: иначе по этажам щёлкают в надежде найти чертёж.
        # Подзапрос идёт через тот же чокпоинт — чужая строка не должна ставить значок.
        context["floors"] = visible.floors_of(building).annotate(
            has_plan=Exists(plans.filter(floor=OuterRef("pk")))
        )
        plan = plans.latest_for(self.object)
        context["plan"] = plan
        # Контуры отбираются тем же чокпоинтом, что и дерево: помещение другого клиента,
        # оказавшееся под этим этажом, не должно проехать на экран именем и формой.
        # Его помещение едет тем же запросом — при наведении на контур видно имя.
        context["contours"] = (
            plan.contours.filter(space__in=visible).select_related("space").order_by("space__code")
            if plan
            else ()
        )
        # Всё нутро здания одним запросом: дерево вложено на произвольную глубину,
        # и обход по узлам стоил бы запроса на каждое помещение. Лишнее отсекает
        # само дерево: под этажом оказывается только то, что связано с ним через
        # `parent`.
        inside = visible.filter(building=building).order_by("code", "name")
        context["tree"] = tree_under(self.object, inside)
        return context


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
