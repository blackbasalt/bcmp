"""The floor plan upload form — the first write path outside the Django admin.

It asks for exactly two things: the file of the drawing and the date from which the
layout is in force. Contours are not entered on the form — they are taken from the paths
of the file while parsing (ADR 0003) — and the system does not derive the dates: the day
of a rebuild is known to whoever commissioned it (ADR 0004).

The form has no checks of its own. The plan itself parses the file and verifies the
periods: the rule stands on the model, so the admin, this form and code all get the same
rejection, and the reason is the very same phrase. The form is left to show it next to
the field.
"""

from django import forms

from .models import FloorPlan


class FloorPlanForm(forms.ModelForm):
    """A file and a date. The floor comes from the screen the form stands on, not from a field.

    The floor is chosen by the same address the screen was opened at, and the form
    cannot substitute another one: the right to upload is checked on that floor, and a
    field in the markup would put a second answer to the question "where to" alongside.
    """

    class Meta:
        model = FloorPlan
        fields = ("file", "valid_from")
        labels = {
            "file": "Файл SVG",
            # Not "the upload date": a plan records when the building changed, not when
            # someone finally got round to the drawing.
            "valid_from": "Планировка действует с",
        }

    def __init__(self, *args, floor, **kwargs):
        super().__init__(*args, **kwargs)
        # The date deliberately has no default: a pre-filled today would be accepted
        # without a glance, and the rebuild would be recorded on an administrative day
        # (ADR 0004).
        self.instance.floor = floor
