"""Template filters over the passport display rules.

Only the registration lives here: the rules themselves are in `passport_display`,
because more than the markup uses them. What gets registered is what is called from a
template — quantities assembled in Python reach the screen already formatted.

What is *defined* here rather than registered is about the markup alone, and `styled` is
the one such thing: it renders a form field and has no reader outside a template.
"""

from django import template

from ..passport_display import area, or_missing, space_label

register = template.Library()

register.filter(or_missing)
register.filter(area)
register.filter(space_label)


@register.filter
def styled(field, classes):
    """A form field rendered by its own widget, wearing the classes given in the markup.

    Two things have to hold at once, and hand-written `<input>`s cannot hold both. A value
    already stored has to come back into the field in the notation that field reads — a date
    printed by hand arrives as «14 марта 2024 г.» and a площадь as «40,00», neither of which
    `type="date"` and `type="number"` can read, so both fields come up empty and are saved
    away by whoever opened the form to change something else. The widget knows the notation;
    the markup does not.

    And the classes have to stand in the template: Tailwind builds the stylesheet by
    scanning `templates/`, so a class name living in a Python widget would not be emitted
    at all and the field would come out unstyled. Hence they are passed in from the markup
    instead — the same reason `_messages.html` writes its alert classes out in full.

    It stands in `passport` rather than in one section's library because it is about forms
    rather than about a section: the реквизиты документа and the правка аренды render their
    fields alike.
    """
    return field.as_widget(attrs={"class": classes})
