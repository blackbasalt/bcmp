"""Finding a Сторона among hundreds — the отбор and, for now, its one condition.

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
condition itself (ADR 0001, ADR 0020).
"""

import pytest
from django.urls import reverse

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
