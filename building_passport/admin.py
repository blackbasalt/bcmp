from django.contrib import admin

# Register your models here.
from .models import *

admin.site.register(Space)
admin.site.register(SpaceRequirement)
admin.site.register(BuildingPassport)
admin.site.register(SpaceArea)
admin.site.register(SpaceCodeHistory)
