"""Finding a Сторона among hundreds — the отбор and its five conditions.

The seam is the same as everywhere else in this section: the HTTP boundary of `/parties/`.
What is asked of the полка is asked in the address, and what is checked is which Стороны
came back, what the count line says about them, and what the bar the отбор was typed into
holds afterwards.

The foothold in the markup is the `data-party` attribute on a table row — an отбор is only a
different set of rows, and it is read the way the whole полка is. The bar itself carries
`data-search`: whether the полка can be narrowed at all is its own assertion, separate from
what any one отбор answers.

Isolation is checked here again rather than left to the section's own tests, and
deliberately: the отбор is the one thing on this screen that takes a value from the reader
and puts it into a query, so «отбором нельзя дотянуться до чужого» has to be asserted of the
conditions themselves (ADR 0001, ADR 0020).

Two of the five — «только арендаторы» and «БЦ» — are answered through an аренда in force
today, and they are checked here rather than in `leases`: what is asserted is which Стороны
came back on the screen, and «действующая на день» is checked once, where the rule lives.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse

from building_passport.models import Space

from .test_shelf import count_line, folded, parties_on, stated

pytestmark = pytest.mark.django_db


def asked(client, **conditions):
    """The полка with an отбор put to it — the conditions travel in the address."""
    response = client.get(reverse("parties:party_list"), conditions)
    return response, response.content.decode()


@pytest.fixture
def registry(downtown, alpha, petrov, make_party, make_record):
    """Three Стороны of one организация — a ТОО, an ИП and the поставщик the search is about.

    Staged as one fixture rather than per test: what a condition does is told by the rows it
    leaves standing, and that needs more than one row to leave.
    """
    fasteners = make_party("ТОО «Центр КРЕПЕЖНЫХ систем»", "090340008884")
    for party in (alpha, petrov, fasteners):
        make_record(downtown, party)
    return {"alpha": alpha, "petrov": petrov, "fasteners": fasteners}


@pytest.fixture
def tokyo_office(tokyo, make_space):
    """A помещение in the second БЦ: «кто сидит в Tokyo» needs somewhere to sit.

    The second БЦ itself is the suite's own, so that «Tokyo» means one building here and on
    the полка помещений; what stands here is only the room an аренда can be put on.
    """
    return make_space(Space.objects.get(building=tokyo, type="floor"), "tok-f3-a", "Офис")


# The search


def test_a_party_is_found_by_its_name(client, member, registry):
    """The question a сотрудник УК arrives with: «с кем мы имеем дело», and they know the
    name rather than the БИН."""
    client.force_login(member)

    _, page = asked(client, q="Петров")

    assert parties_on(page) == [str(registry["petrov"].pk)]


def test_the_name_is_searched_regardless_of_case(client, member, registry):
    """«крепеж» must find «КРЕПЕЖНЫХ»: every название here is Russian, and SQLite's `LIKE`
    folds case for ASCII alone (ADR 0014). Whoever "tidies" this back into `icontains` breaks
    the search for Russian without breaking one ASCII test."""
    client.force_login(member)

    _, page = asked(client, q="крепеж")

    assert parties_on(page) == [str(registry["fasteners"].pk)]


def test_a_party_is_found_by_its_bin(client, member, registry):
    """Название and БИН are one field: the БИН is what a Сторона is identified by, and
    whoever has it in front of them types it where they type a name."""
    client.force_login(member)

    _, page = asked(client, q="050340008889")

    assert parties_on(page) == [str(registry["alpha"].pk)]


def test_the_search_matches_a_substring(client, member, registry):
    """A substring and not a whole word, and not a beginning either: the названия come out of
    the УК's own выгрузка with their ОПФ, their quotes and their spelling, and a БИН is read
    off a счёт from wherever the eye lands on it."""
    client.force_login(member)

    _, page = asked(client, q="0340008")

    assert set(parties_on(page)) == {
        str(registry["alpha"].pk),
        str(registry["fasteners"].pk),
    }


def test_the_search_reaches_the_name_and_the_bin_and_no_further(client, member, registry, construction):
    """A word typed to find a Сторона must not also answer with every Сторона whose сфера
    деятельности happens to contain it: сфера gets a condition of its own, and it is asked
    when it is meant."""
    registry["alpha"].line_of_business = construction
    registry["alpha"].save()
    client.force_login(member)

    _, page = asked(client, q="Строительство")

    assert parties_on(page) == []


def test_a_search_that_finds_nothing_says_so(client, member, registry):
    """«ничего не нашлось» sends the reader to change the question; the count line beside it
    is what says the полка is full and the отбор is empty."""
    client.force_login(member)

    _, page = asked(client, q="Газпром")

    assert parties_on(page) == []
    assert "ничего не нашлось" in stated(page)
    assert count_line(page) == "Показано 0 из 3 Сторон"


def test_the_stated_count_follows_the_otbor(client, member, registry):
    """«Показано N из 637 Сторон»: everything after «Показано» is what is on screen, and only
    «из 637» refers to the whole полка."""
    client.force_login(member)

    _, page = asked(client, q="Петров")

    assert count_line(page) == "Показано 1 из 3 Сторон"


# The отбор lives in the address


def test_the_same_address_answers_the_same_way_twice(client, member, registry):
    """An отбор in the address is a link: reloaded, left in a tab overnight or opened by the
    colleague it was sent to, it answers with the Стороны it answered with the first time."""
    client.force_login(member)
    address = f"{reverse('parties:party_list')}?q=Петров"

    first = client.get(address).content.decode()
    again = client.get(address).content.decode()

    assert parties_on(again) == parties_on(first) == [str(registry["petrov"].pk)]
    assert count_line(again) == count_line(first)


def test_clearing_the_question_returns_the_whole_shelf(client, member, registry):
    """The полка without a question is the whole полка: an отбор lives in the address and
    nowhere else, so dropping the address drops it."""
    client.force_login(member)

    _, narrowed = asked(client, q="Петров")
    _, whole = asked(client, q="")

    assert len(parties_on(narrowed)) == 1
    assert len(parties_on(whole)) == 3


def test_a_narrowed_shelf_offers_the_way_back_to_the_whole_one(client, member, registry):
    """«Сбросить» is on screen exactly when there is a question to drop.

    It is the полка saying which of the two states it is in — «спросили» or «не спрашивали» —
    and that reading is `bcmp.shelf`'s rather than this section's, so each полка asserts it
    of itself.
    """
    client.force_login(member)

    _, page = asked(client, q="Петров")

    assert "Сбросить" in page
    assert f'href="{reverse("parties:party_list")}"' in folded(page)


def test_a_shelf_nobody_asked_anything_of_offers_nothing_to_clear(client, member, registry):
    """The other half: an отбор with no conditions filled in was not asked, and a «Сбросить»
    over it would offer to undo a question the reader never put."""
    client.force_login(member)

    _, page = asked(client)

    assert "Сбросить" not in page


def test_the_bar_holds_on_to_what_was_asked(client, member, registry):
    """The question stays in the bar after it is answered: a bar that emptied itself would
    leave the reader looking at a shortened полка with nothing on screen saying why."""
    client.force_login(member)

    _, page = asked(client, q="Петров")

    assert 'value="Петров"' in page


def test_the_bar_stands_over_a_shelf_a_question_emptied(client, member, registry):
    """That is where the question has to be corrected: an empty answer is not an empty полка."""
    client.force_login(member)

    _, page = asked(client, q="Газпром")

    assert 'data-search="parties"' in page


# Isolation


def test_the_search_does_not_reach_into_another_organisations_records(
    client, member, central, registry, make_party, make_record
):
    """The отбор can only take rows away from the answer to «чьи это учётные карточки»."""
    theirs = make_party("ТОО «Чужой крепёж»", "100340008885")
    make_record(central, theirs)
    client.force_login(member)

    _, page = asked(client, q="крепёж")

    assert parties_on(page) == []
    assert "Чужой крепёж" not in page


def test_the_search_does_not_reach_a_party_no_organisation_knows(
    client, member, registry, make_party
):
    """The registry is system-wide and the полка is not: a Сторона loaded from another base
    stays findable where an аренда is entered, and off this screen (ADR 0020)."""
    make_party("Asset-Asia ТОО", "060340008881")
    client.force_login(member)

    _, page = asked(client, q="Asset")

    assert parties_on(page) == []
    assert "Asset-Asia" not in page


# Conditions that did not read


def test_a_search_longer_than_any_name_narrows_the_shelf_to_nothing(client, member, registry):
    """An отбор that did not read narrows to nothing rather than being dropped (ADR 0014).

    Dropped, the screen would state an отбор it never performed. The refusal itself is
    `bcmp.shelf`'s and not this section's — the assertion stands here because that is where
    the reading is observable.
    """
    client.force_login(member)

    _, page = asked(client, q="К" * 256)

    assert parties_on(page) == []
    assert "В адресе указан текст длиннее" in stated(page)


def test_the_narrowed_page_carries_no_leftover_template_comments(client, member, registry):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on screen."""
    client.force_login(member)

    _, page = asked(client, q="Петров")

    assert "{#" not in page


# Сфера деятельности


def test_the_line_of_business_condition_makes_all_our_builders_one_click(
    client, member, registry, construction, catering
):
    """«Все наши строители» is one question, and asking it by название would find whoever
    happens to carry the word in theirs.

    A second сфера stands on the полка on purpose: with one, the condition would pass just
    as well answering «у кого сфера вообще заведена», which is a different question and
    would find the общепит too.
    """
    registry["alpha"].line_of_business = construction
    registry["alpha"].save()
    registry["fasteners"].line_of_business = catering
    registry["fasteners"].save()
    client.force_login(member)

    _, page = asked(client, line_of_business=str(construction.pk))

    assert parties_on(page) == [str(registry["alpha"].pk)]


# Юрлицо / физлицо


def test_the_kind_condition_tells_an_ip_from_a_too(client, member, registry):
    """ИП and ТОО are told apart when that matters — and the condition has to answer both
    ways, or it is a checkbox «физлицо» wearing a select's clothes."""
    client.force_login(member)

    _, people = asked(client, kind="person")
    _, companies = asked(client, kind="company")

    assert parties_on(people) == [str(registry["petrov"].pk)]
    assert set(parties_on(companies)) == {
        str(registry["alpha"].pk),
        str(registry["fasteners"].pk),
    }


# Только арендаторы


def test_the_tenants_condition_separates_who_pays_us_from_whom_we_pay(
    client, member, registry, first_floor, make_lease
):
    """637 of the 699 Стороны are поставщики: without this condition «наши арендаторы» is
    a question the полка cannot be asked at all."""
    make_lease(Space.objects.get(code="man-f1-b"), registry["alpha"])
    client.force_login(member)

    _, page = asked(client, tenants_only="1")

    assert parties_on(page) == [str(registry["alpha"].pk)]


def test_a_lease_that_is_over_does_not_make_a_tenant(
    client, member, registry, first_floor, make_lease, today
):
    """«Действующая сегодня» and not «когда-нибудь арендовал»: the полка speaks about today
    the way the карточка помещения and the «Арендатор» column do."""
    make_lease(
        Space.objects.get(code="man-f1-b"),
        registry["alpha"],
        valid_from=today - timedelta(days=30),
        valid_to=today - timedelta(days=1),
    )
    client.force_login(member)

    _, page = asked(client, tenants_only="1")

    assert parties_on(page) == []


def test_a_lease_with_no_end_makes_a_tenant(
    client, member, registry, first_floor, make_lease, today
):
    """An empty «по» reads «по сей день» — the ordinary бессрочная аренда (ADR 0004)."""
    make_lease(
        Space.objects.get(code="man-f1-b"), registry["alpha"], valid_from=today, valid_to=None
    )
    client.force_login(member)

    _, page = asked(client, tenants_only="1")

    assert parties_on(page) == [str(registry["alpha"].pk)]


def test_a_lease_of_another_organisations_room_does_not_make_a_tenant(
    client, member, central, registry, make_building, make_floor, make_space, make_lease
):
    """Who sees the помещение sees its аренды and nobody else's (ADR 0018): a карточка of
    DownTown answers «арендатор» about DownTown's помещения, whatever the same юрлицо rents
    at another client of the platform."""
    theirs = make_space(
        make_floor(make_building(central, "ctr", "Central City"), 1),
        "ctr-f1-a",
        "Чужой офис",
    )
    make_lease(theirs, registry["alpha"])
    client.force_login(member)

    _, page = asked(client, tenants_only="1")

    assert parties_on(page) == []


# БЦ


def test_the_building_condition_answers_who_sits_in_tokyo(
    client, member, registry, first_floor, tokyo_office, tokyo, make_lease
):
    """The question the полка помещений answers room by room, asked Стороной."""
    make_lease(tokyo_office, registry["alpha"])
    make_lease(Space.objects.get(code="man-f1-b"), registry["petrov"])
    client.force_login(member)

    _, page = asked(client, building=str(tokyo.pk))

    assert parties_on(page) == [str(registry["alpha"].pk)]


def test_a_supplier_falls_out_of_the_building_condition_entirely(
    client, member, registry, tokyo, tokyo_office, make_lease
):
    """And that is the honest answer: a поставщик is tied to no building, so «кто сидит в
    Tokyo» has nothing to say about it — the condition works through an аренда and there is
    none.

    Said as the whole list and not as «поставщика среди них нет»: an empty полка satisfies
    the second reading, and an empty полка is what a БЦ condition that narrows to nothing
    looks like.
    """
    make_lease(tokyo_office, registry["alpha"])
    client.force_login(member)

    _, page = asked(client, building=str(tokyo.pk))

    assert parties_on(page) == [str(registry["alpha"].pk)]


def test_a_lease_that_is_over_does_not_put_a_party_in_a_building(
    client, member, registry, tokyo, tokyo_office, make_lease, today
):
    """«Кто сидит в Tokyo» is asked about today: an арендатор who moved out last month is
    not somebody the reader can go and see."""
    make_lease(
        tokyo_office,
        registry["alpha"],
        valid_from=today - timedelta(days=30),
        valid_to=today - timedelta(days=1),
    )
    client.force_login(member)

    _, page = asked(client, building=str(tokyo.pk))

    assert parties_on(page) == []


def test_the_building_list_offers_the_readers_own_buildings_only(
    client, member, central, registry, tokyo, make_building
):
    """Naming another client's building on this screen would say what buildings they have
    (ADR 0001)."""
    theirs = make_building(central, "ctr", "Central City")
    client.force_login(member)

    _, page = asked(client)

    assert str(theirs.pk) not in page
    assert str(tokyo.pk) in page


# The conditions together


def test_the_conditions_compose(
    client, member, registry, downtown, construction, tokyo, tokyo_office,
    make_party, make_record, make_lease,
):
    """«Наш строитель-юрлицо Альфа, сидящий в Tokyo» is one отбор and not five screens.

    Staged so that not one of the five answers with Альфа on its own: a combination that
    each of its parts already answers would pass just as well with four of them ignored.
    """
    supply = make_party("ТОО «Альфа-Снаб»", "110340008886")
    make_record(downtown, supply)
    for party in (registry["alpha"], registry["petrov"], supply):
        party.line_of_business = construction
        party.save()
    for party in (registry["alpha"], registry["petrov"]):
        make_lease(tokyo_office, party)
    client.force_login(member)

    _, page = asked(
        client,
        q="Альфа",
        line_of_business=str(construction.pk),
        kind="company",
        tenants_only="1",
        building=str(tokyo.pk),
    )

    assert parties_on(page) == [str(registry["alpha"].pk)]


def test_the_bar_holds_on_to_every_condition_that_was_asked(
    client, member, registry, construction, tokyo
):
    """A bar that emptied itself would leave the reader looking at a shortened полка with
    nothing on screen saying why."""
    client.force_login(member)

    _, page = asked(
        client,
        line_of_business=str(construction.pk),
        kind="person",
        tenants_only="1",
        building=str(tokyo.pk),
    )

    assert f'value="{construction.pk}" selected' in folded(page)
    assert 'value="person" selected' in folded(page)
    assert f'value="{tokyo.pk}" selected' in folded(page)
    assert re.search(r'name="tenants_only"[^>]*checked', folded(page))


# Conditions that did not read


def test_a_line_of_business_that_is_not_one_narrows_the_shelf_to_nothing(
    client, member, registry
):
    """An отбор that did not read narrows to nothing rather than being dropped, and the
    screen says why (ADR 0014)."""
    client.force_login(member)

    _, page = asked(client, line_of_business="00000000-0000-0000-0000-000000000000")

    assert parties_on(page) == []
    assert "В адресе указана сфера деятельности" in stated(page)


def test_a_kind_that_is_not_a_kind_narrows_the_shelf_to_nothing(client, member, registry):
    """Left to Django's own wording the reader is told «Выберите корректный вариант» about a
    list they never touched: the value came from the address."""
    client.force_login(member)

    _, page = asked(client, kind="ооо")

    assert parties_on(page) == []
    assert "В адресе указано не юрлицо и не физлицо" in stated(page)


def test_a_building_that_did_not_read_is_said_the_same_whoever_it_belongs_to(
    client, member, central, registry, make_building
):
    """A БЦ of another client and one that does not exist answer identically: telling them
    apart would tell this reader what the other one has (ADR 0006)."""
    theirs = make_building(central, "ctr", "Central City")
    client.force_login(member)

    _, other_clients = asked(client, building=str(theirs.pk))
    _, no_such_thing = asked(client, building="00000000-0000-0000-0000-000000000000")

    assert parties_on(other_clients) == parties_on(no_such_thing) == []
    assert "В адресе указан БЦ" in stated(other_clients)
    assert stated(other_clients) == stated(no_such_thing)


# The полка around the question


def test_there_is_no_supplier_condition(client, member, registry, first_floor, make_lease):
    """«Поставщики» beside «только арендаторы» would mean «не арендатор», which the
    предметная область does not agree with: a Сторона can be both at once — an арендатор who
    also services our lifts — and a бывший арендатор is neither of the two.

    Asserted of the answer and not of the markup: a bar that merely stopped drawing the
    control while the condition still worked would leave it reachable from the address, and
    an отбор reachable from the address is an отбор.
    """
    make_lease(Space.objects.get(code="man-f1-b"), registry["alpha"])
    client.force_login(member)

    _, page = asked(client, suppliers_only="1")

    assert len(parties_on(page)) == 3
    assert "Поставщик" not in page
