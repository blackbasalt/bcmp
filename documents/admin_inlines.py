from functools import partial

from django.contrib import admin
from django.contrib.admin.checks import InlineModelAdminChecks
from django.contrib.admin.utils import flatten_fieldsets
from django.forms.models import BaseModelFormSet, modelformset_factory

from .models import Document, DocumentLink


class DocumentLinkFormSet(BaseModelFormSet):
    """A formset bound to an arbitrary object without an FK to it."""

    entity_type = None

    def __init__(self, *args, instance=None, queryset=None, save_as_new=False, **kwargs):
        # the admin passes save_as_new to every inline; for a copy of an object the links
        # are created afresh, so resetting the ids of the existing forms is enough
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
    """Disables admin.E202: there is no FK to the parent here, and there will not be one."""

    def _check_relation(self, obj, parent_model):
        return []


class DocumentLinkInline(admin.TabularInline):
    """The "Документы" inline for any passport entity.

        class SpaceDocumentsInline(DocumentLinkInline):
            entity_type = "space"

        @admin.register(Space)
        class SpaceAdmin(admin.ModelAdmin):
            inlines = [SpaceDocumentsInline]

    Requires search_fields on DocumentAdmin — otherwise autocomplete will not work.
    """

    model = DocumentLink
    formset = DocumentLinkFormSet
    checks_class = PolymorphicInlineChecks
    fields = ("document", "role")
    autocomplete_fields = ["document"]
    extra = 1
    verbose_name = "документ"
    verbose_name_plural = "Документы"

    #: the code in DocumentLink.entity_type; defaults to the parent's table name
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
            # without this, autocomplete_fields and the admin's widgets are not applied
            "formfield_callback": partial(self.formfield_for_dbfield, request=request),
            **kwargs,
        }
        formset = modelformset_factory(DocumentLink, **defaults)
        formset.entity_type = self.get_entity_type(self.parent_model)
        return formset

    def get_queryset(self, request):
        # filtering by the specific object is done in the formset,
        # here it is enough to cut off other entity types
        qs = super().get_queryset(request)
        return qs.filter(entity_type=self.get_entity_type(self.parent_model))


# ── From the document's side: what it is attached to ────────────────────────────────

class ReverseDocumentLinkInline(admin.TabularInline):
    """An inline on the document page: it shows the links; adding through them is awkward —
    entity_id would have to be typed in as a UUID by hand. Hence read-only."""

    model = DocumentLink
    fields = ("entity_type", "entity_id", "role")
    readonly_fields = fields
    extra = 0
    can_delete = True
    verbose_name = "привязка"
    verbose_name_plural = "Привязан к объектам"

    def has_add_permission(self, request, obj=None):
        return False
