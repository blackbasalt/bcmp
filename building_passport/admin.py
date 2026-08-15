from django.contrib import admin

# Register your models here.
from .models import *

from documents.admin_mixins import DocumentLookupsMixin, LinkedDocumentsMixin
from documents.admin_inlines import DocumentLinkInline

class SpaceDocumentsInline(DocumentLinkInline):
    entity_type = "space"

@admin.register(Space)
class SpaceAdmin(LinkedDocumentsMixin, admin.ModelAdmin):
    document_entity_type = "space"          # or auto-detection from db_table
    list_display = ("code","name","floor_number","type","subtype","parent","building","area_m2","is_common","is_leasable","documents")
    list_filter = ("type","floor_number",  "subtype", "is_common", "is_leasable")
    inlines = [SpaceDocumentsInline]

@admin.register(FloorPlan)
class FloorPlanAdmin(admin.ModelAdmin):
    """Until the upload form exists, plans are created here — by file and date, without geometry.

    Contours are never entered by hand at all: they appear from the parse together with
    the plan, so the admin shows them as a count and gives them no separate model to
    edit.
    """

    list_display = ("floor", "valid_from", "valid_to", "contour_count")
    list_filter = ("floor__building",)
    readonly_fields = ("view_box", "contour_count", "unmatched")

    def get_readonly_fields(self, request, obj=None):
        # The drawing has already been parsed, and the contours must not be rebuilt
        # (ADR 0003): a substituted file would silently drift from its own contours. A
        # new layout is a new plan.
        if obj is None:
            return self.readonly_fields
        return (*self.readonly_fields, "floor", "file")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "floor":
            kwargs["queryset"] = Space.objects.filter(type=DictSpaceType.FLOOR).order_by(
                "building__name", "floor_number"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="контуров")
    def contour_count(self, obj):
        return obj.contours.count()

    @admin.display(description="непривязанные пути")
    def unmatched(self, obj):
        """The `id`s of paths that found no space — right where the plan is created.

        The same is visible on the floor screen, but the drawing is fixed by whoever
        uploaded it, and they should discover the typo where they have just pressed
        "save".
        """
        return ", ".join(obj.unmatched_ids) or "—"


#admin.site.register(SpaceRequirement)
admin.site.register(BuildingPassport)
#admin.site.register(SpaceArea)
#admin.site.register(SpaceCodeHistory)
