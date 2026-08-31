"""Finding помещения among hundreds — the отбор and its nine conditions.

The seam is the same as everywhere else in this section: the HTTP boundary of `/rooms/`.
What is asked of the полка is asked in the address, and what is checked is which помещения
came back, what is said about them, and what the bar the отбор was typed into holds
afterwards.

The foothold in the markup is the `data-room` attribute on a table row — an отбор is only a
different set of rows, and it is read the way the whole полка is. The bar itself carries
`data-search`: whether the полка can be narrowed at all is its own assertion, separate from
what any one отбор answers.

Isolation is checked here again rather than left to the section's own tests, and
deliberately: the отбор is the one thing on this screen that takes a value from the reader
and puts it into a query, so «отбором нельзя дотянуться до чужого» has to be asserted of the
conditions themselves (ADR 0001, ADR 0006).
"""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from building_passport.models import Space

from .test_shelf import (
    count_line,
    folded,
    free_link,
    make_room,
    missing_area_link,
    rooms_on,
    rows_on,
    stated,
)

pytestmark = pytest.mark.django_db


def asked(client, **conditions):
    """The полка with an отбор put to it — the conditions travel in the address."""
    response = client.get(reverse("rooms:room_list"), conditions)
    return response, response.content.decode()


@pytest.fixture
def portfolio(first_floor, tokyo, toilet, office, manhattan, make_floor):
    """Two БЦ, three этажа and a помещение of every shape the отбор asks about.

    Staged as one fixture rather than per test: the conditions are meant to compose, and a
    fixture per condition would leave the composing tests staging the portfolio a second
    time — in a slightly different building.
    """

    def recorded(code, **fields):
        room = Space.objects.get(code=code)
        for name, value in fields.items():
            setattr(room, name, value)
        room.save()
        return room

    tokyo_third = Space.objects.get(building=tokyo, type="floor")
    return {
        # Manhattan, first floor: an office let to a tenant, of a known area.
        "office": recorded(
            "man-f1-a", subtype=office, area_m2=Decimal("120.00"),
            is_leasable=True, is_common=False,
        ),
        # Its nested part — the same building and floor, and much smaller.
        "cubicle": recorded(
            "man-f1-a1", subtype=toilet, area_m2=Decimal("4.00"),
            is_leasable=False, is_common=True,
        ),
        # Technical, and with no площадь at all — one of the 36.
        "heating": recorded("man-f1-b", is_leasable=False, is_common=False),
        # Tokyo, third floor: the санузел «санузлы Tokyo на третьем этаже» is asked for.
        "tokyo_toilet": make_room(
            tokyo_third, "tok-f3-a", "Санузел", subtype=toilet,
            area_m2=Decimal("8.00"), is_leasable=False, is_common=True,
        ),
        # Nobody classified it: both flags left unset.
        "unclassified": make_room(
            tokyo_third, "tok-f3-b", "Кладовая", is_leasable=None, is_common=None
        ),
    }


# The search


def test_a_room_is_found_by_its_name(client, member, portfolio):
    """The question a сотрудник УК arrives with: «где каб101», and they know the number
    rather than the building."""
    client.force_login(member)

    _, page = asked(client, q="Кладовая")

    assert rooms_on(page) == [str(portfolio["unclassified"].pk)]


def test_the_name_is_searched_regardless_of_case(client, member, portfolio):
    """«кладовая» must find «Кладовая»: every название here is Russian, and SQLite's `LIKE`
    folds case for ASCII alone (ADR 0014)."""
    client.force_login(member)

    _, page = asked(client, q="КЛАДОВАЯ")

    assert rooms_on(page) == [str(portfolio["unclassified"].pk)]


def test_the_search_matches_a_substring(client, member, portfolio):
    """«101» finds «каб101», «каб101вход» and «каб101вправо» together — they are one
    кабинет's parts, and whoever looks for the кабинет wants all of them."""
    client.force_login(member)

    _, page = asked(client, q="101")

    assert set(rooms_on(page)) == {str(portfolio["office"].pk), str(portfolio["cubicle"].pk)}


def test_a_room_is_found_by_its_code(client, member, portfolio):
    """A path id left in a план's `unmatched_ids` is a код, and it has to be lookupable."""
    client.force_login(member)

    _, page = asked(client, q="tok-f3-b")

    assert rooms_on(page) == [str(portfolio["unclassified"].pk)]


def test_the_search_reaches_no_further_than_the_name_and_the_code(client, member, portfolio):
    """Название and код only. Назначение has a condition of its own, and a search that also
    matched it would answer «нашлось сорок» to a word typed to find one помещение."""
    client.force_login(member)

    _, page = asked(client, q="Санузел")

    assert rooms_on(page) == [str(portfolio["tokyo_toilet"].pk)]
    assert str(portfolio["cubicle"].pk) not in page


def test_a_search_matching_nothing_shows_no_rows_at_all(client, member, portfolio):
    client.force_login(member)

    response, page = asked(client, q="венткамера")

    assert response.status_code == 200
    assert rooms_on(page) == []


# The conditions one at a time


def test_the_building_condition_shows_that_buildings_rooms_alone(client, member, portfolio):
    """«покажи всё по Tokyo» is one control — and it reaches вложенные помещения too,
    because `building_id` is set on every one of them."""
    client.force_login(member)

    _, page = asked(client, building=str(portfolio["tokyo_toilet"].building_id))

    assert set(rooms_on(page)) == {
        str(portfolio["tokyo_toilet"].pk),
        str(portfolio["unclassified"].pk),
    }


def test_the_building_list_offers_the_readers_own_buildings_only(
    client, member, central, portfolio, make_building
):
    """A БЦ this reader may not see is not on offer — naming it would name another client's
    building on their screen (ADR 0001)."""
    theirs = make_building(central, "ctr", "Central City")
    client.force_login(member)

    _, page = asked(client)

    assert str(portfolio["tokyo_toilet"].building_id) in page
    assert str(theirs.pk) not in page


def test_the_kind_condition_makes_the_leasing_question_one_click(client, member, portfolio):
    client.force_login(member)

    _, page = asked(client, kind="leasable")

    assert rooms_on(page) == [str(portfolio["office"].pk)]


def test_the_kind_condition_finds_the_common_areas(client, member, portfolio):
    client.force_login(member)

    _, page = asked(client, kind="common")

    assert set(rooms_on(page)) == {
        str(portfolio["cubicle"].pk),
        str(portfolio["tokyo_toilet"].pk),
    }


def test_the_technical_kind_takes_in_what_nobody_classified(client, member, portfolio):
    """Техническое is the remainder, and an unset flag means "no" — so a помещение nobody
    classified answers here. That is precisely why «вид не заведён» is a condition of its
    own: without it these помещения are indistinguishable from the ИТП."""
    client.force_login(member)

    _, page = asked(client, kind="technical")

    assert set(rooms_on(page)) == {
        str(portfolio["heating"].pk),
        str(portfolio["unclassified"].pk),
    }


def test_the_purpose_condition_makes_show_me_all_the_toilets_one_click(
    client, member, portfolio
):
    client.force_login(member)

    _, page = asked(client, purpose=str(portfolio["tokyo_toilet"].subtype_id))

    assert set(rooms_on(page)) == {
        str(portfolio["cubicle"].pk),
        str(portfolio["tokyo_toilet"].pk),
    }


def test_the_floor_condition_means_that_floor_of_every_building(
    client, member, portfolio, manhattan, make_floor
):
    """«всё на третьем» across БЦ means the third floors of all of them — the right reading
    for a полка that spans the portfolio."""
    upstairs = make_room(make_floor(manhattan, 3), "man-f3-a", "каб301")
    client.force_login(member)

    _, page = asked(client, floor=3)

    assert set(rooms_on(page)) == {
        str(upstairs.pk),
        str(portfolio["tokyo_toilet"].pk),
        str(portfolio["unclassified"].pk),
    }


def test_the_area_range_answers_the_leasing_question(client, member, portfolio):
    """«офисы больше 100 м²» is askable."""
    client.force_login(member)

    _, page = asked(client, area_from="100")

    assert rooms_on(page) == [str(portfolio["office"].pk)]


def test_the_area_range_narrows_from_both_ends(client, member, portfolio):
    client.force_login(member)

    _, page = asked(client, area_from="5", area_to="10")

    assert rooms_on(page) == [str(portfolio["tokyo_toilet"].pk)]


def test_the_area_range_does_not_reach_a_room_with_no_area(client, member, portfolio):
    """«от» and «до» cannot find what is not filled in — and silently that would read as
    «таких нет» while the truth is «мы не знаем» (ADR 0015)."""
    client.force_login(member)

    _, page = asked(client, area_from="0")

    assert str(portfolio["heating"].pk) not in rooms_on(page)


def test_the_missing_area_condition_asks_the_audit_question(client, member, portfolio):
    """«у каких помещений не заведена площадь» — asked from the same полка as everything
    else, and it is the only condition that can ask it."""
    client.force_login(member)

    _, page = asked(client, no_area="1")

    assert set(rooms_on(page)) == {
        str(portfolio["heating"].pk),
        str(portfolio["unclassified"].pk),
    }


def test_the_missing_kind_condition_finds_what_nobody_classified(client, member, portfolio):
    """Помещения nobody classified are findable before they quietly count as технические.

    It is not a fourth вид: the ИТП is technical because both flags say "no", and it stays
    out of this answer.
    """
    client.force_login(member)

    _, page = asked(client, no_kind="1")

    assert rooms_on(page) == [str(portfolio["unclassified"].pk)]


def test_the_free_condition_answers_what_stands_empty(
    client, member, first_floor, portfolio, alpha, make_lease
):
    """«Что стоит пустым» — one control rather than 324 карточки."""
    let = make_room(
        first_floor, "man-f1-c", "каб305",
        is_leasable=True, is_common=False, area_m2=Decimal("300.00"),
    )
    make_lease(let, alpha)
    client.force_login(member)

    _, page = asked(client, free="1")

    assert rooms_on(page) == [str(portfolio["office"].pk)]


def test_a_room_with_a_lease_in_force_is_not_free(client, member, portfolio, alpha, make_lease):
    """Свободно means not a single действующая аренда: one is enough to take a помещение off
    the answer, whatever share of it that аренда covers."""
    make_lease(portfolio["office"], alpha)
    client.force_login(member)

    _, page = asked(client, free="1")

    assert rooms_on(page) == []


def test_a_room_with_only_past_leases_is_free(
    client, member, portfolio, alpha, make_lease, today
):
    """The арендатор who left is not standing in the помещение: the полка speaks about today,
    and today the кабинет is empty."""
    make_lease(
        portfolio["office"], alpha,
        valid_from=today - timedelta(days=60), valid_to=today - timedelta(days=30),
    )
    client.force_login(member)

    _, page = asked(client, free="1")

    assert rooms_on(page) == [str(portfolio["office"].pk)]


def test_a_room_that_was_never_on_offer_is_not_free(client, member, portfolio):
    """МОП свободным не бывает — иначе полка отчиталась бы венткамерой как возможностью
    сдать. Both halves of «свободно» are asked, and the first is about the помещение."""
    client.force_login(member)

    _, page = asked(client, free="1")

    shown = rooms_on(page)
    for empty in ("cubicle", "heating", "tokyo_toilet", "unclassified"):
        assert str(portfolio[empty].pk) not in shown


def test_the_same_address_answers_the_same(client, member, portfolio):
    """The condition travels in the address like the eight others, and the address is a link:
    reloaded, left in a tab overnight or opened by the colleague it was sent to, it answers
    with the помещения it answered with the first time."""
    client.force_login(member)
    address = f"{reverse('rooms:room_list')}?free=1"

    first = client.get(address).content.decode()
    again = client.get(address).content.decode()

    assert rooms_on(again) == rooms_on(first) == [str(portfolio["office"].pk)]
    assert count_line(again) == count_line(first)


# The conditions together


def test_the_conditions_compose(client, member, portfolio):
    """«санузлы Tokyo на третьем этаже» is one отбор and not three screens."""
    client.force_login(member)

    _, page = asked(
        client,
        building=str(portfolio["tokyo_toilet"].building_id),
        floor=3,
        purpose=str(portfolio["tokyo_toilet"].subtype_id),
    )

    assert rooms_on(page) == [str(portfolio["tokyo_toilet"].pk)]


def test_clearing_the_question_returns_the_whole_shelf(client, member, portfolio):
    """The полка without a question is the whole полка: an отбор lives in the address and
    nowhere else, so dropping the address drops it."""
    client.force_login(member)

    _, narrowed = asked(client, q="Кладовая")
    _, whole = asked(client, q="", kind="", building="", purpose="", floor="")

    assert len(rooms_on(narrowed)) == 1
    assert len(rooms_on(whole)) == 5


def test_the_bar_holds_on_to_what_was_asked(client, member, portfolio):
    """The question stays in the bar after it is answered.

    A bar that emptied itself would leave the reader looking at a shortened полка with
    nothing on screen saying why it is short — and the way to change one condition would be
    to type all the others again.
    """
    client.force_login(member)

    _, page = asked(
        client,
        q="Санузел",
        building=str(portfolio["tokyo_toilet"].building_id),
        kind="common",
        purpose=str(portfolio["tokyo_toilet"].subtype_id),
        floor="3",
        area_from="5",
        area_to="10",
        no_area="1",
        no_kind="1",
        free="1",
    )

    assert 'value="Санузел"' in page
    assert f'value="{portfolio["tokyo_toilet"].building_id}" selected' in page
    assert 'value="common" selected' in page
    assert f'value="{portfolio["tokyo_toilet"].subtype_id}" selected' in page
    assert 'name="floor" value="3"' in folded(page)
    assert 'name="area_from" value="5"' in folded(page)
    assert 'name="area_to" value="10"' in folded(page)
    assert re.search(r'name="no_area"[^>]*checked', folded(page))
    assert re.search(r'name="no_kind"[^>]*checked', folded(page))
    assert re.search(r'name="free"[^>]*checked', folded(page))


# What the screen says about the answer


def test_the_stated_count_follows_the_otbor(client, member, portfolio):
    """«Показано N из 583»: everything after «Показано» is what is on screen, and only «из
    583» refers to the whole полка."""
    client.force_login(member)

    _, page = asked(client, q="Кладовая")

    assert "Показано 1 из 5 помещений" in count_line(page)


def test_the_missing_area_figure_counts_only_what_is_on_screen(client, member, portfolio):
    """The line must not contradict the table above it."""
    client.force_login(member)

    _, page = asked(client, kind="leasable")

    assert "площадь не заведена" not in count_line(page)


def test_the_missing_area_link_keeps_the_rest_of_the_otbor(client, member, portfolio):
    """Someone who narrowed the полка to Tokyo and then asks where the площадь is missing
    means "in Tokyo"."""
    client.force_login(member)

    _, page = asked(client, building=str(portfolio["tokyo_toilet"].building_id))

    followed = client.get(missing_area_link(page)).content.decode()

    assert rooms_on(followed) == [str(portfolio["unclassified"].pk)]


def test_the_free_figure_counts_only_what_is_on_screen(client, member, portfolio):
    """The line must not contradict the table above it: narrowed to МОПы there is nothing
    свободное on screen, and the figure counts none of the помещения that are not."""
    client.force_login(member)

    _, page = asked(client, kind="common")

    assert "свободно" not in count_line(page)


def test_the_free_link_keeps_the_rest_of_the_otbor(client, member, portfolio, tokyo):
    """Someone who narrowed the полка to Tokyo and then asks what stands empty means "in
    Tokyo"."""
    tokyo_office = make_room(
        Space.objects.get(building=tokyo, type="floor"), "tok-f3-c", "каб301",
        is_leasable=True, is_common=False, area_m2=Decimal("50.00"),
    )
    client.force_login(member)

    _, page = asked(client, building=str(tokyo.pk))

    followed = client.get(free_link(page)).content.decode()

    assert rooms_on(followed) == [str(tokyo_office.pk)]


def test_a_figure_that_is_already_the_question_links_to_the_same_address(
    client, member, portfolio
):
    """Clicking «свободно N» on a полка already narrowed to свободные changes nothing.

    The condition is set, not added to: an address carrying it twice would grow a copy on
    every click and stop being the link the reader means to send.
    """
    client.force_login(member)

    _, page = asked(client, free="1")

    assert free_link(page).count("free=1") == 1


def test_a_question_that_matched_nothing_says_so_rather_than_that_nothing_was_entered(
    client, member, portfolio
):
    """«ничего не нашлось» sends the reader to change the question; «помещения не заведены»
    sends them to whoever loads them, and one screen for both would send them to the wrong
    one half the time."""
    client.force_login(member)

    _, page = asked(client, q="венткамера")

    assert "ничего не нашлось" in stated(page)
    assert "Помещения не заведены" not in stated(page)


def test_an_emptied_shelf_still_says_the_size_of_what_was_narrowed(client, member, portfolio):
    """«Показано 0 из 5 помещений» is what tells the reader the полка was full and their
    question was empty. «Ничего не нашлось» alone leaves them not knowing whether there was
    ever anything to find."""
    client.force_login(member)

    _, page = asked(client, q="венткамера")

    assert "Показано 0 из 5 помещений" in count_line(page)


def test_the_bar_stands_on_a_shelf_that_a_question_emptied(client, member, portfolio):
    """That is where the question has to be corrected."""
    client.force_login(member)

    _, page = asked(client, q="венткамера")

    assert 'data-search="rooms"' in page


# Isolation


def test_the_search_does_not_reach_into_another_organisations_rooms(
    client, member, central, portfolio, make_building, make_floor
):
    """The отбор can only take rows away from the answer to «чьи это помещения»."""
    make_room(make_floor(make_building(central, "ctr", "Central City"), 1),
              "ctr-f1-a", "Кладовая чужая")
    client.force_login(member)

    _, page = asked(client, q="Кладовая")

    assert rooms_on(page) == [str(portfolio["unclassified"].pk)]
    assert "Кладовая чужая" not in page


def test_a_building_of_another_organisation_selects_nothing(
    client, member, central, portfolio, make_building, make_floor
):
    """Not the reader's whole полка: a dropped condition would state an отбор that was not
    performed (ADR 0014)."""
    theirs = make_building(central, "ctr", "Central City")
    make_room(make_floor(theirs, 1), "ctr-f1-a", "Чужая серверная")
    client.force_login(member)

    _, page = asked(client, building=str(theirs.pk))

    assert rooms_on(page) == []
    assert "Чужая серверная" not in page


def test_a_room_of_another_organisation_is_unreachable_by_direct_address(
    client, member, central, portfolio, make_building, make_floor
):
    """Naming it in the search finds nothing, and its own key names nothing on this screen."""
    theirs = make_room(make_floor(make_building(central, "ctr", "Central City"), 1),
                       "ctr-f1-a", "Чужая серверная")
    client.force_login(member)

    _, page = asked(client, q="ctr-f1-a")

    assert rooms_on(page) == []
    assert str(theirs.pk) not in page


# Conditions that did not read


def test_a_kind_that_is_not_a_kind_selects_nothing_and_is_said_on_the_screen(
    client, member, portfolio
):
    """An empty полка beneath a bar standing on «Любой вид» reads as a breakage: the отбор
    that emptied it came from the address and is not in the select."""
    client.force_login(member)

    _, page = asked(client, kind="какое-нибудь-прочее")

    assert rooms_on(page) == []
    assert "В адресе указан вид, которого нет в списке" in stated(page)


def test_a_building_that_did_not_read_is_said_the_same_whoever_it_belongs_to(
    client, member, central, portfolio, make_building
):
    """One wording for both readings: telling a missing БЦ from another client's would tell
    this reader what the other one has (ADR 0006)."""
    theirs = make_building(central, "ctr", "Central City")
    client.force_login(member)

    _, other_clients = asked(client, building=str(theirs.pk))
    _, no_such_thing = asked(client, building="00000000-0000-0000-0000-000000000000")

    assert "В адресе указан БЦ, которого нет в списке" in stated(other_clients)
    assert "В адресе указан БЦ, которого нет в списке" in stated(no_such_thing)
    assert "Central City" not in other_clients


def test_a_purpose_that_is_not_a_purpose_selects_nothing_and_is_said_on_the_screen(
    client, member, portfolio
):
    client.force_login(member)

    _, page = asked(client, purpose="123456")

    assert rooms_on(page) == []
    assert "В адресе указано назначение, которого нет в списке" in stated(page)


def test_a_floor_that_is_not_a_number_selects_nothing_and_is_said_on_the_screen(
    client, member, portfolio
):
    client.force_login(member)

    _, page = asked(client, floor="третий")

    assert rooms_on(page) == []
    assert "В адресе указан этаж, который не читается числом" in stated(page)


def test_an_area_that_is_not_a_number_selects_nothing_and_is_said_on_the_screen(
    client, member, portfolio
):
    client.force_login(member)

    _, page = asked(client, area_from="сто")

    assert rooms_on(page) == []
    assert "В адресе указана площадь, которая не читается числом" in stated(page)


# The полка around the question


def test_there_is_no_status_condition(client, member, portfolio):
    """`status` is filled on 0 of 583 помещений, and a control that can only ever answer
    «ничего не нашлось» teaches the reader that the bar lies."""
    client.force_login(member)

    _, page = asked(client)

    assert "Статус" not in page


def test_there_is_no_let_condition(client, member, portfolio):
    """«Сдано» would only ever mean «не свободно», and «сдано целиком» would need a threshold
    the предметная область does not have — the bar must not offer a second handle able to say
    one and the same thing."""
    client.force_login(member)

    _, page = asked(client)

    assert "Сдано" not in page
    assert "сдано" not in page


def test_the_rows_of_a_narrowed_shelf_read_as_they_always_do(client, member, portfolio):
    """An отбор changes which rows are shown and nothing about how one is read."""
    client.force_login(member)

    _, page = asked(client, q="101")
    row = rows_on(page)[str(portfolio["cubicle"].pk)]

    assert "man-f1-a1" in row
    assert "каб101вход" in row  # the «Внутри» column stands as it does on the whole полка
    assert "МОП" in row
    assert "4,00" in row


def test_the_narrowed_page_carries_no_leftover_template_comments(client, member, portfolio):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on screen."""
    client.force_login(member)

    _, page = asked(client, q="101")

    assert "{#" not in page
