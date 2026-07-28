from functools import partial

from django.contrib import admin
from django.contrib.admin.checks import InlineModelAdminChecks
from django.contrib.admin.utils import flatten_fieldsets
from django.forms.models import BaseModelFormSet, modelformset_factory

from .models import Document, DocumentLink


class DocumentLinkFormSet(BaseModelFormSet):
    """Формсет, привязанный к произвольному объекту без FK на него."""

    entity_type = None

    def __init__(self, *args, instance=None, queryset=None, save_as_new=False, **kwargs):
        # save_as_new админка передаёт всем инлайнам; для копии объекта связи
        # создаются заново, поэтому достаточно сбросить id существующих форм
        self.save_as_new = save_as_new
        self.instance = instance
        qs = queryset if queryset is not None else DocumentLink.objects.all()
        if instance is not None and instance.pk:
            qs = qs.filter(entity_type=self.entity_type, entity_id=instance.pk)
        else:
            qs = qs.none()
        super().__init__(*args, queryset=qs.select_related("document"), **kwargs)

    def _stamp(self, obj):
        obj.entity_type = self.entity_type
        obj.entity_id = self.instance.pk
        return obj

    def save_new(self, form, commit=True):
        obj = self._stamp(super().save_new(form, commit=False))
        if commit:
            obj.save()
        return obj

    def save_existing(self, form, obj, commit=True):
        obj = self._stamp(super().save_existing(form, obj, commit=False))
        if commit:
            obj.save()
        return obj


class PolymorphicInlineChecks(InlineModelAdminChecks):
    """Отключает admin.E202: FK на родителя тут нет и не будет."""

    def _check_relation(self, obj, parent_model):
        return []


class DocumentLinkInline(admin.TabularInline):
    """Инлайн «Документы» для любой сущности паспорта.

        class SpaceDocumentsInline(DocumentLinkInline):
            entity_type = "space"

        @admin.register(Space)
        class SpaceAdmin(admin.ModelAdmin):
            inlines = [SpaceDocumentsInline]

    Требует search_fields в DocumentAdmin — иначе autocomplete не заработает.
    """

    model = DocumentLink
    formset = DocumentLinkFormSet
    checks_class = PolymorphicInlineChecks
    fields = ("document", "role")
    autocomplete_fields = ["document"]
    extra = 1
    verbose_name = "документ"
    verbose_name_plural = "Документы"

    #: код в DocumentLink.entity_type; по умолчанию — имя таблицы родителя
    entity_type = None

    def get_entity_type(self, parent_model):
        return self.entity_type or parent_model._meta.db_table

    def get_formset(self, request, obj=None, **kwargs):
        if self.get_fieldsets(request, obj):
            fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        else:
            fields = None
        defaults = {
            "form": self.form,
            "formset": self.formset,
            "fields": fields,
            "extra": self.get_extra(request, obj),
            "min_num": self.get_min_num(request, obj),
            "max_num": self.get_max_num(request, obj),
            "can_delete": self.has_delete_permission(request, obj),
            # без этого autocomplete_fields и виджеты админки не применяются
            "formfield_callback": partial(self.formfield_for_dbfield, request=request),
            **kwargs,
        }
        formset = modelformset_factory(DocumentLink, **defaults)
        formset.entity_type = self.get_entity_type(self.parent_model)
        return formset

    def get_queryset(self, request):
        # фильтрация по конкретному объекту делается в формсете,
        # здесь достаточно отсечь чужие типы сущностей
        qs = super().get_queryset(request)
        return qs.filter(entity_type=self.get_entity_type(self.parent_model))


# ── Со стороны документа: к чему он прикреплён ───────────────────────────────────────

class ReverseDocumentLinkInline(admin.TabularInline):
    """Инлайн на странице документа: показывает привязки, добавлять ими неудобно —
    entity_id пришлось бы вводить UUID руками. Поэтому только чтение."""

    model = DocumentLink
    fields = ("entity_type", "entity_id", "role")
    readonly_fields = fields
    extra = 0
    can_delete = True
    verbose_name = "привязка"
    verbose_name_plural = "Привязан к объектам"

    def has_add_permission(self, request, obj=None):
        return False
