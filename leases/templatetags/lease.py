"""Template filters over the аренда display rules.

Only the registration lives here: the rules are in `lease_display`, because the карточка is
not the only reader of them — the полка помещений names the same things in its own column —
and the one about the складка is in `lease_edit`, where правка and удаление live.
"""

from django import template

from ..lease_display import (
    fold_title,
    lease_area,
    lease_rate,
    lease_term,
    occupancy_line,
)
from ..lease_edit import fold_stands_open

register = template.Library()

register.filter(lease_area)
register.filter(lease_rate)
register.filter(lease_term)
register.filter(occupancy_line)
register.filter(fold_title)
register.filter(fold_stands_open)
