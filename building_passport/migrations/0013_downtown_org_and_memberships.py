"""Moving the existing data into the organisation DownTown Management ТОО (ADR 0001).

Five passports already carry this party as their `operator_party`, so the organisation
is built over the existing party — no second Party is created.
"""

from django.conf import settings
from django.db import migrations

DOWNTOWN_BIN = "180540035878"


def _downtown_party(apps):
    Party = apps.get_model("parties", "Party")
    return Party.objects.filter(bin_iin=DOWNTOWN_BIN).first()


def grant_downtown_access(apps, schema_editor):
    party = _downtown_party(apps)
    if party is None:
        return  # a clean database: there is nothing to move

    Org = apps.get_model("parties", "Org")
    OrgMembership = apps.get_model("parties", "OrgMembership")
    Space = apps.get_model("building_passport", "Space")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    org, _ = Org.objects.get_or_create(party=party)
    Space.objects.filter(org__isnull=True).update(org=org)
    OrgMembership.objects.bulk_create(
        [OrgMembership(user=user, org=org) for user in User.objects.all()],
        ignore_conflicts=True,
    )


def revoke_downtown_access(apps, schema_editor):
    """A full rollback of the move.

    It revokes every access to the organisation, not only the ones granted by this
    migration: there is nothing to tell them apart from those granted later in the
    admin. A rollback on the production database wipes the onboarding.
    """
    party = _downtown_party(apps)
    if party is None:
        return

    Org = apps.get_model("parties", "Org")
    OrgMembership = apps.get_model("parties", "OrgMembership")
    Space = apps.get_model("building_passport", "Space")

    org = Org.objects.filter(party=party).first()
    if org is None:
        return

    Space.objects.filter(org=org).update(org=None)
    OrgMembership.objects.filter(org=org).delete()
    org.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("building_passport", "0012_alter_buildingpassport_building_volume"),
        ("parties", "0004_orgmembership"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(grant_downtown_access, revoke_downtown_access),
    ]
