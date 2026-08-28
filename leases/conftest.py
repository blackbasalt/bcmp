"""What the аренда tests are staged on.

The организации, the employees, Manhattan and its first floor come from the root
`conftest` — there must not be a second definition of one Manhattan. What stands here is
only what аренда needs: the Стороны that sit in the помещения, and a factory for an
аренда.

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
