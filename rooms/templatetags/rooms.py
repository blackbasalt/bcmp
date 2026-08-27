"""Template filters over the полка's display rules.

The rules themselves are in `room_display` and in `building_passport.space_kind`, because
more than the markup uses them: the вид in a column and the вид as a condition of the отбор
are one rule, and the отбор reads it from Python. The same arrangement as `passport` and
`documents`.
"""

from django import template

from building_passport import space_kind
from building_passport.passport_display import space_label
from dictionary.models import DictSpaceType

from ..room_display import NAME_OF

register = template.Library()


@register.filter
def kind(room):
    """The вид of a помещение, as the полка names it.

    A filter and not a column computed in the view: вид is read off two flags the row
    already carries, so it costs nothing per row, and a value assembled beside the queryset
    would be a second thing to keep in step with the rows it describes.
    """
    return NAME_OF[space_kind.kind_of(room)]


@register.filter
def inside(room):
    """The помещение this one sits inside, or nothing when it lies straight on the этаж.

    Nothing, and not a dash: the полка unwove a tree into a flat table, and a помещение
    directly on the этаж is not a row with a gap in it — it is a row about the ordinary
    case. The dash is for data that should be there and is not.
    """
    parent = room.parent
    if parent is None or parent.type != DictSpaceType.ROOM:
        return ""
    # Named by the project's one rule for naming a space, so that the same помещение reads
    # the same way in this cell, in the tree on the этаж and in the row of its own.
    return space_label(parent)
