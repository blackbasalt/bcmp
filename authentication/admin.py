from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from parties.admin import MembershipsOfUserInline


class UserWithMembershipsAdmin(UserAdmin):
    """Доступы к организациям видны там же, где заводится пользователь."""
    inlines = [*UserAdmin.inlines, MembershipsOfUserInline]


admin.site.unregister(User)
admin.site.register(User, UserWithMembershipsAdmin)
