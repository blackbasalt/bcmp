"""Наполнение: a dozen fictional арендаторы and their аренды on Manhattan.

What is checked is not that the files were read but what they were written for. «Сдано X
из Y», the находки and the отбор «свободно» have nothing to stand on until somebody enters
an аренда, and the awkward shapes are the whole point of the наполнение: a помещение with
three арендаторы, a sum over the помещение's площадь, an аренда with no площадь, one with
no ставка, one on a лобби, and a pair of прошлые аренды behind the fold. Every one of them
is pinned here by name, because every one of them looks like bad data to whoever tidies the
file next.

Half of the checks never touch the database — they stand over the files themselves. That a
помещение named in `lease.csv` exists in `space.csv`, and that a вымышленный БИН is not the
number of a real Сторона, is visible in the file, and it is better seen there than after a
refusal has left the base half-filled.

The building the rest stand on is built from the same `space.csv` the working base lives
from: наполнение that has drifted apart from the посевные помещения would go in silently
and let nothing.
"""

from datetime import date
from decimal import Decimal

import pytest

from building_passport.models import Space
from building_passport.space_kind import COMMON, LEASABLE, kind_of
from leases.models import Lease
from parties.models import Party

from . import load_real_data

pytestmark = pytest.mark.django_db

#: The day the наполнение is entered on in the tests. Any day would do — that is the point
#: of holding the срок as offsets — but a named one makes «уже кончилось» and «кончится
#: через полгода» checkable at all.
ANCHOR = date(2026, 3, 2)


def leases():
    return load_real_data.rows("lease.csv")


def tenants():
    return load_real_data.rows("tenant.csv")


def real_bins():
    """Настоящие БИНы — те, что вымышленный занять не должен и настоящий обязан носить."""
    return {row["inn_bin"] for row in load_real_data.rows("party.csv")}


def in_force_on(lease, day):
    """Both ends included, an empty end reading «по сей день» — the срок as the spec reads it.

    It is spelled out here rather than imported: the rule the screens will read belongs to
    the stage that builds them, and this suite is about the data, not about the rule.
    """
    return lease.valid_from <= day and (lease.valid_to is None or lease.valid_to >= day)


def in_force(day=ANCHOR):
    return [lease for lease in Lease.objects.all() if in_force_on(lease, day)]


# The files themselves


def test_the_filling_holds_a_couple_of_dozen_leases():
    """«Пара десятков» — enough for the awkward shapes, few enough to read in one sitting."""
    assert 20 <= len(leases()) <= 30


def test_every_let_room_is_a_room_of_manhattan():
    """A наполнение that has drifted from `space.csv` would let помещения that do not exist."""
    manhattan = {
        row["code"] for row in load_real_data.rows("space.csv") if row["building"] == "man"
    }

    assert {row["space"] for row in leases()} <= manhattan


def test_no_fictional_tenant_borrows_a_bin_from_a_real_party():
    """Their БИН is impossible — month 99 — so that it cannot be a real Сторона's number.

    699 Стороны in `party.csv` came from an actual list of counterparties. A вымышленный
    арендатор wearing one of their numbers would put a lie into the data that somebody
    later reads as the truth.
    """
    fictional = [row["bin_iin"] for row in tenants()]

    assert len(set(fictional)) == len(fictional)
    assert not set(fictional) & real_bins()


def test_every_named_landlord_is_a_party_of_the_registry():
    """The арендодатель is a Сторона already in the base, not a thirteenth invented one."""
    named = {row["landlord"] for row in leases() if row["landlord"]}

    assert named and named <= real_bins()


def test_every_fictional_tenant_actually_rents_something():
    """A Сторона entered and never let anything to is not an арендатор, it is litter."""
    assert {row["slug"] for row in tenants()} == {row["tenant"] for row in leases()}


def test_no_lease_in_the_file_ends_before_it_begins():
    """The model refuses such a период (ADR 0017), and the refusal lands mid-наполнение.

    Seen in the file, it is one bad line; seen at the model, it is a base half-filled.
    """
    for row in leases():
        valid_from, valid_to = load_real_data.term(row, ANCHOR)
        assert valid_to is None or valid_to >= valid_from, row["space"]


# The building the наполнение is entered onto, as the working base holds it


@pytest.fixture
def manhattan_from_seed(downtown):
    """Manhattan out of `space.csv` — the same помещения the working base lives from."""
    pending = [
        row
        for row in load_real_data.rows("space.csv")
        if row["code"] == "man" or row["building"] == "man"
    ]
    spaces = {}
    while pending:
        deferred = []
        for row in pending:
            parent = spaces.get(row["parent"])
            if parent is None and row["code"] != "man":
                deferred.append(row)
                continue
            spaces[row["code"]] = Space.objects.create(
                org=downtown,
                parent=parent,
                building=spaces.get("man"),
                type=row["type"],
                code=row["code"],
                name=row["name"],
                floor_number=int(row["floor_number"]) if row["floor_number"] else None,
                area_m2=Decimal(row["area_m2"]) if row["area_m2"] else None,
                is_common=row["is_common"] == "TRUE" if row["is_common"] else None,
                is_leasable=row["is_leasable"] == "TRUE" if row["is_leasable"] else None,
            )
        assert len(deferred) < len(pending), "помещение ссылается на несуществующего родителя"
        pending = deferred
    return spaces


@pytest.fixture
def landlords():
    """The Стороны the наполнение lets in the name of: the собственник and the УК.

    All five БЦ belong to «Компания системных бизнес технологий ТОО» and are run by
    DownTown Management ТОО. That gap is already in the data, and the наполнение shows it.
    """
    named = {row["landlord"] for row in leases() if row["landlord"]}
    by_bin = {row["inn_bin"]: row for row in load_real_data.rows("party.csv")}
    # `get_or_create`: DownTown Management is the УК of the наполнение and the Сторона
    # behind the организация of the root `conftest` at once — one Сторона, entered once.
    return [
        Party.objects.get_or_create(
            bin_iin=bin_iin,
            defaults={"kind": Party.Kind.COMPANY, "name": by_bin[bin_iin]["clean_name"]},
        )[0]
        for bin_iin in named
    ]


@pytest.fixture
def filled(manhattan_from_seed, landlords):
    load_real_data.fill_leases(ANCHOR)
    return manhattan_from_seed


# What the наполнение puts into the base


def test_the_filling_lets_rooms_of_manhattan(filled):
    """Every аренда entered, and every one of them on a помещение of the one building."""
    assert Lease.objects.count() == len(leases())
    assert {lease.space.building.code for lease in Lease.objects.all()} == {"man"}


def test_a_room_holds_three_tenants_at_once(filled):
    """The опенспейс the плоская аренда exists for (ADR 0017): three, and no walls between."""
    crowded = [
        space
        for space in filled.values()
        if len([lease for lease in in_force() if lease.space_id == space.pk]) >= 3
    ]

    assert crowded


def test_a_room_is_let_for_more_metres_than_it_has(filled):
    """«Сдано 340 из 300 м²» — the share of the МОП sits inside the арендуемая площадь."""
    over = [
        space
        for space in filled.values()
        if space.area_m2
        and sum(
            lease.area_m2 for lease in in_force() if lease.space_id == space.pk and lease.area_m2
        )
        > space.area_m2
    ]

    assert over


def test_a_lease_names_no_leased_area(filled):
    """The one that makes «сдано X из Y» incomplete: an арендатор sits there, unmeasured.

    It shares its помещение with an аренда that does name its metres, so the incompleteness
    is visible on the screen rather than only in the table.
    """
    without = [lease for lease in in_force() if lease.area_m2 is None]

    assert without
    assert all(
        any(
            other.area_m2 is not None
            for other in in_force()
            if other.space_id == lease.space_id
        )
        for lease in without
    )


def test_a_lease_names_no_rate(filled):
    """The бумага is lost and the запись is not: half an аренда beats none at all."""
    assert [lease for lease in in_force() if lease.rate is None]


def test_a_lease_sits_on_a_room_that_is_not_leasable(filled):
    """The банкомат in the лобби — a находка on the полка, and not an error to be refused.

    Вид is asked of `space_kind` rather than read off the two flags here: the rule is
    settled there and nowhere else, and a copy of it in a test would be the copy nobody
    updates when the flags are read differently.
    """
    on_common = [lease for lease in in_force() if kind_of(lease.space) == COMMON]

    assert on_common


def test_a_room_carries_two_leases_that_are_already_over(filled):
    """The складка has something to hide, and the помещение is not free for all that."""
    over = [lease for lease in Lease.objects.all() if not in_force_on(lease, ANCHOR)]
    by_space = {}
    for lease in over:
        by_space.setdefault(lease.space_id, []).append(lease)

    assert any(len(past) >= 2 for past in by_space.values())


def test_a_lease_has_no_end(filled):
    """Бессрочная: an empty «по» reads «по сей день» and needs no invented date."""
    assert [lease for lease in Lease.objects.all() if lease.valid_to is None]


def test_the_landlord_is_named_on_some_leases_and_left_empty_on_others(filled):
    """Both halves of the разрыв: the собственник, the УК in its own name, and no name at all.

    Доверительное управление is how all five БЦ actually stand, and the УК's table does not
    always say in whose name a помещение was let.
    """
    named = {lease.landlord.bin_iin for lease in Lease.objects.all() if lease.landlord}

    # Two at least, and the two that matter: the БЦ belongs to one Сторона and is let by
    # another. One name alone would hide exactly the разрыв the наполнение exists to show.
    assert len(named) >= 2
    assert [lease for lease in Lease.objects.all() if lease.landlord is None]


def test_rooms_are_left_free_on_purpose(filled):
    """«Свободно» must be a number worth reading, not a synonym for «ничего не заведено»."""
    leasable = [space for space in filled.values() if kind_of(space) == LEASABLE]
    let = {lease.space_id for lease in in_force()}

    assert len([space for space in leasable if space.pk not in let]) > len(leasable) / 2


def test_the_fictional_tenants_do_not_pass_for_real_parties(filled):
    """They are marked in the base too, and by the field that already says where a row is from.

    A second flag saying «это наполнение» would one day disagree with the first, and the
    same mark is how the наполнение recognises its own leavings when it clears them.
    """
    fictional = Party.objects.filter(external_id__startswith=load_real_data.FILLING_MARK)

    assert fictional.count() == len(tenants())
    assert {party.name for party in fictional} == {row["name"] for row in tenants()}


def test_filling_twice_doubles_neither_the_leases_nor_the_parties(filled):
    """A repeat run replaces the previous наполнение rather than laying a second one on top."""
    load_real_data.fill_leases(ANCHOR)

    assert Lease.objects.count() == len(leases())
    assert Party.objects.filter(external_id__startswith=load_real_data.FILLING_MARK).count() == (
        len(tenants())
    )


def test_the_filling_leaves_the_real_parties_alone(filled, landlords):
    """699 Стороны came from an actual list of counterparties; наполнение comes beside them."""
    assert Party.objects.filter(external_id__isnull=True).count() == len(landlords)
