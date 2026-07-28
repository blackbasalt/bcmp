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

#admin.site.register(SpaceRequirement)
admin.site.register(BuildingPassport)
#admin.site.register(SpaceArea)
#admin.site.register(SpaceCodeHistory)
