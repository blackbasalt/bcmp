"""What the documents section's tests are staged on.

The root `conftest` holds the organisations, the employees and the building — everything
the whole suite is staged on. What stands here belongs to the documents alone and is
needed by more than one of their screens: the shelf and a document's own page both name an
issuing party, and two definitions of one and the same «ТОО Промэнерго» would drift.
"""

import pytest

from parties.models import Party, PartyRecord


@pytest.fixture
def issuer(downtown):
    """The party that issued the document — the same as «кем выдан» in the table and on the page.

    On the УК's own shelf, because that is where «кем выдан» is now chosen from: a Сторона
    with nobody's учётная карточка is in the реестр and on no one's form (ADR 0020), and an
    issuing party staged without one would be a подрядчик this УК has never heard of.
    """
    party = Party.objects.create(kind=Party.Kind.COMPANY, name="ТОО Промэнерго")
    PartyRecord.objects.create(party=party, org=downtown)
    return party
