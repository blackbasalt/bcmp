"""What the полка помещений's tests are staged on.

The root `conftest` holds the organisations, the employees and the two БЦ — everything the
whole suite is staged on, and there must not be two definitions of one Manhattan. What
stands here belongs to the полка alone: the назначения its conditions are asked by, which
no other screen puts a question about.
"""

import pytest

from dictionary.models import DictSpaceSubtype


@pytest.fixture
def toilet(db):
    """A назначение — «Санузел», the one «покажи все санузлы» is asked by."""
    return DictSpaceSubtype.objects.create(type="room", name="Санузел", short_name="Санузел")


@pytest.fixture
def office(db):
    """A second назначение, so that narrowing by one is telling it from another."""
    return DictSpaceSubtype.objects.create(type="room", name="Офис", short_name="Офис")

