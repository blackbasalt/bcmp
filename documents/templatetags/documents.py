"""Template filters over the documents section's display rules.

The rules themselves are in `document_display`, because more than the markup uses them: the
document's page formats its dates in Python and the table formats the same dates in the
markup. The same arrangement as `passport`.
"""

from django import template

from ..document_display import day

register = template.Library()

register.filter(day)
