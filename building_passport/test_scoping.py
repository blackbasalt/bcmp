"""The single checkpoint for filtering by organisation (ADR 0001).

`Space.objects.visible_to(user)` is the only place where data is narrowed down to the
user's organisations. Read paths ask it instead of assembling a filter themselves; at
the time of this ticket there are no screens yet, so the checkpoint is tested directly.
"""

import pytest
from django.contrib.auth.models import AnonymousUser, User

from building_passport.models import Space
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db


def make_building(org, code):
    return Space.objects.create(org=org, type="building", code=code)


def test_a_member_sees_the_spaces_of_their_organisation_only(downtown, central):
    user = User.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    ours = make_building(downtown, "БЦ-1")
    make_building(central, "БЦ-2")

    assert list(Space.objects.visible_to(user)) == [ours]


def test_a_superuser_sees_every_organisation(downtown, central):
    """A developer reproduces a client's problem without granting themselves a membership."""
    developer = User.objects.create_superuser("developer")
    ours = make_building(downtown, "БЦ-1")
    theirs = make_building(central, "БЦ-2")

    assert set(Space.objects.visible_to(developer)) == {ours, theirs}


def test_a_user_without_membership_sees_nothing_rather_than_everything(downtown):
    """"No membership → everything is visible" is exactly the leak the filtering exists for."""
    newcomer = User.objects.create_user("newcomer")
    make_building(downtown, "БЦ-1")

    assert list(Space.objects.visible_to(newcomer)) == []


def test_an_anonymous_visitor_sees_nothing(downtown):
    make_building(downtown, "БЦ-1")

    assert list(Space.objects.visible_to(AnonymousUser())) == []


def test_a_member_of_two_organisations_sees_both_portfolios(downtown, central):
    user = User.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    OrgMembership.objects.create(user=user, org=central)
    ours = make_building(downtown, "БЦ-1")
    theirs = make_building(central, "БЦ-2")

    assert set(Space.objects.visible_to(user)) == {ours, theirs}


def test_a_space_belonging_to_no_organisation_is_visible_to_no_member(downtown):
    """A space attached to no organisation belongs to nobody, not to everybody."""
    user = User.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)
    make_building(None, "БЦ-ничей")

    assert list(Space.objects.visible_to(user)) == []


def test_revoking_membership_hides_the_organisation_again(downtown):
    user = User.objects.create_user("engineer")
    membership = OrgMembership.objects.create(user=user, org=downtown)
    make_building(downtown, "БЦ-1")

    membership.delete()

    assert list(Space.objects.visible_to(user)) == []
