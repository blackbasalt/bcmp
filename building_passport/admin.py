from django.contrib import admin

# Register your models here.
from .models import *

from documents.admin_mixins import DocumentLookupsMixin, LinkedDocumentsMixin
from documents.admin_inlines import DocumentLinkInline

class SpaceDocumentsInline(DocumentLinkInline):
    entity_type = "space"

@admin.register(Space)
class SpaceAdmin(LinkedDocumentsMixin, admin.ModelAdmin):
    document_entity_type = "space"          # или автоопределение по db_table
    list_display = ("code","name","floor_number","type","subtype","parent","building","area_m2","is_common","is_leasable","documents")
    list_filter = ("type","floor_number",  "subtype", "is_common", "is_leasable")
    inlines = [SpaceDocumentsInline]

@admin.register(FloorPlan)
class FloorPlanAdmin(admin.ModelAdmin):
    """Пока формы загрузки нет, планы заводятся здесь — файлом и датой, без геометрии.

    Контуры руками не заводятся вовсе: они появляются разбором вместе с планом,
    поэтому в админке их видно числом, а отдельной модели для правки у них нет.
    """

    list_display = ("floor", "valid_from", "valid_to", "contour_count")
    list_filter = ("floor__building",)
    readonly_fields = ("view_box", "contour_count")

    def get_readonly_fields(self, request, obj=None):
        # Чертёж уже разобран, и контуры пересобирать нельзя (ADR 0003): подменённый
        # файл разошёлся бы со своими контурами молча. Новая планировка — новый план.
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


#admin.site.register(SpaceRequirement)
admin.site.register(BuildingPassport)
#admin.site.register(SpaceArea)
#admin.site.register(SpaceCodeHistory)
