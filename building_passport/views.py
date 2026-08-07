from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class BCListView(LoginRequiredMixin, TemplateView):
    """Список БЦ — the бизнес-центры the signed-in user has access to."""

    template_name = "building_passport/bc_list.html"


class BCDetailView(LoginRequiredMixin, TemplateView):
    """Карточка БЦ — the паспорт здания of a single бизнес-центр."""

    template_name = "building_passport/bc_detail.html"
