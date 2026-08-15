"""Placeholders in the passports become NULL.

Five passports carry `-1` in the total area, the building footprint, the volume and the
number of apartments, an empty string in the floor count and `1900` in the year built —
values written as measurements but meaning "there is no data". The cleanup happens in
the database, not in the templates: hiding a placeholder while rendering means leaving
it to everyone who reads the data further on, the AI manager included.

The list of fields is exactly the one enumerated in the ticket. `living_area`,
`balcony_loggia_area`, `non_residential_area` and `total_rooms` carry `-1` too, but they
are not on that list and are not touched here.
"""

from decimal import Decimal

from django.db import migrations

PLACEHOLDER_MEASUREMENT = Decimal(-1)
PLACEHOLDER_COUNT = -1
PLACEHOLDER_YEAR = 1900

# Field → the value in which the absence of data is recorded in it.
PLACEHOLDERS = {
    "total_area": PLACEHOLDER_MEASUREMENT,
    "building_footprint": PLACEHOLDER_MEASUREMENT,
    "building_volume": PLACEHOLDER_MEASUREMENT,
    "number_of_floors": "",
    "apartments_number": PLACEHOLDER_COUNT,
}


def clear_placeholders(apps, schema_editor):
    BuildingPassport = apps.get_model("building_passport", "BuildingPassport")

    # The year is cleared only where the total area is a placeholder too, and strictly
    # before that one becomes NULL. An unconditional rule would erase 1900 from a
    # genuinely old building on any subsequent run.
    BuildingPassport.objects.filter(
        total_area=PLACEHOLDER_MEASUREMENT, year_built=PLACEHOLDER_YEAR
    ).update(year_built=None)

    for field, placeholder in PLACEHOLDERS.items():
        BuildingPassport.objects.filter(**{field: placeholder}).update(**{field: None})


def keep_placeholders_cleared(apps, schema_editor):
    """The rollback leaves the NULLs in place.

    Restoring `-1` would only be possible for every empty field at once — there is
    nothing to tell a cleared placeholder from a field nobody ever filled in. The
    placeholder was not data, and restoring it would mean inventing a measurement anew.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("building_passport", "0014_alter_buildingpassport_balcony_loggia_area_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_placeholders, keep_placeholders_cleared),
    ]
