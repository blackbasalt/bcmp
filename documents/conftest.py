"""What the documents section's tests are staged on.

The root `conftest` holds the organisations, the employees and the building — everything
the whole suite is staged on. What stands here belongs to the documents alone and is
needed by more than one of their screens: the shelf and a document's own page both name an
issuing party, and two definitions of one and the same «ТОО Промэнерго» would drift.
"""

import pytest

from parties.models import Party


@pytest.fixture
def issuer(db):
    """The party that issued the document — the same as «кем выдан» in the table and on the page."""
    return Party.objects.create(kind=Party.Kind.COMPANY, name="ТОО Промэнерго")
