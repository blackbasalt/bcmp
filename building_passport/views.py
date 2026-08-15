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

from . import plan_completeness, plan_layer
from .models import FloorPlan, Space
from .passport_sections import sections
from .plan_upload import FloorPlanForm
from .space_tree import spaces_under, tree_under


class BCListView(LoginRequiredMixin, ListView):
    """The list of BCs — the business centres the signed-in user has access to."""

    template_name = "building_passport/bc_list.html"
    context_object_name = "buildings"

    def get_queryset(self):
        """Data comes through the single checkpoint (ADR 0001); no filter is built here."""
        # The spaces of a BC point at it both as their parent and through the
        # denormalised `building`; either link is enough for the badge. The subquery
        # goes through the checkpoint too: another client's row must not clear the badge.
        spaces = Space.objects.visible_to(self.request.user).filter(
            Q(parent=OuterRef("pk")) | Q(building=OuterRef("pk"))
        )
        return (
            Space.objects.buildings_visible_to(self.request.user)
            # `parent__parent` — the same two levels above a BC that `Space.project` unwinds.
            .select_related("passport", "parent__parent")
            .annotate(has_spaces=Exists(spaces))
            .order_by("name")
        )


class BCDetailView(LoginRequiredMixin, DetailView):
    """The BC card — the building passport of a single business centre."""

    template_name = "building_passport/bc_detail.html"
    context_object_name = "building"

    def get_queryset(self):
        """Another client's BC answers 404, not 403: the answer must not confirm it exists."""
        return (
            Space.objects.buildings_visible_to(self.request.user)
            # Parties are shown by name, so they travel in the same query as the passport.
            .select_related(
                "passport__owner_party",
                "passport__operator_party",
                "passport__designer_party",
                "passport__builder_party",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The passport may not have been created yet — a state of the data, not a screen error.
        context["sections"] = sections(getattr(self.object, "passport", None))
        # The way into the building: a BC with no interior has an empty list and no section.
        context["floors"] = Space.objects.visible_to(self.request.user).floors_of(self.object)
        return context


class FloorView(LoginRequiredMixin, DetailView):
    """The floor screen — the tree of spaces, the plan in the middle, the space card on the right.

    It also accepts plan uploads: the form lives on this screen and is submitted to
    this same address. A separate address for writing would mean a second place that
    assembles the same floor and the same right to it, and a rejected form would come
    back on a page without the tree and without the drawing — the very things the
    uploader needs to check against.
    """

    template_name = "building_passport/floor.html"
    context_object_name = "floor"

    def get_queryset(self):
        """Another client's floor, a floor of another BC and a non-floor all answer the same — 404.

        A floor has three marks, and the query checks all three: it is visible to the
        user, it really is a floor, and it belongs to the building named in the
        address. An answer that told these cases apart would talk about another
        client's data.
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
        # Today is taken once for the whole screen: the badge in the switcher and the
        # drawing in the middle must speak about the same day, even if the request
        # happened to land on midnight.
        in_force = plans.in_force_on(timezone.localdate())
        # The plan badge in the switcher: without it people click through floors hoping
        # to find a drawing. The subquery goes through the same checkpoint — another
        # client's row must not set the badge. It promises exactly what will open: a
        # floor whose only plan lies in the future shows no drawing today, and carries
        # no badge either.
        context["floors"] = visible.floors_of(building).annotate(
            has_plan=Exists(in_force.filter(floor=OuterRef("pk")))
        )
        # The layout is shown by the plan in force, not by the last one uploaded: work
        # is planned against today's drawing, and a rebuild scheduled for the future
        # stays off the screen until its date.
        plan = in_force.filter(floor=self.object).first()
        context["plan"] = plan
        # Contours are selected through the same checkpoint as the tree: another
        # client's space that happens to sit under this floor must not reach the screen
        # by name or by shape. Its space travels in the same query — the layer paints
        # the contour from it.
        contours = (
            plan.contours.filter(space__in=visible).select_related("space").order_by("space__code")
            if plan
            else ()
        )
        # The colour of a contour and its legend entry are the layer's rule, computed
        # here rather than being a set of classes in the markup: the next layer will
        # take this same place, and the screen will need nothing new for it. There is
        # one layer on the plan at a time, and so far only one has been defined.
        context["painting"] = plan_layer.SPACE_TYPE.apply(contours)
        # The whole interior of the building in one query: the tree nests to an
        # arbitrary depth, and walking it node by node would cost a query per space.
        # The tree itself cuts off what does not belong: only what is linked to the
        # floor through `parent` ends up under it.
        inside = visible.filter(building=building).order_by("code", "name")
        context["tree"] = tree_under(self.object, inside)
        # Completeness: how many spaces of the floor are drawn, which are left without
        # a contour and which paths of the drawing found no space. One count for the
        # whole screen — the same one marks the tree nodes, because the mark in the
        # tree and the figure under the plan speak about the same thing and must not
        # drift apart.
        #
        # It is counted only against the plan in force: without one nothing is drawn at
        # all, and "0 of 82" with a mark on every node would say exactly what the empty
        # middle of the screen already says.
        context["completeness"] = plan_completeness.completeness_of(
            spaces_under(self.object, inside) if plan else (),
            contours,
            plan.unmatched_ids if plan else (),
        )
        # The upload form goes only to whoever may upload: an action an employee cannot
        # perform is not offered to them either. A rejection brings its own already
        # filled-in form, so the empty one is only put in its place.
        if not self.administers_the_floor:
            context["upload"] = None
        else:
            context.setdefault("upload", FloorPlanForm(floor=self.object))
        return context

    def post(self, request, *args, **kwargs):
        """Uploading a plan: the same address as the screen — the form stands on it.

        A rejection returns the same screen with the reason on the form, and success
        redirects back to it: the reloaded screen is the confirmation, and the new plan
        in force takes the place of the previous one by itself.
        """
        self.object = self.get_object()
        if not self.administers_the_floor:
            # 403, not 404: this employee can see the floor, and answering "it does not
            # exist" would lie about what has already been shown. There is nothing to
            # hide here — what gets hidden is other clients' data, not one's own lack
            # of rights (ADR 0005).
            raise PermissionDenied("Загружать планы этой организации может её администратор.")
        form = FloorPlanForm(request.POST, request.FILES, floor=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(upload=form))
        plan = form.save()
        messages.success(request, self.upload_report(plan))
        return redirect("building_passport:floor", self.object.building_id, self.object.pk)

    @cached_property
    def administers_the_floor(self):
        """Whether this user may maintain the data of this floor's organisation (ADR 0005).

        The same checkpoint is asked as on writing: the button that is shown and the
        request that is accepted must answer one question the same way, otherwise the
        form offers what is later rejected. There is one answer per request, so it is
        asked once: a rejected form would otherwise ask the same question twice.
        """
        return Space.objects.administered_by(self.request.user).filter(pk=self.object.pk).exists()

    @staticmethod
    def upload_report(plan):
        """What to say about the uploaded plan: from which day it applies and whether it shows.

        A plan with a future date does not reach the screen today — and the uploader
        must learn that from us rather than from an unchanged screen they would read as
        a lost file. The phrase stays silent about the previous plan: there may be none
        at all, and promising a drawing that does not exist is the same invention as an
        invented date.

        Whether the plan is in force today is asked of the same `in_force_on` the
        screen uses to pick the drawing: a second date comparison would drift from the
        first.
        """
        loaded = f"План загружен. Планировка действует с {plan.valid_from:%d.%m.%Y}"
        in_force = FloorPlan.objects.in_force_on(timezone.localdate())
        if in_force.filter(pk=plan.pk).exists():
            return f"{loaded}."
        return f"{loaded} — до этого дня экран этажа его не показывает."


class SpaceCardView(LoginRequiredMixin, DetailView):
    """The space card — the right-hand rail of the floor screen, not a screen of its own.

    The answer is a chunk of markup that HTMX puts into the rail: the plan stays on
    screen, and the spatial context that led the reader to the space is not spent on
    reading about it.
    """

    template_name = "building_passport/_space_card.html"
    context_object_name = "space"

    def get_queryset(self):
        """Another client's space answers 404 — the same checkpoint as the screens (ADR 0001)."""
        return Space.objects.visible_to(self.request.user).select_related("subtype")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Neighbours in the tree travel through the same checkpoint as the space
        # itself — and so does the one above it: walking `parent` directly would create
        # a second place where it is decided whose data to show (ADR 0001). Another
        # client's row must not reach the rail by name, just as it does not reach the
        # tree or the plan.
        visible = Space.objects.visible_to(self.request.user)
        context["children"] = visible.filter(parent=self.object).order_by("code", "name")
        parent_id = self.object.parent_id
        parent = visible.filter(pk=parent_id).first() if parent_id else None
        context["parent"] = parent
        # The floor above the space is named but does not open as a card: it is not a
        # node of the tree but the screen the rail itself stands on — a link would lead
        # where the reader already is.
        context["parent_is_a_space"] = parent is not None and parent.type != DictSpaceType.FLOOR
        return context


class FloorPlanSVGView(LoginRequiredMixin, View):
    """The drawing file — the same read path as the screens, not a door of its own.

    Serving it through nginx around the application would hand a client's drawing to
    anyone who knows the address: exactly the leak the checkpoint exists for (ADR
    0001). So the file travels through `visible_to`, and another client's plan answers
    404 rather than 403.
    """

    def get(self, request, pk):
        plan = get_object_or_404(FloorPlan.objects.visible_to(request.user), pk=pk)
        response = FileResponse(plan.file.open("rb"), content_type="image/svg+xml")
        # SVG is an executable format, and it is served from the application's own
        # domain: opened directly by its address it would run as one of our pages. The
        # sandbox strips it of our origin, and `nosniff` of the chance to call itself
        # another type.
        response["Content-Security-Policy"] = "sandbox"
        response["X-Content-Type-Options"] = "nosniff"
        return response
