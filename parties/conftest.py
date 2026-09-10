"""What the полка Сторон's tests are staged on.

The root `conftest` holds the organisations, the employees and the Стороны that sit in
помещения — ТОО «Альфа» and ИП Петров are the pair every screen of this stage is read
through, and there must not be two definitions of either. What stands here belongs to the
раздел «Стороны» alone: the учётная карточка that puts a Сторона on the полка at all, and
the сфера деятельности a row names.
"""

import pytest

from dictionary.models import DictLineOfBusiness
from parties.models import Party, PartyRecord


@pytest.fixture
def make_record(db):
    """The учётная карточка that puts a Сторона on an organisation's полка.

    A factory rather than a ready-made карточка: the полка is a полка карточек, and what
    almost every test here stages is which pair «Сторона + организация» exists and which
    does not.
    """

    def _make_record(org, party, **fields):
        return PartyRecord.objects.create(party=party, org=org, **fields)

    return _make_record


@pytest.fixture
def make_party(db):
    """A Сторона of the registry — with or without anybody's карточка on her.

    The 62 Стороны loaded from other bases are exactly this: rows of the registry that no
    организация knows, and the полка has to keep them off itself.
    """

    def _make_party(name, bin_iin, kind=Party.Kind.COMPANY, **fields):
        return Party.objects.create(kind=kind, name=name, bin_iin=bin_iin, **fields)

    return _make_party


@pytest.fixture
def construction(db):
    """A сфера деятельности — the one «все наши строители» is asked by."""
    return DictLineOfBusiness.objects.create(name="Строительство", short_name="Строительство")


@pytest.fixture
def catering(db):
    """A second сфера, so that narrowing by one is telling it from another.

    Общепит and not a second building trade: the отбор is checked by what it leaves off the
    полка, and two сферы a reader could confuse would make a passing test out of a condition
    that answers with everybody who has any сфера at all.
    """
    return DictLineOfBusiness.objects.create(name="Общепит", short_name="Общепит")
