"""Аренда as data: what is written down, what is refused, and what is deliberately not.

This stage has no screen — an аренда is entered in the Django admin — so the seams are the
two the stage actually has: the model, where the refusal sits so that the admin, a future
form and any script get it in the same words, and the admin page itself.

Most of what is checked here is what is **accepted**: overlapping периоды, one арендатор
twice on one помещение, a sum of арендуемые площади over the площадь of the помещение, an
аренда on a МОП. Every one of them is a check the project decided not to have (ADR 0017,
ADR 0019), and every one of them looks like an oversight to whoever reads the model next.
Pinned by name, they read as what they are.

The last two tests are about neighbouring models rather than about Lease. They stand here
because they exist for the sake of аренда: `PartyRole.TENANT` goes because the аренда says
who sits in a помещение, and `DocumentLink` gains «аренда» because the скан of a договор
has to be attachable to one.
"""

import re
import uuid
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from documents.models import Document, DocumentLink
from leases.models import Lease
from parties.models import PartyRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def kab305(first_floor, make_space):
    """An арендопригодное помещение of a known площадь — the ordinary subject of an аренда."""
    return make_space(
        first_floor, "man-f1-c", "каб305", area_m2=300, is_leasable=True, is_common=False
    )


# What an аренда holds


def test_a_lease_says_who_sits_where_on_what_terms_and_until_when(kab305, alpha, petrov):
    """«Кто сидит в 305 и на каких условиях» is one record and not a search across tables."""
    lease = Lease.objects.create(
        space=kab305,
        tenant=alpha,
        landlord=petrov,
        area_m2=40,
        rate=12000,
        contract_no="№17",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
    )

    lease.refresh_from_db()
    assert (lease.space, lease.tenant, lease.landlord) == (kab305, alpha, petrov)
    assert (lease.area_m2, lease.rate, lease.contract_no) == (40, 12000, "№17")
    assert (lease.valid_from, lease.valid_to) == (date(2026, 1, 1), date(2026, 12, 31))


def test_only_the_room_the_tenant_and_the_beginning_of_the_period_are_required(kab305, alpha):
    """The УК's table is not always complete, and half an аренда beats none at all.

    The one thing that may not be missing is the day it starts: a record that cannot say
    whether it is in force today answers no question the аренда exists for.
    """
    lease = Lease.objects.create(space=kab305, tenant=alpha, valid_from=date(2026, 1, 1))

    assert (lease.landlord, lease.area_m2, lease.rate, lease.contract_no) == (None,) * 4
    assert lease.valid_to is None


def test_the_leases_of_a_room_are_reached_from_the_room(kab305, alpha, make_lease):
    """The карточка помещения asks the помещение, not a query of its own."""
    lease = make_lease(kab305, alpha)

    assert list(kab305.leases.all()) == [lease]


def test_a_lease_is_keyed_by_a_uuid(kab305, alpha, make_lease):
    """Like everything introduced since stage 1: a key that a screen may put in an address."""
    assert isinstance(make_lease(kab305, alpha).pk, uuid.UUID)


def test_a_lease_has_no_organisation_of_its_own():
    """Visibility is inherited from the помещение — the checkpoint stays single (ADR 0018).

    A second place deciding whose data to show is the way for the two to drift apart, and
    an аренда is about exactly one помещение whose `org` is always filled in.
    """
    assert "org" not in {field.name for field in Lease._meta.get_fields()}


# The срок


def test_a_period_that_ends_before_it_begins_is_refused(kab305, alpha):
    """A typo in a date is caught where it is made: such a период is never in force."""
    with pytest.raises(ValidationError) as refusal:
        Lease.objects.create(
            space=kab305, tenant=alpha, valid_from=date(2026, 3, 1), valid_to=date(2026, 2, 1)
        )

    assert re.search(r"раньше", str(refusal.value))
    assert Lease.objects.count() == 0


def test_editing_a_period_into_an_ending_before_its_beginning_is_refused(
    kab305, alpha, make_lease
):
    """A досрочный выезд is recorded by moving «по» — the same write path, the same refusal."""
    lease = make_lease(kab305, alpha, valid_from=date(2026, 3, 1))

    lease.valid_to = date(2026, 2, 1)
    with pytest.raises(ValidationError):
        lease.save()

    lease.refresh_from_db()
    assert lease.valid_to is None


def test_a_period_of_a_single_day_is_a_period(kab305, alpha, make_lease):
    """Both ends belong to the период: «с 1 по 1 марта» is in force on the 1st."""
    lease = make_lease(kab305, alpha, valid_from=date(2026, 3, 1), valid_to=date(2026, 3, 1))

    assert lease.valid_to == lease.valid_from


def test_a_period_with_no_end_is_a_lease_to_this_day(kab305, alpha, make_lease):
    """A бессрочная аренда needs no invented end date — the reading the план already gives."""
    assert make_lease(kab305, alpha, valid_to=None).valid_to is None


# The checks that are absent, and that is the decision


def test_two_leases_of_one_room_may_overlap(kab305, alpha, petrov, make_lease):
    """Пересечение is the normal case, not a collision (ADR 0017).

    An опенспейс with two арендаторы has no wall between them and will not grow one; a
    refusal here would refuse the very case the аренда was built for.
    """
    make_lease(kab305, alpha, valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31))
    make_lease(kab305, petrov, valid_from=date(2026, 6, 1), valid_to=date(2027, 5, 31))

    assert kab305.leases.count() == 2


def test_one_tenant_holds_two_leases_of_one_room_at_once(kab305, alpha, make_lease):
    """Taking another 20 м² in June does not overwrite the 40 taken in January."""
    make_lease(kab305, alpha, area_m2=40, valid_from=date(2026, 1, 1))
    make_lease(kab305, alpha, area_m2=20, valid_from=date(2026, 6, 1))

    assert sorted(lease.area_m2 for lease in kab305.leases.all()) == [20, 40]


def test_the_leased_areas_may_add_up_to_more_than_the_room(kab305, alpha, petrov, make_lease):
    """Арендуемая площадь is a term of an agreement, not a measurement.

    It includes a share of the МОП by a coefficient, so «сдано 340 из 300 м²» is correct
    data; a check would refuse it.
    """
    make_lease(kab305, alpha, area_m2=200)
    make_lease(kab305, petrov, area_m2=140)

    assert kab305.area_m2 == 300


def test_a_lease_with_no_leased_area_is_accepted(kab305, alpha, make_lease):
    """The number of metres is often not in the УК's table, and the арендатор still sits there."""
    assert make_lease(kab305, alpha, area_m2=None).area_m2 is None


def test_a_lease_on_a_common_room_is_accepted(first_floor, alpha, make_space, make_lease):
    """The банкомат in the лобби is a real аренда, and the лобби stays a МОП.

    Арендопригодность is not checked: a венткамера let by mistake surfaces as a находка on
    the полка, where it can be looked at, rather than as a refusal at the moment of entry.
    """
    lobby = make_space(first_floor, "man-f1-l", "Лобби", is_common=True, is_leasable=False)

    assert make_lease(lobby, alpha).space == lobby


def test_a_lease_on_a_technical_room_is_accepted(first_floor, alpha, make_lease):
    """The ИТП of the first floor is neither арендопригодное nor a МОП, and is let all the same."""
    itp = first_floor.subspace.get(name="ИТП")

    assert make_lease(itp, alpha).space == itp


def test_letting_a_room_does_not_let_the_rooms_inside_it(first_floor, alpha, make_lease):
    """Занятость is not read from the дерево (ADR 0019): «каб101» sits inside «каб101вход».

    A connection in the tree means one of two things and does not say which, so letting the
    входной тамбур leaves the кабинеты behind it as they were.
    """
    entrance = first_floor.subspace.get(name="каб101вход")
    inner = entrance.subspace.get(name="каб101")

    make_lease(entrance, alpha)

    assert inner.leases.count() == 0


# The Django admin — the only place an аренда is entered in this stage


def lease_form(space, tenant, valid_from=date(2026, 1, 1), valid_to=None, **fields):
    return {
        "space": str(space.pk),
        "tenant": str(tenant.pk),
        "landlord": "",
        "area_m2": "",
        "rate": "",
        "contract_no": "",
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat() if valid_to else "",
        **fields,
    }


def test_a_lease_is_created_in_django_admin(admin_client, kab305, alpha):
    """Until the карточка carries the form, this is where an аренда is written down."""
    response = admin_client.post(
        reverse("admin:leases_lease_add"), lease_form(kab305, alpha, area_m2="40", rate="12000")
    )

    assert response.status_code == 302
    lease = Lease.objects.get()
    assert (lease.space, lease.tenant, lease.area_m2) == (kab305, alpha, 40)


def test_a_lease_is_edited_in_django_admin(admin_client, kab305, alpha, petrov, make_lease):
    """A досрочный выезд and a corrected ставка are entered in the same place."""
    lease = make_lease(kab305, alpha)

    response = admin_client.post(
        reverse("admin:leases_lease_change", args=[lease.pk]),
        lease_form(kab305, petrov, valid_to=date(2026, 6, 30)),
    )

    assert response.status_code == 302
    lease.refresh_from_db()
    assert (lease.tenant, lease.valid_to) == (petrov, date(2026, 6, 30))


def test_a_period_that_ends_before_it_begins_is_refused_in_admin_with_a_reason(
    admin_client, kab305, alpha
):
    """The refusal is named on the form, in Russian: otherwise the date is fixed by guesswork."""
    response = admin_client.post(
        reverse("admin:leases_lease_add"),
        lease_form(kab305, alpha, valid_from=date(2026, 3, 1), valid_to=date(2026, 2, 1)),
    )

    assert response.status_code == 200
    assert re.search(r"Период заканчивается раньше", response.content.decode())
    assert Lease.objects.count() == 0


# What аренда changes in the models next to it


def test_a_party_is_no_longer_made_a_tenant_by_a_role():
    """Арендатором Сторону делает аренда, а не роль.

    Left in place, the роль invites an арендатор to be entered beside the аренда — with no
    metres, no срок and no ставка — and then a помещение is let by one table and free by
    another. The other seven роли are untouched.
    """
    assert "tenant" not in PartyRole.Role.values
    assert {
        "owner",
        "operator",
        "contractor",
        "supplier",
        "expert",
        "designer",
        "builder",
    } <= set(PartyRole.Role.values)


def test_the_scan_of_a_contract_is_attached_to_the_lease_itself(kab305, alpha, downtown, make_lease):
    """A скан pointing at the помещение would pile every договор of a shared one into a heap.

    No screen attaches anything yet: the type exists so that the привязка of the документы
    stage has somewhere to point when it is built.
    """
    lease = make_lease(kab305, alpha)
    document = Document.objects.create(
        org=downtown, kind=Document.Kind.CONTRACT, title="Договор №17"
    )

    link = DocumentLink.objects.create(
        document=document, entity_type=DocumentLink.EntityType.LEASE, entity_id=lease.pk
    )

    assert (link.entity_type, link.entity_id) == ("lease", lease.pk)
