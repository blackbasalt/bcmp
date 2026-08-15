"""Template filters over the passport display rules.

Only the registration lives here: the rules themselves are in `passport_display`,
because more than the markup uses them. What gets registered is what is called from a
template — quantities assembled in Python reach the screen already formatted.
"""

from django import template

from ..passport_display import area, or_missing, space_label

register = template.Library()

register.filter(or_missing)
register.filter(area)
register.filter(space_label)
