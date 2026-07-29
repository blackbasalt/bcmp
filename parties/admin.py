from django.contrib import admin

# Register your models here.
from .models import *

@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name","kind","bin_iin")
    list_filter = ("kind",)
    search_fields = ("name", "bin_iin")

admin.site.register(Org)
admin.site.register(PartyRole)
