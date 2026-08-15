import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse

from parties.models import Org, OrgMembership

pytestmark = pytest.mark.django_db


def test_a_user_works_for_two_organisations_under_one_login(downtown, central):
    """An employee of the management company serving two clients holds both memberships,
    not two accounts."""
    user = User.objects.create_user("engineer")

    OrgMembership.objects.create(user=user, org=downtown)
    OrgMembership.objects.create(user=user, org=central)

    assert set(Org.objects.filter(memberships__user=user)) == {downtown, central}


def test_the_same_access_cannot_be_granted_twice(downtown):
    user = User.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown)

    with pytest.raises(IntegrityError), transaction.atomic():
        OrgMembership.objects.create(user=user, org=downtown)

    assert OrgMembership.objects.filter(user=user, org=downtown).count() == 1


def test_revoking_a_membership_leaves_the_organisation_and_the_user_in_place(downtown):
    """Revoking access is deleting the membership, not the user and not the organisation."""
    user = User.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=downtown).delete()

    assert not Org.objects.filter(memberships__user=user).exists()
    assert User.objects.filter(pk=user.pk).exists()
    assert Org.objects.filter(pk=downtown.pk).exists()


def test_an_administrator_grants_and_revokes_access_from_django_admin(client, downtown):
    """Onboarding an employee does not require a developer."""
    client.force_login(User.objects.create_superuser("administrator"))
    user = User.objects.create_user("engineer")

    granted = client.post(
        reverse("admin:parties_orgmembership_add"),
        {"user": user.pk, "org": str(downtown.pk)},
    )

    assert granted.status_code == 302
    membership = OrgMembership.objects.get(user=user, org=downtown)

    revoked = client.post(
        reverse("admin:parties_orgmembership_delete", args=[membership.pk]),
        {"post": "yes"},
    )

    assert revoked.status_code == 302
    assert not OrgMembership.objects.filter(pk=membership.pk).exists()


def test_the_user_page_in_admin_carries_the_memberships_of_that_user(client):
    """Access is visible in the same place where the user is created."""
    client.force_login(User.objects.create_superuser("administrator"))
    user = User.objects.create_user("engineer")

    page = client.get(reverse("admin:auth_user_change", args=[user.pk]))

    assert page.status_code == 200
    assert "memberships-0-org" in page.content.decode()
