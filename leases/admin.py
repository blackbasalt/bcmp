"""Пока экранов аренды нет, договоры заводятся здесь — договором с предметами сразу."""

from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from building_passport.models import Space
from documents.admin_inlines import DocumentLinkInline

from .models import Lease, LeaseSubject


class LeaseSubjectFormSet(BaseInlineFormSet):
    """Предметы проверяются против договора, который в базу ещё не попал.

    Инлайн валидируется раньше, чем сохранён родитель, и спросить договор по
    ссылке в этот момент нечем — админка вдобавок обнуляет его ключ, пока он не
    записан. Строки бы прошли проверку, а отказ пришёл бы уже из `save()`:
    пятисоткой вместо сообщения у поля. Договор передаётся прямо объектом, тем
    самым, который админка держит в руках.
    """

    default_error_messages = {
        "too_few_forms": "Договор без предмета не бывает: назовите хотя бы одно помещение.",
    }

    def _construct_form(self, index, **kwargs):
        form = super()._construct_form(index, **kwargs)
        form.instance.lease = self.instance
        return form


class LeaseSubjectInline(admin.TabularInline):
    """Предмет договора: помещение, ставка и договорная площадь.

    Договор без предмета не договор — сдавать нечего и красить на плане нечего,
    поэтому одна строка обязательна.
    """

    model = LeaseSubject
    formset = LeaseSubjectFormSet
    extra = 1
    min_num = 1
    verbose_name = "предмет"
    verbose_name_plural = "Предметы договора"

    def get_formset(self, request, obj=None, **kwargs):
        # `min_num` сам по себе только рисует строку: без `validate_min` пустой
        # формсет проходит, и договор сохраняется без единого помещения. Админка
        # этот флаг не передаёт, поэтому он идёт отсюда.
        return super().get_formset(request, obj, validate_min=True, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Выбирать можно только из арендопригодных: венткамера не должна попадать
        # в список вовсе. Отказ на модели при этом остаётся — он ловит скрипты и
        # будущую форму, а не только промах в выпадающем списке.
        if db_field.name == "space":
            kwargs["queryset"] = Space.objects.filter(is_leasable=True).order_by(
                "building__name", "floor_number", "code"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class LeaseDocumentsInline(DocumentLinkInline):
    """Скан договора подшивается к самому договору, а не заменяет его (ADR 0006)."""

    entity_type = "lease"


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("__str__", "org", "tenant", "valid_from", "valid_to", "subject_count")
    list_filter = ("org",)
    search_fields = ("number", "tenant__name")
    autocomplete_fields = ("tenant",)
    inlines = [LeaseSubjectInline, LeaseDocumentsInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("org__party", "tenant")

    @admin.display(description="помещений")
    def subject_count(self, obj):
        return obj.subjects.count()
