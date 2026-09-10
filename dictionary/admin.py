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


@admin.register(DictBank)
class DictBankAdmin(admin.ModelAdmin):
    """Банк ищут по БИК и по названию: платёжные реквизиты выбирают его из семисот строк.

    Поиск здесь стоит не для удобства этой страницы, а потому что комплект платёжных
    реквизитов ссылается на банк полем с автодополнением, а оно спрашивает поиск у той
    админки, на которую указывает.
    """

    list_display = ("name", "code")
    search_fields = ("name", "short_name", "code")


admin.site.register(DictLineOfBusiness)
admin.site.register(DictProfessionalHoliday)
#admin.site.register()
