from django.contrib import admin

# Register your models here.
from .models import *

@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name","kind","bin_iin")
    list_filter = ("kind",)
    search_fields = ("name", "bin_iin")


class MembershipsOfUserInline(admin.TabularInline):
    """Организации, к которым допущен пользователь."""
    model = OrgMembership
    fk_name = "user"  # CommonModel добавляет created_by/updated_by на того же User
    extra = 1
    autocomplete_fields = ("org",)
    verbose_name = "доступ к организации"
    verbose_name_plural = "доступы к организациям"


class MembersOfOrgInline(admin.TabularInline):
    """Пользователи, допущенные к организации."""
    model = OrgMembership
    fk_name = "org"
    extra = 1
    verbose_name = "сотрудник"
    verbose_name_plural = "сотрудники"


@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "plan")
    list_filter = ("is_active",)
    search_fields = ("party__name", "party__bin_iin")
    autocomplete_fields = ("party",)
    inlines = [MembersOfOrgInline]


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    """Здесь администратор платформы и выдаёт администраторство (ADR 0005).

    Право стоит на членстве, то есть на паре «сотрудник + организация», поэтому и
    список фильтруется обоими: вопрос «кто ведёт данные этого клиента» задают и от
    организации, и от пользователя.
    """

    list_display = ("user", "org", "is_admin")
    list_filter = ("org", "is_admin")
    search_fields = ("user__username", "org__party__name")
    autocomplete_fields = ("org",)


admin.site.register(PartyRole)
