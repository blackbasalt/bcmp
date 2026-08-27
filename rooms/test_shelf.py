"""The «Помещения» section — what a сотрудник УК sees over HTTP.

There is one seam: the HTTP boundary of `/rooms/`. The tests walk the named address with
the test client on behalf of a user with a known membership and check what is observable —
which помещения are on screen, in what order, what is written in a row, what the count line
says and what code the request answers with. Below HTTP there is no seam: the visibility
chokepoint, the отбор and the вид rule are all checked through this screen, because that is
how they are read.

The foothold in the markup is the `data-room` attribute on a table row, mirroring
`data-document` on the полка документов. That is the screen's contract: it shows which
помещения are displayed and in what order, and a rebuild of the layout does not rewrite the
test suite.
"""

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from building_passport.models import Space

pytestmark = pytest.mark.django_db

#: A table row together with the помещение's key: the screen's contract and everything
#: written in the row. It is not read by parsing tags — what is asked of a row is not its
#: structure but its text, and that text must be found in the row itself, not somewhere on
#: the page.
ROW = re.compile(r'<tr[^>]*data-room="(?P<key>[^"]+)"[^>]*>(?P<cells>.*?)</tr>', re.DOTALL)

#: The cells of one row, in the order they stand in it — for the questions about a
#: particular column, where the row's text as a whole cannot tell «Внутри» from «Название».
CELL = re.compile(r"<t[dh][^>]*>(?P<text>.*?)</t[dh]>", re.DOTALL)


def stated(text):
    """The text on a single line: a phrase must not break on a line wrap in the markup."""
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def folded(markup):
    """The markup on a single line, tags and all: an attribute and its value must not be
    told apart by a line wrap when a test looks for the two together. `stated` is for what
    the reader sees; this is for what the markup promises."""
    return " ".join(markup.split())


def rows_on(page):
    """The table rows by помещение key: what is written in each of them."""
    return {row["key"]: stated(row["cells"]) for row in ROW.finditer(page)}


def cells_on(page, raw=False):
    """The same rows, cell by cell: key → the list of cells as they stand.

    `raw` keeps the markup of each cell, for the one question a cell's text cannot answer:
    where the link in it leads.
    """
    return {
        row["key"]: [
            cell["text"] if raw else stated(cell["text"])
            for cell in CELL.finditer(row["cells"])
        ]
        for row in ROW.finditer(page)
    }


def headings_on(page):
    """The column headings, left to right — what the cells of a row are to be read against."""
    head = re.search(r"<thead>(.*?)</thead>", page, re.DOTALL)
    return [stated(cell["text"]) for cell in CELL.finditer(head.group(1))] if head else []


def rooms_on(page):
    """The keys of the помещения shown, top to bottom — the order of the rows is checked too."""
    return [row["key"] for row in ROW.finditer(page)]


def count_line(page):
    """The line saying how much of the полка is on screen, and what it lacks.

    Found by `data-count`, the screen's contract for it, and not by the classes it wears:
    it stands beneath the table on a полка that has rows and beneath the warning on one an
    отбор emptied, and both are the same line.
    """
    found = re.search(r'data-count="rooms"[^>]*>(.*?)</p>', page, re.DOTALL)
    return stated(found.group(1)) if found else ""


def missing_area_link(page):
    """The address behind the «площадь не заведена у M» figure — the second half of the
    count line is a link, and where it leads is the assertion."""
    found = re.search(r'площадь не заведена у <a[^>]*href="(?P<url>[^"]+)"', page)
    return found["url"].replace("&amp;", "&")


def shelf(client):
    response = client.get(reverse("rooms:room_list"))
    return response, response.content.decode()


def make_room(parent, code, name, **fields):
    """A помещение under an этаж or under another помещение — the same as `make_space`,
    named the way this section names it."""
    return Space.objects.create(
        org=parent.org,
        type="room",
        parent=parent,
        building=parent.building,
        floor_number=parent.floor_number,
        code=code,
        name=name,
        **fields,
    )


@pytest.fixture
def shelf_page(client, member, first_floor):
    client.force_login(member)
    _, page = shelf(client)
    return page


# Access and isolation


def test_a_member_sees_the_rooms_of_their_own_organisation_only(
    client, member, central, first_floor, make_building, make_floor
):
    """Client isolation on screen — the полка obeys the same chokepoint as every other
    screen (ADR 0001)."""
    theirs = make_floor(make_building(central, "ctr", "Central City"), 1)
    make_room(theirs, "ctr-f1-a", "Чужая серверная")
    client.force_login(member)

    response, page = shelf(client)

    assert response.status_code == 200
    assert "каб101вход" in page
    assert "Чужая серверная" not in page


def test_an_anonymous_visitor_is_sent_to_login(client, first_floor):
    """The полка is not a way round the login every other screen requires."""
    response = client.get(reverse("rooms:room_list"))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_a_superuser_reads_every_organisations_rooms(
    client, django_user_model, central, first_floor, make_building, make_floor
):
    """A superuser reads on everyone's behalf — the same rule as on every other screen."""
    theirs = make_floor(make_building(central, "ctr", "Central City"), 1)
    make_room(theirs, "ctr-f1-a", "Чужая серверная")
    client.force_login(django_user_model.objects.create_superuser("root"))

    _, page = shelf(client)

    assert "каб101вход" in page
    assert "Чужая серверная" in page


# What is on the полка


def test_the_shelf_opens_with_every_room_the_reader_may_see(shelf_page, first_floor):
    """The screen starts by telling the reader how much there is: no отбор, the whole полка."""
    assert len(rooms_on(shelf_page)) == 3


def test_a_nested_room_is_a_row_of_its_own(shelf_page):
    """The tree is unwoven, not cut: a кабина inside a уборная is looked for on this полка
    exactly as a кабинет is (ADR 0015)."""
    nested = Space.objects.get(code="man-f1-a1")

    assert str(nested.pk) in rooms_on(shelf_page)


def test_a_space_that_is_not_a_room_stays_off_the_shelf(client, member, first_floor, make_space):
    """Шахты, лестничные клетки and кровли are not помещения on this screen."""
    make_space(first_floor, "man-f1-s", "Лифтовая шахта", type="shaft")
    client.force_login(member)

    _, page = shelf(client)

    assert "Лифтовая шахта" not in page


def test_a_floor_is_not_a_room_either(shelf_page, first_floor):
    """The этаж holding the помещения is not one of them."""
    assert str(first_floor.pk) not in rooms_on(shelf_page)


def test_the_rows_are_ordered_by_building_then_floor_then_code(
    client, member, first_floor, tokyo, manhattan, make_floor
):
    """Reading the полка top to bottom walks the portfolio the way one would walk it.

    Manhattan before Tokyo, and within Manhattan the first floor before the second: the
    rows are staged out of that order on purpose, so that the assertion is about the
    screen's ordering and not about the order of creation.
    """
    third = Space.objects.get(building=tokyo, type="floor")
    far = make_room(third, "tok-f3-a", "Санузел")
    second = make_floor(manhattan, 2)
    upstairs = make_room(second, "man-f2-a", "каб201")
    client.force_login(member)

    _, page = shelf(client)
    shown = rooms_on(page)

    assert shown[-1] == str(far.pk)
    assert shown.index(str(upstairs.pk)) > shown.index(str(Space.objects.get(code="man-f1-b").pk))


# What a row says


def test_a_row_says_what_is_needed_to_judge_a_room_without_opening_it(
    client, member, first_floor, office
):
    """Код, название, БЦ, этаж, вид, назначение and площадь — all in the row."""
    room = Space.objects.get(code="man-f1-b")
    room.subtype = office
    room.area_m2 = Decimal("12.50")
    room.is_leasable = True
    room.save()
    client.force_login(member)

    _, page = shelf(client)
    row = rows_on(page)[str(room.pk)]

    assert "man-f1-b" in row
    assert "ИТП" in row
    assert "Manhattan" in row
    assert "Офис" in row
    assert "Арендопригодное" in row
    assert "12,50" in row


def test_the_floor_column_says_which_floor_the_room_is_on(client, member, first_floor):
    """The этаж is in the row, so that «третий этаж» is judged without opening anything."""
    room = Space.objects.get(code="man-f1-b")
    client.force_login(member)

    _, page = shelf(client)
    floor = cells_on(page)[str(room.pk)][headings_on(page).index("Этаж")]

    assert floor == "1"


def test_a_row_leads_to_the_floor_screen_with_that_rooms_card_named(
    client, member, first_floor
):
    """Having found «которое», the reader immediately sees «где».

    The address is checked, not merely the presence of a link: a row leading to the этаж
    without naming the помещение would land the reader on a screen with an empty rail, back
    to hunting through the tree they came to the полка to avoid.
    """
    nested = Space.objects.get(code="man-f1-a1")
    client.force_login(member)

    _, page = shelf(client)
    named = cells_on(page, raw=True)[str(nested.pk)][headings_on(page).index("Название")]
    leads_to = re.search(r'href="(?P<url>[^"]*)"', named)

    assert leads_to["url"] == (
        reverse("building_passport:floor", args=[nested.building_id, first_floor.pk])
        + f"?space={nested.pk}"
    )


def test_a_room_whose_floor_number_names_no_floor_leads_nowhere(
    client, member, first_floor, make_space
):
    """A link opening the wrong этаж is worse than no link.

    Today's data has no such помещение — every one of the 583 has a `floor_number` and every
    number has an этаж. It is staged here because the row must degrade to plain text rather
    than to an address assembled out of nothing.
    """
    stray = make_space(first_floor, "man-f9-a", "каб901", floor_number=9)
    client.force_login(member)

    _, page = shelf(client)
    named = cells_on(page, raw=True)[str(stray.pk)][headings_on(page).index("Название")]

    assert "каб901" in stated(named)
    assert "href" not in named


def test_the_inside_column_names_the_room_a_row_sits_in(client, member, first_floor):
    """A flat table admits it unwove a tree: that is how a кабина is told from a кабинет."""
    nested = Space.objects.get(code="man-f1-a1")
    client.force_login(member)

    _, page = shelf(client)
    inside = cells_on(page)[str(nested.pk)][headings_on(page).index("Внутри")]

    assert inside == "каб101вход"


def test_the_inside_column_is_empty_for_a_room_lying_on_the_floor(client, member, first_floor):
    """Empty, and not a dash: lying straight on an этаж is the ordinary case, not a gap."""
    on_the_floor = Space.objects.get(code="man-f1-b")
    client.force_login(member)

    _, page = shelf(client)
    inside = cells_on(page)[str(on_the_floor.pk)][headings_on(page).index("Внутри")]

    assert inside == ""


def test_a_room_with_no_area_shows_a_dash_rather_than_a_zero(client, member, first_floor):
    """«Не заведено» must not be read as «нулевая площадь»."""
    room = Space.objects.get(code="man-f1-b")
    client.force_login(member)

    _, page = shelf(client)
    area = cells_on(page)[str(room.pk)][headings_on(page).index("Площадь")]

    assert area == "— нет данных"


def test_the_area_column_is_not_totalled(client, member, first_floor):
    """No итог under площадь: вложенные помещения would be counted twice, and by an unknown
    amount (ADR 0015). The footer of the table is where a sum would stand, and there is
    none — the row count is what the line beneath says instead."""
    for code, area in [("man-f1-a", "30.00"), ("man-f1-a1", "10.00"), ("man-f1-b", "5.00")]:
        Space.objects.filter(code=code).update(area_m2=Decimal(area))
    client.force_login(member)

    _, page = shelf(client)

    assert "<tfoot" not in page
    assert "45,00" not in page


def test_the_kind_is_read_off_the_flags_the_plan_reads(client, member, first_floor):
    """Арендопригодное, МОП, техническое — the same rule the план colours contours by.

    Техническое is the remainder, and that is checked here rather than assumed: a помещение
    nobody classified is technical, and the полка must say so out loud rather than leave the
    cell blank.
    """
    Space.objects.filter(code="man-f1-a").update(is_leasable=True, is_common=False)
    Space.objects.filter(code="man-f1-a1").update(is_leasable=False, is_common=True)
    Space.objects.filter(code="man-f1-b").update(is_leasable=None, is_common=None)
    client.force_login(member)

    _, page = shelf(client)
    kind = headings_on(page).index("Вид")
    cells = cells_on(page)

    assert cells[str(Space.objects.get(code="man-f1-a").pk)][kind] == "Арендопригодное"
    assert cells[str(Space.objects.get(code="man-f1-a1").pk)][kind] == "МОП"
    assert cells[str(Space.objects.get(code="man-f1-b").pk)][kind] == "Техническое"


def test_a_room_let_and_common_at_once_reads_as_leasable(client, member, first_floor):
    """What is let to a tenant is never common — the same reading as on the план."""
    Space.objects.filter(code="man-f1-b").update(is_leasable=True, is_common=True)
    client.force_login(member)

    _, page = shelf(client)
    row = rows_on(page)[str(Space.objects.get(code="man-f1-b").pk)]

    assert "Арендопригодное" in row
    assert "МОП" not in row


# The organisation column


def test_a_member_of_two_organisations_sees_each_organisation_under_its_own_name(
    client, both_clients, downtown, central, first_floor, make_building, make_floor
):
    """Two clients for one employee — two полки, not one common heap.

    This must be said in the row itself: the names of both organisations somewhere on the
    page distinguish nothing — they would match even with their places swapped.
    """
    theirs = make_room(make_floor(make_building(central, "ctr", "Central City"), 1),
                       "ctr-f1-a", "Чужая серверная")
    ours = Space.objects.get(code="man-f1-b")
    client.force_login(both_clients)

    _, page = shelf(client)
    rows = rows_on(page)

    assert downtown.name in rows[str(ours.pk)]
    assert central.name not in rows[str(ours.pk)]
    assert central.name in rows[str(theirs.pk)]


def test_a_member_of_one_organisation_gets_no_organisation_column(shelf_page, downtown):
    """A column repeating one word 583 times would take the width and say nothing."""
    assert "Организация" not in headings_on(shelf_page)
    assert downtown.name not in shelf_page


# The count line


def test_the_count_says_how_much_of_the_shelf_is_on_screen(shelf_page):
    """The question asked first, answered by a phrase and not by the length of the list."""
    assert "Показано 3 из 3 помещений" in count_line(shelf_page)


def test_the_count_names_the_rooms_with_no_area(shelf_page):
    """The gap in the data is stated on the screen that holds the data (ADR 0015)."""
    assert "площадь не заведена у 3" in count_line(shelf_page)


def test_the_missing_area_figure_is_a_link_that_asks_for_exactly_those_rooms(
    client, member, first_floor
):
    """The audit is one click from the finder: the figure itself is the link, and following
    it leaves exactly the помещения it counted."""
    Space.objects.filter(code="man-f1-b").update(area_m2=Decimal("5.00"))
    client.force_login(member)

    _, page = shelf(client)

    followed = client.get(missing_area_link(page)).content.decode()
    assert len(rooms_on(followed)) == 2
    assert "площадь не заведена у 2" in count_line(followed)


def test_a_shelf_with_no_gaps_says_nothing_about_them(client, member, first_floor):
    """«площадь не заведена у 0» is a line about nothing."""
    Space.objects.filter(type="room").update(area_m2=Decimal("5.00"))
    client.force_login(member)

    _, page = shelf(client)

    assert "площадь не заведена" not in count_line(page)


# Empty states


def test_a_shelf_with_no_rooms_says_who_enters_them(client, member, manhattan):
    """Told who acts, rather than handed a link they cannot use: помещения are entered by
    the platform administrator, not from this screen."""
    client.force_login(member)

    _, page = shelf(client)

    assert rooms_on(page) == []
    assert "Помещения не заведены" in stated(page)
    assert "администратор платформы" in stated(page)


def test_a_shelf_with_no_rooms_says_so_even_with_a_condition_in_the_address(
    client, member, manhattan
):
    """«ничего не нашлось» would send this reader to fix a question that was never the
    problem: there is nothing on the полка to find, whatever is asked of it.

    Which of the two empty states it is follows from the size of the полка and not from
    whether anything was asked — a полка with no помещения can be questioned exactly as a
    full one can.
    """
    client.force_login(member)

    response = client.get(reverse("rooms:room_list"), {"q": "каб101"})
    page = response.content.decode()

    assert "Помещения не заведены" in stated(page)
    assert "ничего не нашлось" not in stated(page)
    assert 'data-search="rooms"' not in page


def test_the_bar_is_not_offered_on_a_shelf_with_no_rooms(client, member, manhattan):
    """Narrowing a nothing is an offer that answers nothing."""
    client.force_login(member)

    _, page = shelf(client)

    assert 'data-search="rooms"' not in page


# The whole полка at once


def test_the_shelf_is_rendered_whole_with_no_pagination(client, member, first_floor):
    """The browser's own find must work across every row, and a shared link lose nothing."""
    for number in range(30):
        make_room(first_floor, f"man-f1-x{number}", f"каб1{number:02d}")
    client.force_login(member)

    _, page = shelf(client)

    assert len(rooms_on(page)) == 33
    assert "?page=" not in page


def test_the_shelf_carries_no_way_to_change_anything(shelf_page):
    """A finder and nothing else: the полка is read-only, and writing stays where it was."""
    assert "Редактировать" not in shelf_page
    assert "Удалить" not in shelf_page
    assert "Добавить" not in shelf_page
    assert "Загрузить" not in shelf_page


def test_the_page_carries_no_leftover_template_comments(shelf_page):
    """Django does not treat a multi-line `{# … #}` as a comment and prints it on screen."""
    assert "{#" not in shelf_page
