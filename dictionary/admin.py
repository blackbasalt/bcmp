from django.contrib import admin

# Register your models here.
from .models import *

admin.site.register(DictSystem)
admin.site.register(DictBuilding)
admin.site.register(DictSpaceSubtype)
admin.site.register(DictRequirementCode)
admin.site.register(DictAreaKind)
admin.site.register(DictSpaceRelationKind)
admin.site.register(DictSpaceStatus)
admin.site.register(DictZoneKind)
admin.site.register(DictAssetRelationKind)
admin.site.register(DictElementCategory)
admin.site.register(DictConditionGrade)
admin.site.register(DictDocumentRole)
#admin.site.register()
