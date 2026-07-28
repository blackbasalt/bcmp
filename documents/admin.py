from django.contrib import admin

# Register your models here.
from .models import *

from .admin_mixins import DocumentLookupsMixin, LinkedDocumentsMixin

@admin.register(Document)
class DocumentAdmin(DocumentLookupsMixin, admin.ModelAdmin):
    list_display = ("kind","title")
    search_fields = ("title", "doc_no")


admin.site.register(DocumentLink)
