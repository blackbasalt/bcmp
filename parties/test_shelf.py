"""The «Стороны» section — what a сотрудник УК sees over HTTP.

There is one seam: the HTTP boundary of `/parties/`. The tests walk the named address with
the test client on behalf of a user with a known membership and check what is observable —
which Стороны are on screen, in what order, what is written in a row, what the count line
says and what code the request answers with. Below HTTP there is no seam: the isolation
chokepoint of the учётная карточка, the отбор and the counting of арендованных помещений
are all checked through this screen, because that is how they are read.

The foothold in the markup is the `data-party` attribute on a table row, mirroring
`data-room` on the полка помещений and `data-document` on the полка документов. That is the
screen's contract: it shows which Стороны are displayed and in what order, and a rebuild of
the layout does not rewrite the test suite.

A row is a учётная карточка and names the Сторона it is about, so a Сторона two of the
reader's clients both know is two rows carrying one `data-party`. That is not a clash to be
worked around — it is what a полка карточек is (ADR 0020) — hence `rows_for` beside
`rows_on`.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from building_passport.models import Space
from dictionary.models import DictProfessionalHoliday
from parties.models import ContactPerson

pytestmark = pytest.mark.django_db

#: A table row together with the Сторона's key: the screen's contract and everything
#: written in the row. It is not read by parsing tags — what is asked of a row is not its
#: structure but its text, and that text must be found in the row itself, not somewhere on
#: the page.
ROW = re.compile(r'<tr[^>]*data-party="(?P<key>[^"]+)"[^>]*>(?P<cells>.*?)</tr>', re.DOTALL)

#: The cells of one row, in the order they stand in it — for the questions about a
#: particular column, where the row's text as a whole cannot tell «Название» from «БИН/ИИН».
CELL = re.compile(r"<t[dh][^>]*>(?P<text>.*?)</t[dh]>", re.DOTALL)


def stated(text):
    """The text on a single line: a phrase must not break on a line wrap in the markup."""
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def folded(markup):
    """The markup on a single line, tags and all: an attribute and its value must not be
    told apart by a line wrap when a test looks for the two together."""
    return " ".join(markup.split())


def parties_on(page):
    """The keys of the Стороны shown, top to bottom — the order of the rows is checked too."""
    return [row["key"] for row in ROW.finditer(page)]


def rows_on(page):
    """The table rows by Сторона key: what is written in each of them.

    One row per Сторона, which is what a полка of one организация holds. Where two clients
    of one reader both know a Сторона, `rows_for` is the one to ask.
    """
    return {row["key"]: stated(row["cells"]) for row in ROW.finditer(page)}


def rows_for(page, party):
    """Every row about one Сторона — the two карточки case, and only that case."""
    return [stated(row["cells"]) for row in ROW.finditer(page) if row["key"] == str(party.pk)]


def cells_on(page):
    """The same rows, cell by cell: key → the list of cells as they stand.

    The text and not the markup: the rows of this полка carry neither a link nor a form —
    that is `row_markup`'s assertion — so there is nothing in a cell that its text does not
    say. The полка помещений keeps a `raw` reading of its cells because a название there
    leads to the экран этажа; a parameter kept here for the day one of these cells does the
    same would be a knob nothing turns.
    """
    return {
        row["key"]: [stated(cell["text"]) for cell in CELL.finditer(row["cells"])]
        for row in ROW.finditer(page)
    }


def headings_on(page):
    """The column headings, left to right — what the cells of a row are to be read against."""
    head = re.search(r"<thead>(.*?)</thead>", page, re.DOTALL)
    return [stated(cell["text"]) for cell in CELL.finditer(head.group(1))] if head else []


def cell_under(page, party, heading):
    """What one column says about one Сторона, found by the heading it stands under.

    By the heading and not by a fixed position: a column inserted before another one must
    not turn an assertion about «Арендует» into a question about a сфера деятельности.
    """
    return cells_on(page)[str(party.pk)][headings_on(page).index(heading)]


def rented_cell(page, party):
    """What the «Арендует» column says about one Сторона."""
    return cell_under(page, party, "Арендует")


def row_markup(page, party):
    """One row as it stands, tags and all — for what a row must not carry."""
    return next(row["cells"] for row in ROW.finditer(page) if row["key"] == str(party.pk))


def count_line(page):
    """The line saying how much of the полка is on screen.

    Found by `data-count`, the screen's contract for it, and not by the classes it wears:
    it stands beneath the table on a полка that has rows and beneath the warning on one an
    отбор emptied, and both are the same line.
    """
    found = re.search(r'data-count="parties"[^>]*>(.*?)</p>', page, re.DOTALL)
    return stated(found.group(1)) if found else ""


def shelf(client):
    response = client.get(reverse("parties:party_list"))
    return response, response.content.decode()


@pytest.fixture
def our_parties(downtown, alpha, petrov, make_record):
    """The two Стороны DownTown Management keeps a карточка on — the ordinary полка."""
    make_record(downtown, alpha)
    make_record(downtown, petrov)
    return alpha, petrov


@pytest.fixture
def shelf_page(client, member, our_parties):
    client.force_login(member)
    _, page = shelf(client)
    return page


# Access and isolation


def test_a_party_without_a_record_of_mine_stays_off_the_shelf(
    client, member, our_parties, make_party
):
    """The полка Сторон is a полка учётных карточек (ADR 0020): the 62 Стороны loaded from
    other bases stay in the registry, findable when an аренда is entered, and on nobody's
    полка."""
    stranger = make_party("Asset-Asia ТОО", "060340008881")
    client.force_login(member)

    response, page = shelf(client)

    assert response.status_code == 200
    assert str(stranger.pk) not in parties_on(page)
    assert "Asset-Asia" not in page


def test_a_record_of_another_organisation_stays_off_the_shelf(
    client, member, central, our_parties, make_party, make_record
):
    """Client isolation on screen — the same chokepoint every other полка obeys, and the
    first one that does not come for free: a Сторона has no организация, a карточка has
    (ADR 0020)."""
    theirs = make_party("ТОО «Чужие поставки»", "070340008882")
    make_record(central, theirs)
    client.force_login(member)

    _, page = shelf(client)

    assert str(theirs.pk) not in parties_on(page)
    assert "Чужие поставки" not in page


def test_one_party_known_to_two_organisations_shows_only_my_record(
    client, member, central, alpha, make_record
):
    """Kaspi Bank supplies two управляющие компании at once, and it is one Сторона: what
    the second one knows about her must not arrive on my полка."""
    make_record(central, alpha)
    client.force_login(member)

    _, page = shelf(client)

    assert parties_on(page) == []


def test_an_anonymous_visitor_is_sent_to_login(client, our_parties):
    """The полка is not a way round the login every other screen requires."""
    response = client.get(reverse("parties:party_list"))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_a_superuser_reads_every_organisations_records(
    client, django_user_model, central, our_parties, make_party, make_record
):
    """A superuser reads on everyone's behalf — the same rule as on every other screen."""
    theirs = make_party("ТОО «Чужие поставки»", "070340008882")
    make_record(central, theirs)
    client.force_login(django_user_model.objects.create_superuser("root"))

    _, page = shelf(client)

    assert "ТОО «Альфа»" in page
    assert "Чужие поставки" in page


# What is on the полка


def test_the_shelf_opens_with_every_party_the_reader_may_see(shelf_page):
    """The screen starts by telling the reader how much there is: no отбор, the whole полка."""
    assert len(parties_on(shelf_page)) == 2


def test_the_rows_are_ordered_by_name(
    client, member, downtown, our_parties, alpha, petrov, make_party, make_record
):
    """The полка is read by eye, hunting for a Сторона on it, and the alphabet is the one
    order that helps: the order in which the выгрузка happened to load 637 поставщиков helps
    nobody. The rows are staged out of that order on purpose, so that the assertion is about
    the screen's ordering and not about the order of creation.
    """
    beta = make_party("ТОО «Бета»", "080340008883")
    make_record(downtown, beta)
    client.force_login(member)

    _, page = shelf(client)

    assert parties_on(page) == [str(petrov.pk), str(alpha.pk), str(beta.pk)]


# What a row says


def test_a_row_says_what_is_needed_to_judge_a_party_without_opening_it(
    client, member, downtown, alpha, construction, make_record, first_floor, make_lease
):
    """Название, БИН/ИИН, сфера деятельности and «Арендует N помещений» — all in the row."""
    alpha.line_of_business = construction
    alpha.save()
    make_record(downtown, alpha)
    make_lease(Space.objects.get(code="man-f1-b"), alpha)
    client.force_login(member)

    _, page = shelf(client)
    row = rows_on(page)[str(alpha.pk)]

    assert "ТОО «Альфа»" in row
    assert "050340008889" in row
    assert "Строительство" in row
    assert "1 помещение" in row


def test_a_party_with_no_line_of_business_shows_a_dash(shelf_page, alpha):
    """None of the 699 Стороны has a сфера filled in, and «не заведено» must not read as a
    Сторона that does nothing."""
    assert cell_under(shelf_page, alpha, "Сфера деятельности") == "— нет данных"


def test_the_rented_rooms_are_counted_in_rooms_and_never_in_metres(
    client, member, our_parties, alpha, first_floor, make_lease
):
    """A Сторона sitting in a помещение inside another помещение would be counted twice in
    metres (ADR 0015, ADR 0019). Помещения cannot be counted twice: each is one row of the
    полка помещений, and each is one here."""
    entrance = Space.objects.get(code="man-f1-a")
    nested = Space.objects.get(code="man-f1-a1")
    for room in (entrance, nested):
        room.area_m2 = Decimal("40.00")
        room.save()
        make_lease(room, alpha, area_m2=Decimal("40.00"))
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "2 помещения"
    assert "м²" not in rows_on(page)[str(alpha.pk)]
    assert "80" not in rows_on(page)[str(alpha.pk)]


def test_a_party_renting_nothing_shows_a_bare_dash(shelf_page, alpha):
    """The dash reads «ничего не арендует», not «нет данных»: a поставщик renting nothing is
    an answer, and 637 of the 699 Стороны are поставщики."""
    assert rented_cell(shelf_page, alpha) == "—"


def test_two_leases_of_one_room_count_the_room_once(
    client, member, our_parties, alpha, first_floor, make_lease
):
    """The column counts помещения, not аренды: taking another 20 м² in the middle of a
    срок is a second аренда of the same помещение (ADR 0017), and «2 помещения» would report
    a room the арендатор does not have."""
    room = Space.objects.get(code="man-f1-b")
    make_lease(room, alpha, area_m2=Decimal("40.00"))
    make_lease(room, alpha, area_m2=Decimal("20.00"))
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "1 помещение"


def test_a_lease_that_is_over_is_not_counted(
    client, member, our_parties, alpha, first_floor, make_lease, today
):
    """The полка speaks about today the way every other screen does."""
    make_lease(
        Space.objects.get(code="man-f1-b"),
        alpha,
        valid_from=today - timedelta(days=30),
        valid_to=today - timedelta(days=1),
    )
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "—"


def test_a_lease_that_has_not_begun_is_not_counted(
    client, member, our_parties, alpha, first_floor, make_lease, today
):
    """A продление entered while the current срок runs is not a помещение occupied today."""
    make_lease(Space.objects.get(code="man-f1-b"), alpha, valid_from=today + timedelta(days=1))
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "—"


def test_a_lease_with_no_end_is_in_force(
    client, member, our_parties, alpha, first_floor, make_lease, today
):
    """An empty «по» reads «по сей день» — the ordinary бессрочная аренда (ADR 0004)."""
    make_lease(Space.objects.get(code="man-f1-b"), alpha, valid_from=today, valid_to=None)
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "1 помещение"


def test_each_row_counts_the_rooms_of_its_own_party(
    client, member, our_parties, alpha, petrov, first_floor, make_lease
):
    """One column asked of the whole полка must not spread one Сторона's аренды over the
    rows beside it."""
    make_lease(Space.objects.get(code="man-f1-a"), alpha)
    make_lease(Space.objects.get(code="man-f1-b"), petrov)
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "1 помещение"
    assert rented_cell(page, petrov) == "1 помещение"


def test_a_lease_of_another_organisations_room_is_not_counted(
    client, member, central, our_parties, alpha, first_floor,
    make_building, make_floor, make_space, make_lease,
):
    """Who sees the помещение sees its аренды and nobody else's (ADR 0018): a карточка of
    DownTown counts DownTown's помещения, whatever the same Сторона rents at another client
    of the platform."""
    theirs = make_space(
        make_floor(make_building(central, "ctr", "Central City"), 1),
        "ctr-f1-a",
        "Чужая серверная",
    )
    make_lease(Space.objects.get(code="man-f1-b"), alpha)
    make_lease(theirs, alpha)
    client.force_login(member)

    _, page = shelf(client)

    assert rented_cell(page, alpha) == "1 помещение"


def test_the_rented_column_costs_no_query_per_row(
    client, member, downtown, our_parties, alpha, first_floor,
    make_party, make_record, make_lease, django_assert_num_queries,
):
    """One query for the whole column, as `tenants_of_each_room` on the полка помещений is:
    the полка carries 637 rows, and a question asked per row is a question asked 637 times."""
    client.force_login(member)
    # Read once before counting: the first request of a session pays for what the column is
    # not about — the session row — and what is asked here is what a row costs.
    shelf(client)
    with CaptureQueriesContext(connection) as few_rows:
        shelf(client)

    room = Space.objects.get(code="man-f1-b")
    for number in range(20):
        party = make_party(f"ТОО «Соседи-{number}»", f"9901400{number:05d}")
        make_record(downtown, party)
        make_lease(room, party)

    with django_assert_num_queries(len(few_rows)):
        _, page = shelf(client)

    assert len(parties_on(page)) == 22


def test_the_shelf_totals_nothing(client, member, our_parties, alpha, petrov, first_floor, make_lease):
    """No итог under the columns: metres would count a Сторона in a вложенное помещение
    twice (ADR 0019), and there is no line of the table where a sum could stand."""
    for code, tenant in (("man-f1-a", alpha), ("man-f1-b", petrov)):
        make_lease(Space.objects.get(code=code), tenant, area_m2=Decimal("40.00"))
    client.force_login(member)

    _, page = shelf(client)

    assert "<tfoot" not in page
    assert "Итого" not in page


# The organisation column


def test_a_member_of_two_organisations_sees_each_record_under_its_own_organisation(
    client, both_clients, downtown, central, alpha, petrov, make_record
):
    """Two clients for one employee — two полки, not one common heap.

    This must be said in the row itself: the names of both organisations somewhere on the
    page distinguish nothing — they would match even with their places swapped.
    """
    make_record(downtown, alpha)
    make_record(central, petrov)
    client.force_login(both_clients)

    _, page = shelf(client)
    rows = rows_on(page)

    assert downtown.name in rows[str(alpha.pk)]
    assert central.name not in rows[str(alpha.pk)]
    assert central.name in rows[str(petrov.pk)]


def test_the_organisation_column_holds_when_the_second_client_has_nothing_loaded(
    client, both_clients, downtown, central, alpha, make_record
):
    """The column is asked about the reader and not about what is shown — and this is
    exactly when whoever handles two clients most needs to know whose полка they are on."""
    make_record(downtown, alpha)
    client.force_login(both_clients)

    _, page = shelf(client)

    assert "Организация" in headings_on(page)
    assert downtown.name in rows_on(page)[str(alpha.pk)]


def test_one_party_known_to_both_clients_is_a_row_for_each(
    client, both_clients, downtown, central, alpha, make_record
):
    """The полка is a полка карточек: one юрлицо known to two of the reader's clients is two
    учётные карточки, and each of them is the reader's own (ADR 0020)."""
    make_record(downtown, alpha)
    make_record(central, alpha)
    client.force_login(both_clients)

    _, page = shelf(client)
    rows = rows_for(page, alpha)

    assert len(rows) == 2
    assert any(downtown.name in row for row in rows)
    assert any(central.name in row for row in rows)


def test_a_member_of_one_organisation_gets_no_organisation_column(shelf_page, downtown):
    """A column repeating one word 637 times would take the width and say nothing."""
    assert "Организация" not in headings_on(shelf_page)
    assert downtown.name not in shelf_page


# The count line


def test_the_count_says_how_much_of_the_shelf_is_on_screen(shelf_page):
    """The question asked first, answered by a phrase and not by the length of the list."""
    assert count_line(shelf_page) == "Показано 2 из 2 Сторон"


def test_the_count_agrees_with_the_numeral(client, member, downtown, alpha, make_record):
    """«из 1 Стороны» and not «из 1 Сторон»: «из» takes the genitive, so the word has two
    forms here and not the three a nominative would need."""
    make_record(downtown, alpha)
    client.force_login(member)

    _, page = shelf(client)

    assert count_line(page) == "Показано 1 из 1 Стороны"


# Empty states


def test_a_shelf_with_no_parties_says_who_enters_them(client, member):
    """Told who acts: the карточка is kept by the организация itself, so the reader is sent
    to their own администратор организации and not to support (ADR 0021)."""
    client.force_login(member)

    _, page = shelf(client)

    assert parties_on(page) == []
    assert "Стороны не заведены" in stated(page)
    assert "администратор организации" in stated(page)


def test_a_shelf_with_no_parties_says_so_even_with_a_condition_in_the_address(client, member):
    """«ничего не нашлось» would send this reader to fix a question that was never the
    problem: there is nothing on the полка to find, whatever is asked of it.

    The полка follows помещения and not документы here: which of the two empty states it is
    follows from the size of the un-narrowed полка and not from whether anything was asked.
    """
    client.force_login(member)

    page = client.get(reverse("parties:party_list"), {"q": "Альфа"}).content.decode()

    assert "Стороны не заведены" in stated(page)
    assert "ничего не нашлось" not in stated(page)
    assert 'data-search="parties"' not in page


def test_the_bar_is_not_offered_on_a_shelf_with_no_parties(client, member):
    """Narrowing a nothing is an offer that answers nothing."""
    client.force_login(member)

    _, page = shelf(client)

    assert 'data-search="parties"' not in page


# The whole полка at once


def test_the_shelf_is_rendered_whole_with_no_pagination(
    client, member, downtown, our_parties, make_party, make_record
):
    """The browser's own find must work across every row, and a shared link lose nothing."""
    for number in range(30):
        make_record(downtown, make_party(f"ТОО «Соседи-{number}»", f"9901400{number:05d}"))
    client.force_login(member)

    _, page = shelf(client)

    assert len(parties_on(page)) == 32
    assert "?page=" not in page


def test_the_shelf_carries_no_way_to_change_anything(shelf_page, alpha):
    """Створок заведения, правки и удаления на полке этим тикетом не появляется: the полка
    answers «с кем мы имеем дело», and every write stands elsewhere."""
    assert "Завести" not in shelf_page
    assert "Редактировать" not in shelf_page
    assert "Удалить" not in shelf_page
    assert "<form" not in row_markup(shelf_page, alpha)
    assert "<button" not in row_markup(shelf_page, alpha)


def test_the_page_carries_no_leftover_template_comments(shelf_page):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on screen."""
    assert "{#" not in shelf_page


# Ближайший повод


def occasion_cell(page, party):
    """What the «Ближайший повод» column says about one Сторона."""
    return cell_under(page, party, "Ближайший повод")


def occasion_date(page, party):
    """The день the column names, read back off the screen as a date.

    Read out of the cell rather than asserted as a string: what the rule resolves to is a
    day, and a test comparing «09.08.2026» to «09.08.2026» would pass just as well against a
    year printed by hand.
    """
    return date(*(int(part) for part in reversed(occasion_cell(page, party).split()[0].split("."))))


def second_sunday_of_august(year):
    """The second Sunday of August, counted by walking the month rather than by arithmetic.

    Deliberately a different route to the answer than `occasions` takes: a helper that
    resolved the rule the same way would agree with the code under test whatever either of
    them did.
    """
    sundays = [day for day in august(year) if day.isoweekday() == 7]
    return sundays[1]


def last_sunday_of_august(year):
    """The last Sunday of August — «последнее» and not «пятое»: August carries four Sundays
    in some years and five in others."""
    return [day for day in august(year) if day.isoweekday() == 7][-1]


def august(year):
    """Every day of an August — the month both weekday rules above are read out of."""
    return [date(year, 8, number) for number in range(1, 32)]


def nearest(day_of, today):
    """The next occurrence of a yearly rule at or after today — this year's or next year's.

    The «ближайший» half of the question and not the «в дату какого года» half: which year
    the day falls in is what the assertion is about, so the test says out loud which one it
    expects rather than asking the code.
    """
    return day_of(today.year) if day_of(today.year) >= today else day_of(today.year + 1)


def birthday_on(day):
    """A день рождения falling on this day of the year, born long enough ago to be nobody's
    business: what a повод is made of is the число and the месяц, and never the год."""
    return day.replace(year=1980)


def test_a_contact_persons_birthday_becomes_an_occasion(
    client, member, downtown, alpha, make_record, make_contact, today
):
    """«Кому звонить» и «кого поздравить» — один список: the день рождения of a контактное
    лицо is the личный повод of a юрлицо, because a юрлицо has no birthday of its own."""
    record = make_record(downtown, alpha)
    make_contact(record, "Иванов Иван", born_on=birthday_on(today + timedelta(days=3)))
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, alpha) == today + timedelta(days=3)
    assert "Иванов Иван" in occasion_cell(page, alpha)


def test_a_natural_persons_birthday_on_the_record_becomes_an_occasion(
    client, member, downtown, petrov, make_record, today
):
    """У физлица контактных лиц нет (ADR 0025), and the личный повод still has to exist —
    so it hangs on the карточка itself, where it is personal data of one организация
    (ADR 0023)."""
    make_record(downtown, petrov, born_on=birthday_on(today + timedelta(days=5)))
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, petrov) == today + timedelta(days=5)
    assert "День рождения" in occasion_cell(page, petrov)


def test_a_professional_occasion_is_derived_from_the_line_of_business(
    client, member, downtown, alpha, construction, make_record, make_holiday
):
    """Derived from the сфера деятельности and never typed in: «День строителя» entered at
    three hundred арендаторов is three hundred copies of one date, and they would drift
    apart (ADR 0023)."""
    alpha.line_of_business = construction
    alpha.save()
    make_record(downtown, alpha)
    make_holiday(construction, "День строителя", month=8, week_of_month=2, weekday=7)
    client.force_login(member)

    _, page = shelf(client)

    assert "День строителя" in occasion_cell(page, alpha)


def test_a_weekday_rule_resolves_into_the_year_being_asked_about(
    client, member, downtown, alpha, construction, make_record, make_holiday, today
):
    """«Второе воскресенье августа» is a rule and not a date: no year goes quietly unfilled,
    which is the whole of ADR 0027."""
    alpha.line_of_business = construction
    alpha.save()
    make_record(downtown, alpha)
    make_holiday(construction, "День строителя", month=8, week_of_month=2, weekday=7)
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, alpha) == nearest(second_sunday_of_august, today)


def test_the_last_weekday_of_a_month_is_not_the_fourth_one(
    client, member, downtown, alpha, construction, make_record, make_holiday, today
):
    """День шахтёра — последнее воскресенье августа, and August has five Sundays in some
    years: folding «последнее» into «четвёртое» would move the day by a week in half of
    them."""
    alpha.line_of_business = construction
    alpha.save()
    make_record(downtown, alpha)
    make_holiday(construction, "День шахтёра", month=8, week_of_month=-1, weekday=7)
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, alpha) == nearest(last_sunday_of_august, today)


def test_a_day_and_month_rule_resolves_into_the_year_being_asked_about(
    client, member, downtown, alpha, construction, make_record, make_holiday, today
):
    """The other of the two forms: «двенадцатое апреля» carries no year either."""
    alpha.line_of_business = construction
    alpha.save()
    make_record(downtown, alpha)
    make_holiday(construction, "День работников науки", day=12, month=4)
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, alpha) == nearest(lambda year: date(year, 4, 12), today)


def test_the_derived_occasion_is_stored_nowhere(
    client, member, downtown, alpha, construction, make_record, make_holiday
):
    """Нигде не хранится: the праздник stays one row of the справочник however many Стороны
    it is shown against, and reading the полка writes nothing down (ADR 0023).

    Counted over every table the повод could have been written into rather than asserted of
    a `Occasion` table that does not exist: an assertion naming an absent model would go on
    passing on the day somebody adds it.
    """
    alpha.line_of_business = construction
    alpha.save()
    make_record(downtown, alpha)
    make_holiday(construction, "День строителя", month=8, week_of_month=2, weekday=7)
    client.force_login(member)
    before = {model: model.objects.count() for model in (DictProfessionalHoliday, ContactPerson)}

    _, page = shelf(client)

    assert "День строителя" in occasion_cell(page, alpha)
    assert {model: model.objects.count() for model in before} == before


def test_the_nearest_of_several_occasions_is_the_one_the_column_names(
    client, member, downtown, alpha, construction, make_record, make_contact, make_holiday, today
):
    """Один повод в колонке, и это ближайший: «кого поздравить» is a question about the next
    few days, and a row naming the furthest of three would answer a different one."""
    alpha.line_of_business = construction
    alpha.save()
    record = make_record(downtown, alpha)
    make_contact(record, "Дальний Дмитрий", born_on=birthday_on(today + timedelta(days=40)))
    make_contact(record, "Ближний Борис", born_on=birthday_on(today + timedelta(days=2)))
    make_holiday(construction, "День строителя", month=8, week_of_month=2, weekday=7)
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, alpha) == today + timedelta(days=2)
    assert "Ближний Борис" in occasion_cell(page, alpha)


def test_an_occasion_today_is_the_nearest_one(
    client, member, downtown, alpha, make_record, make_contact, today
):
    """Сегодняшний день рождения ещё не прошёл: «кого поздравить» asked on the morning of
    the day itself must not answer with next year."""
    record = make_record(downtown, alpha)
    make_contact(record, "Иванов Иван", born_on=birthday_on(today))
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_date(page, alpha) == today


def test_a_birthday_on_the_twenty_ninth_of_february_is_a_occasion_every_year(
    client, member, downtown, alpha, make_record, make_contact
):
    """Родившегося двадцать девятого февраля поздравляют раз в год, как всех: a повод that
    vanished from the list in three years out of four would read as «дня рождения нет», and
    the повод is a день в году, повторяющийся и бессрочный."""
    make_contact(make_record(downtown, alpha), "Високосов Виктор", born_on=date(1980, 2, 29))
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_cell(page, alpha) != "—"
    assert occasion_date(page, alpha).month == 2


def test_a_party_with_no_occasion_at_all_shows_a_dash(shelf_page, alpha):
    """Ни контактных лиц, ни сферы деятельности — и это ответ, а не пробел: 637 of the 699
    Стороны are поставщики nobody has written a день рождения for."""
    assert occasion_cell(shelf_page, alpha) == "—"


def test_a_line_of_business_with_no_holiday_is_no_occasion(
    client, member, downtown, alpha, catering, make_record
):
    """Отрасль без праздника — обычное дело, а не пробел: общепит сидит в БЦ этажами, and
    the перечень РК has no day for it."""
    alpha.line_of_business = catering
    alpha.save()
    make_record(downtown, alpha)
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_cell(page, alpha) == "—"


def test_a_contact_with_no_birthday_is_no_occasion(
    client, member, downtown, alpha, make_record, make_contact
):
    """«Кому звонить» и «кого поздравить» — один список, and an инженер whose день рождения
    nobody knows does not fall out of it — he simply is not a повод."""
    make_contact(make_record(downtown, alpha), "Иванов Иван")
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_cell(page, alpha) == "—"


def test_a_contact_of_another_organisation_is_not_an_occasion_of_my_row(
    client, member, central, downtown, alpha, make_record, make_contact, today
):
    """Личный повод лежит в учётной карточке (ADR 0020): the mobile and the birthday another
    управляющая компания was given must not surface on my полка because we know the same
    юрлицо."""
    make_record(downtown, alpha)
    make_contact(
        make_record(central, alpha), "Чужой Человек", born_on=birthday_on(today + timedelta(days=1))
    )
    client.force_login(member)

    _, page = shelf(client)

    assert occasion_cell(page, alpha) == "—"
    assert "Чужой Человек" not in page


def test_the_occasion_column_costs_no_query_per_row(
    client, member, downtown, alpha, construction, make_party, make_record,
    make_contact, make_holiday, django_assert_num_queries,
):
    """Одним запросом на всю полку, а не по строке — the device `tenants_of_each_room` is:
    the полка carries 637 rows, and a question asked per row is asked 637 times.

    The полка counted first already carries both kinds of повод — a контактное лицо and a
    сфера деятельности with a праздник on it — so that what the twenty rows added afterwards
    are measured against is a screen doing all the work, and not one that had nothing to look
    up yet.
    """
    make_holiday(construction, "День строителя", month=8, week_of_month=2, weekday=7)
    alpha.line_of_business = construction
    alpha.save()
    make_contact(make_record(downtown, alpha), "Иванов Иван", born_on=date(1980, 3, 4))
    client.force_login(member)
    # Read once before counting: the first request of a session pays for what the column is
    # not about — the session row — and what is asked here is what a row costs.
    shelf(client)
    with CaptureQueriesContext(connection) as few_rows:
        shelf(client)

    for number in range(20):
        party = make_party(
            f"ТОО «Соседи-{number}»", f"9901400{number:05d}", line_of_business=construction
        )
        make_contact(make_record(downtown, party), f"Сосед-{number}", born_on=date(1980, 3, 4))

    with django_assert_num_queries(len(few_rows)):
        _, page = shelf(client)

    assert len(parties_on(page)) == 21
