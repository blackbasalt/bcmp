"""Показ связанных документов в changelist любой сущности паспорта.

DocumentLink полиморфна и не имеет FK на цель: entity_type — текстовый код,
entity_id — UUID. GenericRelation и prefetch_related тут неприменимы (они
требуют ContentType), поэтому документы подтягиваются подзапросом в тот же
запрос, что и сам список: N+1 не возникает независимо от размера страницы.
"""

from django.contrib import admin
from django.db.models import Count, OuterRef, StringAgg, Subquery, Value
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import DocumentLink

SEP = "\u241f"  # разделитель, который не встретится в названии документа
EMPTY = mark_safe('<span style="color:#999">—</span>')


class LinkedDocumentsMixin:
    """Добавляет в список колонку с документами, привязанными к строке.

    Использование:

        @admin.register(Space)
        class SpaceAdmin(LinkedDocumentsMixin, admin.ModelAdmin):
            document_entity_type = "space"      # или оставить автоопределение
            list_display = ("code", "name", "documents")
    """

    #: код в DocumentLink.entity_type. По умолчанию — имя таблицы модели.
    document_entity_type = None
    #: сколько названий показывать в ячейке, остальные уходят в подсказку
    documents_preview = 2

    def get_document_entity_type(self):
        return self.document_entity_type or self.model._meta.db_table

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        links = (
            DocumentLink.objects
            .filter(entity_type=self.get_document_entity_type(), entity_id=OuterRef("pk"))
            .order_by()
            .values("entity_id")
        )
        return qs.annotate(
            documents_count=Subquery(
                links.annotate(n=Count("document_id")).values("n")
            ),
            documents_titles=Subquery(
                links.annotate(
                    t=StringAgg("document__title", Value(SEP), order_by="document__title")
                ).values("t")
            ),
        )

    @admin.display(description="Документы", ordering="documents_count")
    def documents(self, obj):
        count = obj.documents_count or 0
        if not count:
            return EMPTY

        titles = [t for t in (obj.documents_titles or "").split(SEP) if t]
        titles.sort()
        preview = titles[: self.documents_preview]
        tail = count - len(preview)

        url = "{}?links__entity_type={}&links__entity_id={}".format(
            reverse("admin:documents_document_changelist"),
            self.get_document_entity_type(),
            obj.pk,
        )
        label = ", ".join(preview)
        if tail > 0:
            label = f"{label} и ещё {tail}"
        return format_html(
            '<a href="{}" title="{}">{}</a> <span style="color:#999">({})</span>',
            url, "\n".join(titles), label, count,
        )

    @admin.display(description="Документы")
    def documents_detail(self, obj):
        """Для readonly_fields на странице объекта: список ссылок на документы."""
        links = (
            DocumentLink.objects
            .filter(entity_type=self.get_document_entity_type(), entity_id=obj.pk)
            .select_related("document")
            .order_by("document__kind", "document__title")
        )
        if not links:
            return "—"
        rows = []
        for link in links:
            doc = link.document
            href = reverse("admin:documents_document_change", args=[doc.pk])
            rows.append(
                format_html(
                    '<li><a href="{}">{}</a> <span style="color:#999">— {}{}</span></li>',
                    href, doc.title, doc.get_kind_display(),
                    format_html(", {}", link.role) if link.role else "",
                )
            )
        return format_html('<ul style="margin:0;padding-left:1em">{}</ul>', mark_safe("".join(rows)))


class DocumentLookupsMixin:
    """Разрешает DocumentAdmin фильтрацию по links__entity_type / links__entity_id.

    Без этого ссылка из колонки «Документы» упирается в DisallowedModelAdminLookup.
    """

    allowed_document_lookups = ("links__entity_type", "links__entity_id")

    def lookup_allowed(self, lookup, value, request=None):
        if lookup in self.allowed_document_lookups:
            return True
        return super().lookup_allowed(lookup, value, request)
