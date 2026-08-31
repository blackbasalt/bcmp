"""Блок аренды на карточке помещения — что видно на HTTP-границе.

The seam is `building_passport:space_card`, the card's own address and the one this stage
already had: the block arrives inside the card and is read as part of its response. Nothing
below HTTP is a seam — the occupancy rule, the query that collected the аренды and the
wording of the count line are all read through this screen, and a suite that pinned them
would have to be rewritten with every rewrite of them.

These tests live in `leases` rather than beside `test_space_card.py` because what they
stage is аренда: the Стороны that sit in помещения and the factory that seats them come
from `leases/conftest.py`, and Manhattan with its first floor comes from the root one.

The footholds in the markup are `data-lease` on a row, mirroring `data-room` on the полка
and `data-document` on the полка документов — a test names an аренда by its key and reads
its text without parsing the layout — and `data-leases` on the block with `data-past-leases`
on the складка, mirroring `data-upload` on the two upload forms: whether the block is there
at all is asked of the block, not of a word that another column might print one day.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse

from building_passport.models import Space

pytestmark = pytest.mark.django_db

#: One аренда row together with its key — the screen's contract about what a row carries.
LEASE = re.compile(r'<li[^>]*data-lease="(?P<key>[^"]+)"[^>]*>(?P<text>.*?)</li>', re.DOTALL)


def carries_the_block(page) -> bool:
    """Whether the карточка offers the аренда block at all."""
    return "data-leases" in page


def carries_a_fold(page) -> bool:
    """Whether there is a складка, that is, anything that is not today's аренда."""
    return "data-past-leases" in page


def stated(text):
    """The text on a single line: a phrase must not break on a line wrap in the markup."""
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def open_card(client, space):
    """The card as it came back: the markup, so that a row can still be found by its key."""
    response = client.get(reverse("building_passport:space_card", args=[space.pk]))
    return response, response.content.decode()


def leases_on(page):
    """The аренда rows by key: what is written in each of them."""
    return {row["key"]: stated(row["text"]) for row in LEASE.finditer(page)}


# When the block is there at all


def test_a_leasable_space_carries_the_block_even_with_no_leases(reader, kab305):
    """«Свободно» has to read as an answer, not as a section that failed to load."""
    _, page = open_card(reader, kab305)

    assert carries_the_block(page)
    assert "Свободно" in stated(page)


def test_a_common_space_with_no_leases_carries_no_block(reader, lobby):
    """A section promising data that does not exist is not put in front of a reader."""
    _, page = open_card(reader, lobby)

    assert not carries_the_block(page)


def test_a_common_space_holding_a_lease_carries_the_block(reader, lobby, alpha, make_lease):
    """The банкомат in the лобби is visible where it stands."""
    make_lease(lobby, alpha, area_m2=2)

    _, page = open_card(reader, lobby)

    assert carries_the_block(page)
    assert "ТОО «Альфа»" in stated(page)


def test_a_common_space_whose_lease_has_ended_is_not_called_free(
    reader, lobby, alpha, make_lease, today
):
    """«Свободно» is an арендопригодное помещение with nobody in it, and a лобби is not one.

    The word answers «что стоит пустым» — it is a помещение on offer — and a МОП named by it
    is a leasing opportunity BCMP invented. The аренда that has ended is still behind the
    складка: what happened is not hidden, only not renamed.
    """
    make_lease(
        lobby,
        alpha,
        area_m2=2,
        valid_from=today - timedelta(days=90),
        valid_to=today - timedelta(days=1),
    )

    _, page = open_card(reader, lobby)

    assert carries_the_block(page)
    assert "Свободно" not in stated(page)
    assert "Прошлые аренды (1)" in stated(page)


# «Сдано X из Y»


def test_the_line_counts_only_the_leases_in_force(
    reader, kab305, alpha, petrov, make_lease, today
):
    """The card speaks about today: an арендатор who left in March is not still sitting there."""
    make_lease(kab305, alpha, area_m2=210, valid_from=today - timedelta(days=30))
    make_lease(
        kab305,
        petrov,
        area_m2=90,
        valid_from=today - timedelta(days=90),
        valid_to=today - timedelta(days=1),
    )

    _, page = open_card(reader, kab305)

    assert "Сдано 210 из 300 м²" in stated(page)


def test_a_space_with_no_area_gets_no_ratio(reader, first_floor, make_space, alpha, make_lease):
    """A gap in the помещение's own data is not dressed up as a доля."""
    nameless = make_space(first_floor, "man-f1-e", "каб307", is_leasable=True)
    make_lease(nameless, alpha, area_m2=40)

    _, page = open_card(reader, nameless)

    assert "Сдано" not in stated(page)
    assert "ТОО «Альфа»" in stated(page)


def test_a_lease_with_no_area_is_dashed_and_counted_nowhere(
    reader, kab305, alpha, petrov, make_lease
):
    """A missing number of metres must not be read as zero metres."""
    make_lease(kab305, alpha, area_m2=210)
    without = make_lease(kab305, petrov)

    _, page = open_card(reader, kab305)

    assert "Сдано 210 из 300 м²" in stated(page)
    assert "— нет данных" in leases_on(page)[str(without.pk)]


def test_the_line_says_how_many_leases_have_no_area(
    reader, kab305, alpha, petrov, make_lease
):
    """The number must not lie by omission: what it left out is stated beside it."""
    make_lease(kab305, alpha, area_m2=210)
    make_lease(kab305, petrov)
    make_lease(kab305, alpha)

    _, page = open_card(reader, kab305)

    assert "Сдано 210 из 300 м², ещё у 2 аренд площадь не заведена" in stated(page)


def test_one_lease_without_an_area_is_named_in_the_singular(
    reader, kab305, alpha, petrov, make_lease
):
    """«ещё у 1 аренд» reads as a glitch of the screen rather than as one аренда."""
    make_lease(kab305, alpha, area_m2=210)
    make_lease(kab305, petrov)

    _, page = open_card(reader, kab305)

    assert "ещё у 1 аренды площадь не заведена" in stated(page)


def test_a_sum_over_the_area_is_printed_as_it_is(reader, kab305, alpha, petrov, make_lease):
    """Арендуемая площадь carries a share of the МОП: 340 из 300 is a finding, not an error."""
    make_lease(kab305, alpha, area_m2=200)
    make_lease(kab305, petrov, area_m2=140)

    _, page = open_card(reader, kab305)

    assert "Сдано 340 из 300 м²" in stated(page)


# What a row says


def test_a_lease_in_force_is_named_by_tenant_metres_term_and_rate(
    reader, kab305, alpha, make_lease, today
):
    """«Кто здесь сидит» is answered without a second screen."""
    began = today - timedelta(days=30)
    ends = today + timedelta(days=300)
    lease = make_lease(kab305, alpha, area_m2=40, rate=4500, valid_from=began, valid_to=ends)

    _, page = open_card(reader, kab305)

    row = leases_on(page)[str(lease.pk)]
    assert "ТОО «Альфа»" in row
    assert "40 м²" in row
    assert f"с {began:%d.%m.%Y} по {ends:%d.%m.%Y}" in row
    assert "4 500,00 за м² в месяц" in row


def test_the_rate_is_printed_with_its_unit(reader, kab305, alpha, make_lease):
    """Without the unit 4500 reads as the rent for the whole помещение."""
    lease = make_lease(kab305, alpha, area_m2=40, rate=4500)

    _, page = open_card(reader, kab305)

    assert "за м² в месяц" in leases_on(page)[str(lease.pk)]


def test_every_lease_row_carries_its_key(reader, kab305, alpha, petrov, make_lease):
    """`data-lease` is the block's contract: which аренды are shown and in what order."""
    first = make_lease(kab305, alpha, area_m2=40)
    second = make_lease(kab305, petrov, area_m2=60)

    _, page = open_card(reader, kab305)

    assert set(leases_on(page)) == {str(first.pk), str(second.pk)}


# The срок


def test_a_lease_with_no_end_is_in_force(reader, kab305, alpha, make_lease, today):
    """An empty «по» reads «по сей день» — the same reading the поэтажный план gives."""
    lease = make_lease(kab305, alpha, area_m2=40, valid_from=today - timedelta(days=1))

    _, page = open_card(reader, kab305)

    assert "по сей день" in leases_on(page)[str(lease.pk)]


def test_a_lease_ending_today_is_still_in_force(reader, kab305, alpha, make_lease, today):
    """Both ends of the период are included: an аренда «по 31 марта» stands on the 31st."""
    lease = make_lease(
        kab305, alpha, area_m2=40, valid_from=today - timedelta(days=30), valid_to=today
    )

    _, page = open_card(reader, kab305)

    assert str(lease.pk) in leases_on(page)
    assert "Сдано 40 из 300 м²" in stated(page)


def test_a_lease_that_ended_yesterday_is_past(reader, kab305, alpha, make_lease, today):
    """A досрочный выезд is recorded by moving «по», and the screen stops showing the tenant."""
    make_lease(
        kab305,
        alpha,
        area_m2=40,
        valid_from=today - timedelta(days=30),
        valid_to=today - timedelta(days=1),
    )

    _, page = open_card(reader, kab305)

    assert "Свободно" in stated(page)
    assert "Прошлые аренды (1)" in stated(page)


# The fold


def test_past_leases_stand_behind_a_fold_that_counts_them(
    reader, kab305, alpha, petrov, make_lease, today
):
    """Ten departed арендаторы must not bury the one sitting there now."""
    make_lease(kab305, alpha, area_m2=210)
    for gone in (petrov, petrov):
        make_lease(
            kab305,
            gone,
            area_m2=90,
            valid_from=today - timedelta(days=400),
            valid_to=today - timedelta(days=200),
        )

    _, page = open_card(reader, kab305)

    assert "Прошлые аренды (2)" in stated(page)


def test_a_space_with_nothing_behind_the_fold_carries_no_fold(
    reader, kab305, alpha, make_lease
):
    """An empty fold is a click that leads nowhere, and the reader is not made to try it."""
    make_lease(kab305, alpha, area_m2=210)

    _, page = open_card(reader, kab305)

    assert not carries_a_fold(page)


def test_a_lease_that_has_not_begun_is_not_in_force_and_the_fold_says_so(
    reader, kab305, alpha, make_lease, today
):
    """A продление is entered as a new аренда before it starts, and it is not «прошлая»."""
    make_lease(kab305, alpha, area_m2=40, valid_from=today + timedelta(days=30))

    _, page = open_card(reader, kab305)

    assert "Свободно" in stated(page)
    assert "Прошлые и будущие аренды (1)" in stated(page)


# The tree


def test_occupancy_is_not_inherited_from_the_tree(
    reader, first_floor, make_space, alpha, make_lease
):
    """Сдача входного тамбура кабинеты за ним не сдаёт (ADR 0019).

    The link in the tree means either physical nesting or the grouping of neighbours, and
    nothing in a row tells the two apart — so a rule reading occupancy off the hierarchy
    would be right about one and silently wrong about the other.
    """
    entrance = Space.objects.get(code="man-f1-a")
    entrance.is_leasable, entrance.area_m2 = True, 60
    entrance.save()
    inside = Space.objects.get(code="man-f1-a1")
    inside.is_leasable, inside.area_m2 = True, 20
    inside.save()
    make_lease(entrance, alpha, area_m2=60)

    _, page = open_card(reader, inside)

    assert "Свободно" in stated(page)
    assert "ТОО «Альфа»" not in stated(page)


def test_no_floor_screen_totals_the_leases(reader, kab305, alpha, make_lease, first_floor):
    """107 арендопригодных помещений sit inside another one: a total would count them twice."""
    make_lease(kab305, alpha, area_m2=210)

    floor = reader.get(
        reverse("building_passport:floor", args=[first_floor.building_id, first_floor.pk])
    )

    assert "Сдано" not in stated(floor.content.decode())


# Access


def test_the_block_is_not_a_way_round_the_login(client, kab305, alpha, make_lease):
    """Before signing in nothing about a client's помещения is visible, the аренды included."""
    make_lease(kab305, alpha, area_m2=210)

    response, _ = open_card(client, kab305)

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_a_space_of_another_organisation_answers_as_it_did(
    reader, central, make_building, make_floor, make_space, alpha, make_lease
):
    """The аренда adds no new way to ask about another client's data (ADR 0018)."""
    theirs = make_space(make_floor(make_building(central, "ctr"), 1), "ctr-f1-a", "каб1")
    make_lease(theirs, alpha, area_m2=10)

    response, _ = open_card(reader, theirs)

    assert response.status_code == 404
