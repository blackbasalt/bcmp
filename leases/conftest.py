"""What the аренда tests are staged on.

The организации, the employees, Manhattan and its first floor come from the root
`conftest` — there must not be a second definition of one Manhattan. What stands here is
only what аренда needs: the помещения an аренда is staged on, the Стороны that sit in them,
and a factory for an аренда.

The помещения stand here rather than in one of the test modules because three of them ask
about the same two — the model, the block on the карточка and the form on it — and a
кабинет of 300 м² defined three times would drift into three different кабинеты.

The factory fills in a период that has begun and has not ended: almost every rule here is
about something other than the срок, and a test that had to name two dates before it could
say «two аренды on one помещение overlap» would bury the thing it is about.
"""

from datetime import date

import pytest

from leases.models import Lease
from parties.models import Party


@pytest.fixture
def alpha(db):
    """A юрлицо sitting in a помещение — the arendator of the УК's own table."""
    return Party.objects.create(
        kind=Party.Kind.COMPANY, name="ТОО «Альфа»", bin_iin="050340008889"
    )


@pytest.fixture
def petrov(db):
    """A физлицо: an ИП in the стрит-ритейл is not made to register a fictitious ТОО."""
    return Party.objects.create(kind=Party.Kind.PERSON, name="ИП Петров", bin_iin="770101300123")


@pytest.fixture
def make_lease(db):
    def _make_lease(space, tenant, valid_from=None, **fields):
        return Lease.objects.create(
            space=space,
            tenant=tenant,
            valid_from=date(2026, 1, 1) if valid_from is None else valid_from,
            **fields,
        )

    return _make_lease


@pytest.fixture
def kab305(first_floor, make_space):
    """An арендопригодное помещение of a known площадь — the ordinary subject of an аренда."""
    return make_space(
        first_floor, "man-f1-c", "каб305", area_m2=300, is_leasable=True, is_common=False
    )


@pytest.fixture
def lobby(first_floor, make_space):
    """A МОП: not let as a whole, and still holding a банкомат of two metres."""
    return make_space(
        first_floor, "man-f1-d", "Лобби", area_m2=500, is_leasable=False, is_common=True
    )
