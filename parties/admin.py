from django.contrib import admin

# Register your models here.
from .models import *

@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name","kind","bin_iin")
    list_filter = ("kind",)
    search_fields = ("name", "bin_iin")


class MembershipsOfUserInline(admin.TabularInline):
    """The organisations the user is admitted to."""
    model = OrgMembership
    fk_name = "user"  # CommonModel adds created_by/updated_by pointing at the same User
    extra = 1
    autocomplete_fields = ("org",)
    verbose_name = "доступ к организации"
    verbose_name_plural = "доступы к организациям"


class MembersOfOrgInline(admin.TabularInline):
    """The users admitted to the organisation."""
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
    """This is where the platform administrator grants administratorship (ADR 0005).

    The right sits on the membership, that is, on the pair "employee + organisation", so
    the list is filtered by both: the question "who maintains this client's data" is asked
    both from the organisation's side and from the user's.
    """

    list_display = ("user", "org", "is_admin")
    list_filter = ("org", "is_admin")
    search_fields = ("user__username", "org__party__name")
    autocomplete_fields = ("org",)


admin.site.register(PartyRole)


class ContactsOfRecordInline(admin.TabularInline):
    """Контактные лица — внутри карточки, потому что нигде больше они не существуют."""

    model = ContactPerson
    extra = 1


class PaymentDetailsOfRecordInline(admin.TabularInline):
    """Платёжные реквизиты — там же и по той же причине."""

    model = PaymentDetails
    extra = 1
    # Банков в справочнике под восемьсот: их ищут, а не прокручивают.
    autocomplete_fields = ("bank",)


@admin.register(PartyRecord)
class PartyRecordAdmin(admin.ModelAdmin):
    """Пока полки Сторон нет, учётная карточка ведётся здесь.

    Отказ во второй карточке на ту же пару — тот же, что получит скрипт: ограничение стоит
    в базе, а форма называет его словами, а не роняет страницу. Названо оно поверх формы, а
    не у поля: ни «Сторона», ни «Организация» по отдельности не виноваты — виновата пара.
    """

    list_display = ("party", "org", "born_on")
    list_filter = ("org",)
    search_fields = ("party__name", "party__bin_iin")
    # Сторону выбирают из реестра всей системы, а не из списка: их 699.
    autocomplete_fields = ("party", "org")
    inlines = [ContactsOfRecordInline, PaymentDetailsOfRecordInline]
