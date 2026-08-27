"""What the полка помещений's tests are staged on.

The root `conftest` holds the organisations, the employees and Manhattan with its first
floor — everything the whole suite is staged on, and there must not be two definitions of
one Manhattan. What stands here belongs to the полка alone: the полка spans the portfolio,
so it needs a second БЦ with an этаж of its own, which no other screen has any use for.
"""

import pytest

from dictionary.models import DictSpaceSubtype


@pytest.fixture
def tokyo(downtown, make_building, make_floor):
    """A second БЦ of the same client, with a third floor.

    The полка is the first screen that shows two buildings' помещения in one table, and
    «санузлы Tokyo на третьем этаже» is the question it exists for. Its name sorts after
    Manhattan's, so the fixed order БЦ → этаж → код is observable.
    """
    building = make_building(downtown, "tok", "Tokyo")
    make_floor(building, 3)
    return building


@pytest.fixture
def toilet(db):
    """A назначение — «Санузел», the one «покажи все санузлы» is asked by."""
    return DictSpaceSubtype.objects.create(type="room", name="Санузел", short_name="Санузел")


@pytest.fixture
def office(db):
    """A second назначение, so that narrowing by one is telling it from another."""
    return DictSpaceSubtype.objects.create(type="room", name="Офис", short_name="Офис")

