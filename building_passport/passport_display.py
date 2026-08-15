"""How the building passport reads on screen.

A missing value is written as "— нет данных" — the same way everywhere a passport field
is empty: blank space can be read as a zero, a dash cannot. The rule lives here rather
than in template filters: it is used both by the markup and by the breakdown of the
passport into sections, where an empty section is hidden by the same test.
"""

#: A non-breaking space: "2 484 м²" must not be wrapped across lines.
NBSP = "\u00a0"

NO_DATA = "— нет данных"


def is_missing(value) -> bool:
    """There is no passport value. Zero is a value; an empty string is not."""
    return value is None or value == ""


def or_missing(value):
    """An empty passport value reads as "— нет данных"."""
    return NO_DATA if is_missing(value) else value


def space_label(space):
    """How a space is named on screen: its name, or its code when there is no name.

    The code is an accounting identifier, but it is the only thing telling a nameless
    space from the one next to it, so it stands in for the name instead of a dash.
    """
    return or_missing(space.name or space.code)


def measure(value, unit):
    """A quantity with its unit — to hundredths, unrounded, with non-breaking spaces.

    A missing quantity stays None: `or_missing` will format it.
    """
    if is_missing(value):
        return None
    return f"{value:,.2f}{NBSP}{unit}".replace(",", NBSP).replace(".", ",")


def area(value):
    """An area in m² exactly as it is recorded in the passport."""
    return measure(value, "м²")


def volume(value):
    """A building volume in m³ — the same notation as for areas."""
    return measure(value, "м³")
