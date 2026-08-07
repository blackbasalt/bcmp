"""Карточка БЦ — пока только доступ к ней.

Сам экран паспорта — следующий тикет; здесь закрепляется то, что появилось вместе
со ссылкой с карточки списка: адрес БЦ читается через тот же чокпоинт, и чужой БЦ
отвечает как несуществующий (ADR 0001). Фильтрация пишется вместе с представлением,
а не дописывается к готовому запросу потом.
"""

import pytest
from django.urls import reverse

from building_passport.models import Space
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(django_user_model, downtown):
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


def open_bc(client, building):
    return client.get(reverse("building_passport:bc_detail", args=[building.pk]))


def test_a_member_opens_a_building_of_their_own_organisation(client, member, downtown):
    ours = Space.objects.create(org=downtown, type="building", code="man", name="Manhattan")
    client.force_login(member)

    assert open_bc(client, ours).status_code == 200


def test_a_building_of_another_organisation_is_missing_rather_than_forbidden(
    client, member, central
):
    """403 подтвердил бы, что такой БЦ есть у другого клиента."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    client.force_login(member)

    assert open_bc(client, theirs).status_code == 404
