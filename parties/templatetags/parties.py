"""Template filters over the полка Сторон's display rules.

The rules themselves are in `party_display`, because more than the markup uses them — and
what is counted is worked out in `leases.occupancy`, where «действующая на день» is settled.
The same arrangement as `passport`, `documents` and `rooms`.
"""

from django import template

from ..party_display import NOTHING, day, nearest_occasion, rooms_rented

register = template.Library()

#: Дата, как её читают в этом разделе. Регистрируется, а не пишется фильтром `date` в
#: разметке: строка контактного лица печатает день рождения сама, а шапка и повод приходят
#: уже написанными, и написание у всех трёх должно быть одно.
register.filter(day)


@register.filter
def rents(record):
    """What the «Арендует» column says about one учётная карточка.

    A filter and not a column assembled beside the queryset: the number is already on the row
    — `occupancy.rooms_of_each_record` put it there in the same query as the rows — and a
    value built next to them would be a second thing to keep in step with the rows it
    describes.
    """
    return rooms_rented(record.rooms_rented)


@register.filter
def occasion(record):
    """What the «Ближайший повод» column says about one учётная карточка.

    A filter and not a column assembled beside the queryset, for the reason `rents` is one:
    the повод is already on the row — the screen put it there once for the whole полка — and
    a value built next to the rows would be a second thing to keep in step with them.
    """
    return nearest_occasion(record.nearest_occasion)


@register.simple_tag
def nothing():
    """Прочерк там, где ответ — «ничего», а не «неизвестно».

    Тегом, а не строкой в разметке: тот же прочерк стоит в двух колонках полки, и написанный
    в шаблоне отдельно он однажды разошёлся бы с ними. И именно он, а не `or_missing`'s «нет
    данных»: 637 из 699 Сторон — поставщики, которым дня рождения никто не заводил, и это
    ответ, а не пробел в записи.
    """
    return NOTHING
