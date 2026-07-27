from django.contrib import admin

# Register your models here.
from .models import *

admin.site.register(Party)
admin.site.register(Org)
admin.site.register(PartyRole)
