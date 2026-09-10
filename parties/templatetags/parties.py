"""Template filters over the полка Сторон's display rules.

The rules themselves are in `party_display`, because more than the markup uses them — and
what is counted is worked out in `leases.occupancy`, where «действующая на день» is settled.
The same arrangement as `passport`, `documents` and `rooms`.
"""

from django import template

from ..party_display import rooms_rented

register = template.Library()


@register.filter
def rents(record):
    """What the «Арендует» column says about one учётная карточка.

    A filter and not a column assembled beside the queryset: the number is already on the row
    — `occupancy.rooms_of_each_record` put it there in the same query as the rows — and a
    value built next to them would be a second thing to keep in step with the rows it
    describes.
    """
    return rooms_rented(record.rooms_rented)
