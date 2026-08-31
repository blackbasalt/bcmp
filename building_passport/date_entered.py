"""Дата, набираемая в поле даты, — одинаково во всех формах проекта.

The browser's own picker writes `2024-03-14`, and a field has to be told both to read and to
show that. Left to the locale, a date already stored comes back into the form as «14 марта
2024 г.», the browser cannot read it, and the field arrives empty — so whoever opened the
form to correct one thing saves the date away with it.

It stands in a module of its own, and in `building_passport` rather than beside either of
its callers, for the same reason `period` does: two forms in two apps read a stored date
back into `type="date"` — the реквизиты документа and the правка аренды — and a second copy
of the widget would be a second answer to how a date is typed, with one of the two left
unfixed the day the answer changes.
"""

from django import forms


class DateEntered(forms.DateInput):
    """A date typed into a date field, not into a line of free text.

    The notation is fixed rather than localised: it is what `type="date"` submits and what
    it reads back, and it never reaches a reader's eye — the browser draws the date in
    whatever notation the reader's own machine uses.
    """

    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)
