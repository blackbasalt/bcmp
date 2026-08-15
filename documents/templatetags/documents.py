"""Template filters over the documents section's display rules.

The rules themselves are in `document_display`, because more than the markup uses them: the
document's page formats its dates in Python and the table formats the same dates in the
markup. The same arrangement as `passport`. What is defined here rather than registered is
about the markup alone.
"""

from django import template

from ..document_display import day

register = template.Library()

register.filter(day)


@register.filter
def styled(field, classes):
    """A form field rendered by its own widget, wearing the classes given in the markup.

    Two things have to hold at once, and hand-written `<input>`s cannot hold both. A date
    already stored has to come back into the field in the notation `type="date"` reads —
    printed by hand it arrives as «14 марта 2024 г.», and the browser, unable to read it,
    shows an empty field, so whoever came to fill in the номер saves the дата выдачи away.
    The widget knows the notation; the markup does not.

    And the classes have to stand in the template: Tailwind builds the stylesheet by
    scanning `templates/`, so a class name living in a Python widget would not be emitted
    at all and the field would come out unstyled. Hence they are passed in from the markup
    instead — the same reason `_messages.html` writes its alert classes out in full.
    """
    return field.as_widget(attrs={"class": classes})
