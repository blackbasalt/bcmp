"""Организации, над которыми ставятся тесты изоляции клиентов."""

import pytest

from parties.models import Org, Party


@pytest.fixture
def make_org(db):
    def _make_org(name, bin_iin):
        party = Party.objects.create(kind=Party.Kind.COMPANY, name=name, bin_iin=bin_iin)
        return Org.objects.create(party=party)

    return _make_org


@pytest.fixture
def downtown(make_org):
    """Организация существующих пяти БЦ."""
    return make_org("DownTown Management ТОО", "180540035878")


@pytest.fixture
def central(make_org):
    """Второй клиент — его данные не должны попадать к первому."""
    return make_org("Central City Properties ТОО", "201140031473")
