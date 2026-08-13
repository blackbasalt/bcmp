from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.functional import cached_property
from django.views.generic import ListView

from parties.models import Org

from .document_display import documents_shown
from .models import Document


class DocumentListView(LoginRequiredMixin, ListView):
    """Раздел «Документы» — вся полка организации одним экраном.

    Первый экран проекта, до которого не открывают здание: документ может быть
    привязан к нескольким БЦ, а может не быть привязан ни к одному, и вход через
    здание прятал бы устав и лицензию, которые не относятся ни к какому зданию.
    """

    template_name = "documents/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        """Данные берутся через чокпоинт документов (ADR 0006), фильтр здесь не собирается."""
        return (
            Document.objects.visible_to(self.request.user)
            # Организация и выдавшая сторона называются именами, поэтому едут тем же
            # запросом, что и сами документы.
            .select_related("org__party", "issuer_party")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documents = context["documents"]
        # Счёт считается по тому же набору, который поедет в таблицу: число под ней
        # и строки в ней разойтись не должны.
        context["shown"] = documents_shown(len(documents))
        # Организация называется тому, кто ведёт не одного клиента: ему полка общая,
        # и «чья это бумага» — вопрос, который он задаёт о каждой строке. Сотруднику
        # одного клиента колонка повторяла бы одно имя во всю таблицу.
        #
        # Спрашивается это о читателе, а не о показанном: колонка, зависящая от
        # данных, пропала бы ровно тогда, когда у второго клиента документов ещё
        # нет, — а это тот самый случай, когда назвать организацию и надо.
        context["organisation_named"] = self.organisations_of_the_reader > 1
        return context

    @cached_property
    def organisations_of_the_reader(self):
        """Скольких клиентов ведёт читатель — вопрос о нём, а не о его документах.

        Правами он не распоряжается и строк не отбирает: чьи документы показывать,
        решает один чокпоинт (ADR 0006), а здесь считается, надо ли их подписывать.
        Суперпользователь читает за всех, поэтому и организаций у него все.
        """
        user = self.request.user
        if user.is_superuser:
            return Org.objects.count()
        return user.memberships.count()
