"""Placeholders in the non-residential area and the number of rooms become NULL.

The list of fields in ticket #4 is closed, and `0015` did not go beyond it. But `-1`
remained in four more columns, and two of them — `non_residential_area` and
`total_rooms` — are not residential: the "we hide it while rendering" proviso that
covers living area and balconies does not extend to them, and an employee of the
management company would see `-1 м²` and `-1` on screen. Exactly what `0015` was written
for.

A separate migration rather than an edit to `0015`: that one has already been applied.

`living_area` and `balcony_loggia_area` are deliberately left alone — residential
property is out of context (CONTEXT.md, §Язык), and the BC card hides those fields.
"""

from decimal import Decimal

from django.db import migrations

# Field → the value in which the absence of data is recorded in it.
PLACEHOLDERS = {
    "non_residential_area": Decimal(-1),
    "total_rooms": -1,
}


def clear_remaining_placeholders(apps, schema_editor):
    BuildingPassport = apps.get_model("building_passport", "BuildingPassport")

    for field, placeholder in PLACEHOLDERS.items():
        BuildingPassport.objects.filter(**{field: placeholder}).update(**{field: None})


def keep_placeholders_cleared(apps, schema_editor):
    """The rollback leaves the NULLs in place — as in `0015`.

    There is nothing to tell a cleared placeholder from a field nobody ever filled in;
    the placeholder was not data, and restoring it would mean inventing a measurement
    anew.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("building_passport", "0015_clear_passport_placeholders"),
    ]

    operations = [
        migrations.RunPython(clear_remaining_placeholders, keep_placeholders_cleared),
    ]
