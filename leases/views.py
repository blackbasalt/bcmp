"""Экраны аренды: список договоров и карточка договора.

Договор не принадлежит ни одному БЦ (ADR 0009), поэтому и адреса у него свои, не
вложенные в здание: `/leases/` и `/leases/<uuid>/`. Оба экрана берут данные через
`Lease.objects.visible_to` — третий чокпоинт, — и фильтра по организации не собирают.

Они же принимают запись: заводят договор на списке, правят на карточке, и обе формы
отправляются по адресу того экрана, на котором стоят, — как форма загрузки плана
(ADR 0005). Отдельный адрес для записи означал бы второе место, собирающее тот же
договор и то же право на него, а отказ возвращался бы на страницу без списка и без
предметов, с которыми заводивший и сверяется. Своего адреса нет и у расторжения:
досрочное расторжение — это дата окончания периода, и второе место, её пишущее,
однажды разошлось бы с первым. Удаление стоит особняком: с карточки оно уводит
всегда — на список после успеха и обратно с объяснением, если удалять нельзя.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, ProtectedError
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView, View
from django.views.generic.detail import SingleObjectMixin

from parties.models import Org

from .lease_form import LeaseWriting
from .models import Lease

#: Отказ тому, кто вести этот договор не вправе, — одной фразой на все пути записи:
#: правку и удаление отклоняют по одной причине, и двух её описаний быть не должно.
NOT_YOURS_TO_MAINTAIN = "Вести договоры этой организации может её администратор."


def administers(user, lease):
    """Вправе ли пользователь вести этот договор (ADR 0005).

    Спрашивается один раз и одним запросом: показанная кнопка, принятая правка и
    принятое удаление отвечают на один вопрос, и разойтись им нельзя — иначе экран
    предлагает то, что потом отклоняется.
    """
    return Lease.objects.administered_by(user).filter(pk=lease.pk).exists()


class LeaseListView(LoginRequiredMixin, ListView):
    """Список договоров — все договоры организаций, доступных сотруднику.

    Он же заводит договор: заводят там, где ищут, и заведённое видно на том же
    экране следующим же открытием.
    """

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Форма — только тому, кто вправе заводить: действия, которого сотруднику не
        # совершить, ему не предлагают. Отказ приносит с собой уже заполненную форму,
        # поэтому пустая ставится только на её место.
        if not self.administers_anything:
            context["writing"] = None
        else:
            context.setdefault("writing", self.blank_writing())
        return context

    def post(self, request, *args, **kwargs):
        """Заведение договора: тот же адрес, что и у списка, — форма стоит на нём."""
        if not self.administers_anything:
            # 403, а не 404: список этот сотрудник видит, и отвечать «его нет»
            # значило бы соврать о том, что уже показано (ADR 0005).
            raise PermissionDenied("Заводить договоры может администратор организации.")
        writing = LeaseWriting(request.user, data=request.POST)
        lease = writing.save() if writing.is_valid() else None
        if lease is None:
            self.object_list = self.get_queryset()
            return self.render_to_response(self.get_context_data(writing=writing))
        messages.success(request, f"Договор заведён: {lease}.")
        return redirect("leases:lease_detail", lease.pk)

    @cached_property
    def administers_anything(self):
        """Ведёт ли этот сотрудник хоть одну организацию (ADR 0005).

        Спрашивается тот же чокпоинт, что и на записи: показанная форма и принятый
        запрос должны отвечать на один вопрос одинаково, иначе экран предлагает то,
        что потом отклоняется.
        """
        return Org.objects.administered_by(self.request.user).exists()

    def blank_writing(self):
        """Пустая форма — или заполненная прежним договором, если его продлевают."""
        prior = self.prolonged
        if prior is None:
            return LeaseWriting(self.request.user)
        return LeaseWriting.prolonging(self.request.user, prior)

    @cached_property
    def prolonged(self):
        """Договор, который продлевают, — назван адресом экрана, а не скрытым состоянием.

        Пролонгация — это заведение договора со ссылкой на прежний (ADR 0007),
        поэтому и форма та же, и путь записи тот же; отличает её ровно ссылка. Взята
        она из адреса по той же причине, по какой в адресе стоят слой и день экрана
        этажа: продлевающий видит на экране то же, что увидел бы коллега, которому
        он эту ссылку перешлёт.

        Прежний договор едет тем же чокпоинтом, что и список: подставленный в адрес
        чужой ключ не должен вернуть на экран чужого арендатора с его помещениями.
        Ключ, который ключом не является, открывает пустую форму, а не ломает экран,
        — то же правило, что у дня и слоя (`screen_date.named_by`).
        """
        named = self.request.GET.get("prolongs")
        if not named:
            return None
        try:
            return Lease.objects.visible_to(self.request.user).filter(pk=named).first()
        except (ValidationError, ValueError):
            return None


class LeaseDetailView(LoginRequiredMixin, DetailView):
    """Карточка договора — договор целиком вместе со своими предметами.

    Она же его правит и расторгает: правят там, где смотрят, и отказ возвращается на
    тот же экран, рядом с предметами, по которым правку и сверяют.
    """

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
        # Правка и удаление — только тому, кто вправе вести эту организацию.
        context["administers"] = self.administers_the_lease
        if not self.administers_the_lease:
            context["writing"] = None
        else:
            context.setdefault("writing", LeaseWriting(self.request.user, self.object))
        return context

    def post(self, request, *args, **kwargs):
        """Правка договора, она же расторжение: закрытый период — это дата окончания."""
        self.object = self.get_object()
        if not self.administers_the_lease:
            # 403, а не 404: договор этот сотрудник видит, и скрывать здесь нечего —
            # скрывают чужие данные, а не собственную нехватку прав (ADR 0005).
            raise PermissionDenied(NOT_YOURS_TO_MAINTAIN)
        writing = LeaseWriting(request.user, self.object, data=request.POST)
        saved = writing.save() if writing.is_valid() else None
        if saved is None:
            return self.render_to_response(self.get_context_data(writing=writing))
        messages.success(request, "Договор исправлен.")
        return redirect("leases:lease_detail", saved.pk)

    @cached_property
    def administers_the_lease(self):
        """Ответ спрашивается один раз: отказ формы иначе задал бы тот же вопрос дважды."""
        return administers(self.request.user, self.object)


class LeaseDeleteView(LoginRequiredMixin, SingleObjectMixin, View):
    """Удаление договора — настоящее удаление, а не отдельное состояние.

    Расторгнутый договор — факт истории здания и остаётся в ней (ADR 0007), а
    опечатка фактом не была никогда: оставленная «аннулированной», она засоряла бы
    ровно ту историю, которую ADR и защищает. Кто и когда трогал запись, `CommonModel`
    записывает и так.

    Свой адрес у удаления потому, что с карточки оно уводит в любом случае: на список
    после успеха и обратно с объяснением, когда удалять нельзя. Отвечает он только на
    POST: договор не удаляют переходом по ссылке.
    """

    def get_queryset(self):
        """Чужой договор отвечает 404 — тем же чокпоинтом, что и его карточка."""
        return Lease.objects.visible_to(self.request.user)

    def post(self, request, *args, **kwargs):
        lease = self.get_object()
        if not administers(request.user, lease):
            raise PermissionDenied(NOT_YOURS_TO_MAINTAIN)
        named = str(lease)
        try:
            lease.delete()
        except ProtectedError:
            # Цепочку пролонгаций рвать молча нечем: прежний договор — то, ради чего
            # ссылка и заведена, и снявший её должен знать, что снимает.
            messages.error(
                request,
                f"{named} удалить нельзя: на него ссылается пролонгация. Удалите "
                f"сначала её или снимите ссылку.",
            )
            return redirect("leases:lease_detail", lease.pk)
        messages.success(request, f"{named} удалён.")
        return redirect("leases:lease_list")
