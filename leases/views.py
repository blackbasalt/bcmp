"""Экраны аренды: список договоров и карточка договора.

Договор не принадлежит ни одному БЦ (ADR 0009), поэтому и адреса у него свои, не
вложенные в здание: `/leases/` и `/leases/<uuid>/`. Оба экрана берут данные через
`Lease.objects.visible_to` — третий чокпоинт, — и фильтра по организации не собирают.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.views.generic import DetailView, ListView

from .models import Lease


class LeaseListView(LoginRequiredMixin, ListView):
    """Список договоров — все договоры организаций, доступных сотруднику."""

    template_name = "leases/lease_list.html"
    context_object_name = "leases"

    def get_queryset(self):
        """Данные берутся через чокпоинт аренды (ADR 0009), фильтр здесь не собирается."""
        return (
            Lease.objects.visible_to(self.request.user)
            # Арендатор называется именем в каждой строке, поэтому едет тем же запросом.
            .select_related("tenant")
            # Сколько помещений названо договором — счётом в запросе, а не обходом
            # предметов на строку: список длиннее пяти зданий, и обход стоил бы
            # запроса на каждую строку.
            .annotate(space_count=Count("subjects"))
            # Порядок задан здесь, а не взят с модели: в запросе со счётом Django
            # `Meta.ordering` не применяет вовсе, и список вышел бы в том порядке, в
            # каком его вернула база. Свежий договор сверху — с ним и работают, а
            # арендатор вторым ключом держит порядок неизменным между открытиями.
            .order_by("-valid_from", "tenant__name")
        )


class LeaseDetailView(LoginRequiredMixin, DetailView):
    """Карточка договора — договор целиком вместе со своими предметами."""

    template_name = "leases/lease_detail.html"
    context_object_name = "lease"

    def get_queryset(self):
        """Чужой договор отвечает 404, а не 403: ответ не подтверждает, что он есть."""
        return Lease.objects.visible_to(self.request.user).select_related("tenant")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Помещение предмета — той же организации, что и договор: это правило стоит на
        # модели и держится на каждом пути записи, поэтому второго фильтра здесь нет.
        # Здание называется рядом с помещением: договор называет помещения нескольких
        # БЦ, и «Склад» без Boston рядом не отличить от склада в Manhattan.
        context["subjects"] = (
            self.object.subjects.select_related("space", "space__building")
            .order_by("space__building__name", "space__code")
        )
        # Прежний договор едет тем же чокпоинтом, что и открытый: ссылку `prolongs`
        # ведут руками, и указать ею на договор другой организации ничто не мешает —
        # а прочитать чужой номер и чужого арендатора по ней не должно быть можно
        # (ADR 0009). Тот же довод, что у соседей по дереву в карточке помещения.
        prior_id = self.object.prolongs_id
        context["prolongs"] = (
            Lease.objects.visible_to(self.request.user)
            .select_related("tenant")
            .filter(pk=prior_id)
            .first()
            if prior_id
            else None
        )
        return context
