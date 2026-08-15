from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from parties.admin import MembershipsOfUserInline


class UserWithMembershipsAdmin(UserAdmin):
    """Access to organisations is visible in the same place where the user is created."""
    inlines = [*UserAdmin.inlines, MembershipsOfUserInline]


admin.site.unregister(User)
admin.site.register(User, UserWithMembershipsAdmin)
