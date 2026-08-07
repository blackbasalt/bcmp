from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Q
from django.views.generic import DetailView, ListView

from dictionary.models import DictSpaceType

from .models import Space
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
        building = self.object.building
        context["building"] = building
        context["floors"] = visible.floors_of(building)
        # Всё нутро здания одним запросом: дерево вложено на произвольную глубину,
        # и обход по узлам стоил бы запроса на каждое помещение. Лишнее отсекает
        # само дерево: под этажом оказывается только то, что связано с ним через
        # `parent`.
        inside = visible.filter(building=building).order_by("code", "name")
        context["tree"] = tree_under(self.object, inside)
        return context
