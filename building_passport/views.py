from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Q
from django.views.generic import DetailView, ListView

from .models import Space
from .passport_sections import sections


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
        return context
