"""The floor plan as data: the file, its contours and what is visible on the floor screen.

The seam is the same as for the other screens — the HTTP boundary: the tests open the
floor and the plan file with the test client on behalf of a user with a known
membership. Below HTTP only what cannot be observed over HTTP is checked: that creating a
plan and parsing its contours are one operation. The SVG parse itself lives in its own
seam, `test_floor_plan_svg`.

The footholds in the markup are `data-contour` on a contour, `data-plan` on a floor in
the switcher, `data-select` together with `data-drawn` on whatever selects a space,
`data-paint` together with `data-legend` on the layer's colouring, and `data-unmatched`
on a path that found no space. That is the screen's contract, not its styling: through
them the plan and the tree find each other, and they show whether the floor has a
drawing, which spaces are not drawn on it, what each contour is coloured with and which
`id`s in the drawing are left dangling.
"""

import re
from datetime import date, timedelta
from html.parser import HTMLParser

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from building_passport.floor_plan_svg import PlanUnreadable
from building_passport.models import Contour, FloorPlan, Space

pytestmark = pytest.mark.django_db

VIEW_BOX = "0 0 800 600"
ENTRANCE_PATH = "M0 0 L100 0 L100 100 Z"
ITP_PATH = "M400 0 L500 0 L500 100 Z"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Uploaded files go into a temporary directory rather than into the working copy."""
    settings.MEDIA_ROOT = tmp_path


def plan_svg(*contours, view_box=VIEW_BOX):
    """The drawing of a floor: space outlines by code plus a wall that stays a wall."""
    paths = "".join(f'<path id="{code}" d="{d}" />' for code, d in contours)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">'
        f'<path d="M0 0 L800 0" />{paths}</svg>'
    )


def make_plan(floor, source, valid_from=date(2020, 1, 1), valid_to=None):
    return FloorPlan.objects.create(
        floor=floor,
        file=SimpleUploadedFile("plan.svg", source.encode(), content_type="image/svg+xml"),
        valid_from=valid_from,
        valid_to=valid_to,
    )


def day(offset):
    """A date in days from today: "in force" is a property of today in particular."""
    return timezone.localdate() + timedelta(days=offset)


@pytest.fixture
def plan(first_floor):
    """The first floor's plan: "каб101вход" and "ИТП" are outlined, "каб101" is not."""
    return make_plan(
        first_floor,
        plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-b", "M200 0 L300 0 L300 100 Z")),
    )


def floor_url(floor):
    return reverse("building_passport:floor", args=[floor.building_id, floor.pk])


def file_url(plan):
    return reverse("building_passport:floor_plan_svg", args=[plan.pk])


def card_url(space):
    return reverse("building_passport:space_card", args=[space.pk])


@pytest.fixture
def floor_page(client, member, plan):
    client.force_login(member)
    return client.get(floor_url(plan.floor)).content.decode()


@pytest.fixture
def their_plan(central, make_floor, make_space):
    """Another client's plan — what must be visible neither through a screen nor as a file."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    floor = make_floor(theirs, 1)
    make_space(floor, "ctr-f1-a", "Кабинет")
    return make_plan(floor, plan_svg(("ctr-f1-a", ENTRANCE_PATH)))


class Marked(HTMLParser):
    """Tags carrying an attribute from the screen's contract: their attributes and their caption.

    The caption of a contour is the `<title>` nested inside it: the name of the space
    pops up on hover by itself, without a single line on the browser side. It is read by
    parsing rather than by searching the text of the page: the same name stands in the
    tree on the left, and a search would find it there even if it never reached the plan.
    """

    def __init__(self, attribute):
        super().__init__(convert_charrefs=True)
        self.attribute = attribute
        self.found: list[dict[str, str]] = []
        self.titled: dict[str, str] | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if self.attribute in attributes:
            self.found.append(attributes)
        self.titled = self.found[-1] if tag == "title" and self.found else None

    def handle_endtag(self, tag):
        self.titled = None

    def handle_data(self, data):
        if self.titled is not None:
            self.titled["title-text"] = data


def marked(page, attribute):
    parser = Marked(attribute)
    parser.feed(page)
    return parser.found


def contours_on(page):
    return {tag["data-contour"]: tag for tag in marked(page, "data-contour")}


def legend_on(page):
    """Legend entries by the key of the kind — the same one the contour is marked with."""
    return {tag["data-legend"]: tag for tag in marked(page, "data-legend")}


def painted_on(page):
    """What each contour is coloured with: the space's code → the key of the layer's kind.

    A contour with no fill does not get into the set: it is not coloured but outlined.
    """
    return {
        code: tag["data-paint"]
        for code, tag in contours_on(page).items()
        if "data-paint" in tag
    }


def overlay(page):
    """The layer of contours over the drawing — what the application draws, not the file itself.

    Needed where the absence of a superfluous path is checked: the drawing itself holds
    any number of paths, and there is no point counting them mixed in with the contours.
    """
    return re.search(r'<svg[^>]*aria-label="Контуры помещений".*?</svg>', page, re.DOTALL).group()


def stated(page):
    """The page as one line: a phrase must not break on a line wrap in the markup."""
    return " ".join(page.split())


# The plan file


def test_a_member_gets_the_file_of_their_own_plan(client, member, plan):
    """The drawing is served by the application, which is why it reaches the employee whole."""
    client.force_login(member)

    response = client.get(file_url(plan))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert b"man-f1-a" in b"".join(response.streaming_content)


def test_the_file_of_another_organisations_plan_is_missing_rather_than_forbidden(
    client, member, their_plan
):
    """Exactly the leak the checkpoint exists for (ADR 0001): a foreign plan is unreachable.

    A 403 would answer that such a plan exists — and the address of a file can be guessed
    or leak from someone else's tab, in which case the answer would give away another
    client's drawing.
    """
    client.force_login(member)

    assert client.get(file_url(their_plan)).status_code == 404


def test_an_anonymous_request_for_the_file_is_sent_to_login(client, plan):
    """Before signing in, drawings are invisible too: a file is as much a read path as a screen."""
    response = client.get(file_url(plan))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_a_superuser_reaches_any_organisations_plan_and_its_file(
    client, django_user_model, their_plan
):
    """A developer reproduces a client's problem without granting themselves a membership."""
    client.force_login(django_user_model.objects.create_superuser("developer"))

    assert client.get(floor_url(their_plan.floor)).status_code == 200
    assert client.get(file_url(their_plan)).status_code == 200


def test_the_file_is_served_sandboxed(client, member, plan):
    """SVG is an executable format: opened directly by its address it would run on our side.

    The file comes from whoever uploaded it and is served from the application's domain,
    so the response goes into a sandbox and without type sniffing.
    """
    client.force_login(member)

    response = client.get(file_url(plan))

    assert "sandbox" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


# The plan on the floor screen


def test_a_floor_with_a_plan_opens(client, member, plan):
    """A screen with a plan renders: a template error is caught here."""
    client.force_login(member)

    response = client.get(floor_url(plan.floor))

    assert response.status_code == 200
    assert "нет действующего поэтажного плана" not in response.content.decode()


def test_each_drawn_space_is_outlined_on_the_plan(floor_page):
    """A plan is the spaces, drawn: exactly what is drawn is outlined."""
    assert set(contours_on(floor_page)) == {"man-f1-a", "man-f1-b"}


def test_a_contour_is_drawn_along_the_geometry_it_was_authored_with(floor_page):
    """A space is recognised by its shape, not by a rectangle standing in for it."""
    assert contours_on(floor_page)["man-f1-a"]["d"] == ENTRANCE_PATH


def test_a_space_with_no_path_in_the_file_is_not_drawn(floor_page):
    """No shape is invented for a space without a contour — it stays in the tree only."""
    assert "man-f1-a1" not in contours_on(floor_page)
    assert "man-f1-a1" in floor_page


def test_hovering_a_contour_shows_the_name_of_its_space(floor_page):
    """A floor is scanned without diving into every space in turn.

    The name comes first but is not alone: the layer appends its own line to it — what
    the colour the space is filled with means.
    """
    assert contours_on(floor_page)["man-f1-a"]["title-text"].startswith("каб101вход")


def test_the_drawing_is_asked_for_through_the_application(floor_page, plan):
    """The drawing travels through the same checkpoint as everything else — not out of /media/."""
    assert file_url(plan) in floor_page
    assert "/media/" not in floor_page


def test_a_contour_over_a_space_of_another_organisation_is_not_drawn(
    client, member, central, first_floor
):
    """Another client's row under this floor must not reach the screen by name or by shape.

    There is no such row in healthy data; what is checked is that the contours are
    selected through the checkpoint, as the tree is, rather than shown just because they
    happen to lie in the plan.
    """
    Space.objects.create(
        org=central, type="room", parent=first_floor, building=first_floor.building,
        code="ctr-x", name="Чужое помещение",
    )
    make_plan(first_floor, plan_svg(("ctr-x", ENTRANCE_PATH)))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert contours_on(page) == {}
    assert "Чужое помещение" not in page


def test_the_plan_of_another_floor_is_not_drawn_on_this_one(
    client, member, first_floor, make_floor, make_space
):
    """A plan belongs to a floor: a neighbouring drawing is not mixed into this screen."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    make_plan(second, plan_svg(("man-f2-a", ENTRANCE_PATH)))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert contours_on(page) == {}


# The plan and the tree — two views of one selection


def test_a_contour_opens_the_card_of_the_space_it_outlines(floor_page):
    """A plan is questioned by pointing: a click on a contour selects the space."""
    entrance = Space.objects.get(code="man-f1-a")

    assert contours_on(floor_page)["man-f1-a"]["hx-get"] == card_url(entrance)


def test_the_tree_marks_which_spaces_are_missing_from_the_plan(floor_page):
    """The plan is the project's sharpest tool for finding what has not been recorded.

    "каб101" is not outlined on the drawing, and the tree shows that without comparing
    the list against the picture.
    """
    marks = {tag["data-select"]: tag["data-drawn"] for tag in marked(floor_page, "data-drawn")}

    assert marks == {"man-f1-a": "yes", "man-f1-a1": "no", "man-f1-b": "yes"}
    assert "нет контура" in floor_page


def test_a_space_missing_from_the_plan_is_still_selectable_from_the_tree(floor_page):
    """These spaces matter more than the rest, and there is nowhere to click them."""
    undrawn = Space.objects.get(code="man-f1-a1")
    node = {tag["data-select"]: tag for tag in marked(floor_page, "data-drawn")}["man-f1-a1"]

    assert node["hx-get"] == card_url(undrawn)


def test_nothing_is_marked_in_the_tree_when_no_plan_is_in_force(
    client, member, first_floor
):
    """With no plan in force nothing is drawn, and a mark on every node is noise.

    The plan of a future rebuild is already on record for the floor: it is not in force
    today, and it cannot say what is drawn and what is not.
    """
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(30))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert marked(page, "data-drawn") == []
    assert "нет контура" not in page


# Completeness: how much is drawn and what dangles on the drawing


def test_the_floor_screen_states_how_many_spaces_are_drawn_out_of_how_many_exist(floor_page):
    """The screen counts what is missing from the plan — the most valuable thing it can say.

    The floor holds three spaces and two are outlined: "каб101" is not drawn. There is no
    need to compare the tree against the drawing by eye for that.
    """
    assert "Нанесено 2 из 3 помещений" in stated(floor_page)


def test_a_space_with_no_contour_counts_into_the_figure_of_what_is_not_drawn(
    client, member, plan, make_space
):
    """A space created after the plan does not appear on the drawing — and the count says so.

    The contours of a plan are never rebuilt (ADR 0003), so a new space grows the
    denominator, not the numerator.
    """
    make_space(plan.floor, "man-f1-c", "каб102")
    client.force_login(member)

    page = client.get(floor_url(plan.floor)).content.decode()

    assert "Нанесено 2 из 4 помещений" in stated(page)


def test_completeness_is_counted_in_spaces_rather_than_in_square_metres(client, member, plan):
    """Metres need a scale, which a plan does not declare, and not every space has an area.

    An invented scale would give a figure that looks precise without being so.
    """
    Space.objects.filter(code="man-f1-a").update(area_m2=100)
    client.force_login(member)

    page = client.get(floor_url(plan.floor)).content.decode()

    assert "Нанесено 2 из 3 помещений" in stated(page)
    assert "м²" not in page


def test_no_contour_is_drawn_for_the_uncovered_remainder_of_the_floor(floor_page):
    """The gap between the floor's area and the sum of its spaces is a finding, not a hole.

    A synthetic "other" contour would close it with an invented shape — the same mistake
    as `-1 м²`, only in another medium. Over the drawing lie exactly as many paths as
    there are spaces outlined.
    """
    assert overlay(floor_page).count("<path") == len(contours_on(floor_page)) == 2


def test_nothing_is_counted_when_no_plan_is_in_force(client, member, first_floor):
    """With no plan in force nothing is drawn: "0 of 3" says what the empty middle says."""
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(30))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert "Нанесено" not in page


def test_a_path_matching_no_space_is_reported_on_the_floor_screen(client, member, first_floor):
    """A typo in an `id` must be visible: the plan uploaded, but the path never became a space.

    The floor screen is where this is discovered: it carries fewer contours than whoever
    drew them expected, and the reason is named alongside.
    """
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert {tag["data-unmatched"] for tag in marked(page, "data-unmatched")} == {"man-f1-zz"}
    assert "Нанесено 1 из 3 помещений" in stated(page)


def test_one_id_on_two_paths_is_named_once(client, member, first_floor):
    """The typo is named, not every path carrying it: twice it reads as a screen glitch.

    A duplicate `id` behind a known space would get the file rejected; behind an unknown
    one it survives: a plan loads even against an incomplete tree.
    """
    make_plan(
        first_floor,
        plan_svg(("man-f1-zz", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)),
    )
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert [tag["data-unmatched"] for tag in marked(page, "data-unmatched")] == ["man-f1-zz"]


def test_a_plan_whose_every_path_matched_reports_nothing_unmatched(floor_page):
    """A sound drawing must not carry a warning about anything on the screen."""
    assert marked(floor_page, "data-unmatched") == []


def test_the_unmatched_paths_are_kept_with_the_plan_that_was_read(first_floor):
    """Unmatched paths are noticed while parsing but shown on the floor screen.

    Between those two moments they have to be kept somewhere, and the plan keeps them
    itself: the drawing is never parsed again.
    """
    plan = make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)))

    assert plan.unmatched_ids == ["man-f1-zz"]


def test_the_unmatched_paths_are_not_recomputed_when_the_period_is_edited(plan):
    """The parse happened once (ADR 0003): editing the period recomputes nothing either.

    A space gets its code changed — on a second parse its path would become unmatched.
    The plan stays with what it was read with.
    """
    Space.objects.filter(code="man-f1-b").update(code="man-f1-renamed")

    plan.valid_to = date(2026, 1, 1)
    plan.save()

    assert plan.unmatched_ids == []


# The floor switcher


def test_the_switcher_shows_which_floors_have_a_plan(
    client, member, plan, make_floor, make_space
):
    """Otherwise people click through floors hoping to find a drawing."""
    second = make_floor(plan.floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    client.force_login(member)

    page = client.get(floor_url(plan.floor)).content.decode()

    marks = {tag["data-floor"]: tag["data-plan"] for tag in marked(page, "data-floor")}
    assert marks == {"man-f1": "yes", "man-f2": "no"}


# A plan and its contours appear in one operation


def test_a_space_of_any_type_under_the_floor_may_carry_a_contour(first_floor, make_space):
    """A stairwell, a shaft and a void take up floor area no less than an office does."""
    for code, type in (("man-f1-s", "stairwell"), ("man-f1-v", "void"), ("man-f1-sh", "shaft")):
        make_space(first_floor, code, code, type=type)

    plan = make_plan(
        first_floor,
        plan_svg(*((code, ENTRANCE_PATH) for code in ("man-f1-s", "man-f1-v", "man-f1-sh"))),
    )

    assert set(plan.contours.values_list("space__code", flat=True)) == {
        "man-f1-s", "man-f1-v", "man-f1-sh",
    }


def test_a_space_nested_below_a_direct_child_of_the_floor_may_carry_a_contour(
    first_floor, make_space
):
    """A cubicle inside a toilet is a space of the floor, with its own place on the drawing."""
    plan = make_plan(first_floor, plan_svg(("man-f1-a1", ENTRANCE_PATH)))

    assert [c.space.code for c in plan.contours.all()] == ["man-f1-a1"]


def test_a_path_naming_a_space_of_another_floor_is_not_a_contour_here(
    first_floor, make_floor, make_space
):
    """A contour belongs to the pair "plan + space", and the space comes from this floor."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")

    plan = make_plan(first_floor, plan_svg(("man-f2-a", ENTRANCE_PATH)))

    assert plan.contours.count() == 0


def test_a_file_that_is_not_a_plan_leaves_no_plan_and_no_contours(first_floor):
    """The parse is atomic with the plan: otherwise the floor gets a plan and no contours."""
    with pytest.raises(PlanUnreadable):
        make_plan(first_floor, "<svg xmlns='http://www.w3.org/2000/svg'></svg>")

    assert FloorPlan.objects.count() == 0
    assert Contour.objects.count() == 0


def test_a_plan_cannot_be_attached_to_a_space_that_is_not_a_floor(first_floor):
    """A plan belongs to a floor — an office never has a drawing of its own."""
    room = Space.objects.get(code="man-f1-a")
    plan = FloorPlan(
        floor=room,
        file=SimpleUploadedFile("plan.svg", plan_svg().encode()),
        valid_from=date(2020, 1, 1),
    )

    with pytest.raises(ValidationError):
        plan.full_clean()


def test_the_contours_of_a_plan_are_not_rebuilt_when_its_period_is_edited(plan):
    """The drawing is already parsed; editing the period must not rebuild it against today's tree.

    A space gets its code changed: on a second parse its path would become unmatched and
    the contour would disappear. A contour holds on to the space by a link, not by its
    code of today.
    """
    Space.objects.filter(code="man-f1-b").update(code="man-f1-renamed")

    plan.valid_to = date(2026, 1, 1)
    plan.save()

    assert plan.contours.count() == 2


# Uploading through the Django admin


def admin_upload(client, floor, source, valid_from=date(2020, 1, 1), valid_to=None):
    return client.post(
        reverse("admin:building_passport_floorplan_add"),
        {
            "floor": str(floor.pk),
            "file": SimpleUploadedFile("plan.svg", source.encode(), content_type="image/svg+xml"),
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if valid_to else "",
        },
    )


def test_a_plan_is_created_in_django_admin(admin_client, first_floor):
    """Until the upload form exists, plans are created by a platform administrator."""
    response = admin_upload(
        admin_client, first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH))
    )

    assert response.status_code == 302
    assert [c.space.code for c in FloorPlan.objects.get().contours.all()] == ["man-f1-a"]


def test_a_file_that_is_not_a_plan_is_rejected_in_admin_with_a_reason(admin_client, first_floor):
    """The rejection names the reason: otherwise the export gets fixed by guesswork."""
    response = admin_upload(admin_client, first_floor, "<svg viewBox='0 0 10 10'>")

    assert response.status_code == 200
    assert re.search(r"не читается как SVG", response.content.decode())
    assert FloorPlan.objects.count() == 0


# The history of layouts: the plan in force and non-overlapping periods


@pytest.fixture
def superseded(first_floor):
    """The previous plan: its period ended yesterday, but it stays in the history."""
    return make_plan(
        first_floor,
        plan_svg(("man-f1-a", ENTRANCE_PATH)),
        valid_from=day(-365),
        valid_to=day(-1),
    )


@pytest.fixture
def in_force(first_floor):
    """The plan in force: its period began a month ago and is not closed."""
    return make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30))


def floor_screen(client, member, floor):
    client.force_login(member)
    return client.get(floor_url(floor)).content.decode()


def test_the_floor_screen_renders_the_plan_in_force_today(
    client, member, first_floor, superseded
):
    """Work is planned against today's drawing, not against the one from before the rebuild."""
    current = make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    page = floor_screen(client, member, first_floor)

    assert set(contours_on(page)) == {"man-f1-b"}
    assert file_url(current) in page
    assert file_url(superseded) not in page


def test_a_plan_whose_period_has_not_begun_is_not_rendered(client, member, first_floor):
    """The rebuild is scheduled for the future: until its date the floor looks as it does now.

    It can only be scheduled by naming the day the current plan is closed on — otherwise
    the periods overlap and the new plan is not accepted.
    """
    current = make_plan(
        first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30), valid_to=day(29)
    )
    future = make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(30))

    page = floor_screen(client, member, first_floor)

    assert set(contours_on(page)) == {"man-f1-a"}
    assert file_url(current) in page
    assert file_url(future) not in page


def test_a_floor_whose_only_plan_has_not_begun_shows_no_plan(client, member, first_floor):
    """An empty middle is more honest than a future drawing: today the floor looks different.

    And it says "there is none in force" rather than "none uploaded": the floor does have
    a plan, its period simply has not begun, and there is no point uploading the same
    thing twice.
    """
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(30))

    page = floor_screen(client, member, first_floor)

    assert contours_on(page) == {}
    assert "нет действующего поэтажного плана" in page


def test_the_switcher_marks_a_floor_by_the_plan_in_force_today(
    client, member, first_floor, in_force, make_floor, make_space
):
    """The badge promises a drawing: a floor with only a future plan must not promise one."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    make_plan(second, plan_svg(("man-f2-a", ENTRANCE_PATH)), valid_from=day(30))

    page = floor_screen(client, member, first_floor)

    marks = {tag["data-floor"]: tag["data-plan"] for tag in marked(page, "data-floor")}
    assert marks == {"man-f1": "yes", "man-f2": "no"}


def test_a_superseded_plan_is_kept_rather_than_deleted(first_floor, superseded):
    """The history of layouts is what a plan has a period for: the previous drawing stays."""
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert FloorPlan.objects.filter(pk=superseded.pk).exists()


def test_a_superseded_plan_keeps_the_contours_it_was_drawn_with(
    first_floor, superseded, make_space
):
    """An old plan is not redrawn with today's spaces (ADR 0003).

    After the rebuild the floor gained a space that was not on the previous drawing. Its
    contour belongs to the new plan, and the old one stays with what it was drawn with:
    otherwise it is not an outdated picture but a wrong one.
    """
    make_space(first_floor, "man-f1-c", "каб102")

    current = make_plan(
        first_floor,
        plan_svg(("man-f1-b", ITP_PATH), ("man-f1-c", ENTRANCE_PATH)),
        valid_from=day(0),
    )

    assert [c.space.code for c in superseded.contours.all()] == ["man-f1-a"]
    assert sorted(c.space.code for c in current.contours.all()) == ["man-f1-b", "man-f1-c"]


def test_a_plan_overlapping_an_existing_plan_of_the_floor_is_rejected(first_floor, in_force):
    """A floor never has two plans in force: which of them is today's would be unknown."""
    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))


def test_a_rejected_overlap_leaves_the_existing_plan_in_force(
    client, member, first_floor, in_force
):
    """A rejection changes nothing: the plan that was in force stays in force."""
    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert list(FloorPlan.objects.all()) == [in_force]
    assert set(contours_on(floor_screen(client, member, first_floor))) == {"man-f1-a"}


def test_creating_a_plan_does_not_close_the_period_of_the_previous_one(first_floor, in_force):
    """Closing the previous period retroactively records the rebuild on an administrative day.

    The date is named by the uploader; the system does not invent it, so an overlap is a
    rejection rather than a silent closing of the previous plan.
    """
    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    in_force.refresh_from_db()
    assert in_force.valid_to is None


def test_a_plan_beginning_the_day_the_previous_one_ends_is_rejected(first_floor):
    """On that day both would be in force: a period includes its last day too."""
    make_plan(
        first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30), valid_to=day(-10)
    )

    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(-10))


def test_a_plan_beginning_the_day_after_the_previous_one_ends_is_accepted(
    client, member, first_floor
):
    """Adjacent periods are exactly what a history is: every day has its one and only plan."""
    make_plan(
        first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30), valid_to=day(-10)
    )

    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(-9))

    assert FloorPlan.objects.count() == 2
    assert set(contours_on(floor_screen(client, member, first_floor))) == {"man-f1-b"}


def test_a_plan_of_another_floor_may_hold_the_same_period(
    first_floor, in_force, make_floor, make_space
):
    """Non-overlapping is a rule within one floor: every floor has its own plan in force."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")

    make_plan(second, plan_svg(("man-f2-a", ENTRANCE_PATH)), valid_from=in_force.valid_from)

    assert FloorPlan.objects.count() == 2


def test_editing_a_period_into_an_overlap_is_rejected(first_floor, superseded):
    """Editing a period is the same write path: the rule belongs to the plan, not to a form."""
    current = make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    current.valid_from = superseded.valid_to
    with pytest.raises(ValidationError):
        current.save()

    current.refresh_from_db()
    assert current.valid_from == day(0)


def test_a_period_that_ends_before_it_begins_is_rejected(first_floor):
    """A period ending before it begins is not a period: it will never be in force."""
    with pytest.raises(ValidationError):
        make_plan(
            first_floor,
            plan_svg(("man-f1-a", ENTRANCE_PATH)),
            valid_from=day(0),
            valid_to=day(-1),
        )


def test_an_overlapping_plan_is_rejected_in_admin_with_a_reason(
    admin_client, first_floor, in_force
):
    """The rejection names the reason on the form: otherwise the date is fixed by guesswork."""
    response = admin_upload(
        admin_client, first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0)
    )

    assert response.status_code == 200
    assert re.search(r"период.*пересекается", response.content.decode(), re.IGNORECASE)
    assert FloorPlan.objects.count() == 1


def test_the_history_of_plans_does_not_write_the_validity_of_the_spaces_themselves(
    first_floor, superseded
):
    """`Space.valid_from` means when the space existed, not when its drawing did."""
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert set(Space.objects.values_list("valid_from", "valid_to")) == {(None, None)}


# The "space type" layer: colouring the contours and the legend


@pytest.fixture
def coloured_floor(first_floor, make_space):
    """A floor holding all three types of space plus something that belongs to none of them.

    "каб101вход" is leasable, "Коридор" is a common area, the heating substation is
    neither leasable nor common, and a stairwell is not a type of space at all.
    """
    Space.objects.filter(code="man-f1-a").update(is_leasable=True)
    corridor = make_space(first_floor, "man-f1-c", "Коридор")
    Space.objects.filter(pk=corridor.pk).update(is_common=True)
    make_space(first_floor, "man-f1-s", "ЛК-1", type="stairwell")
    make_plan(
        first_floor,
        plan_svg(
            ("man-f1-a", ENTRANCE_PATH),
            ("man-f1-b", ITP_PATH),
            ("man-f1-c", "M0 200 L100 200 L100 300 Z"),
            ("man-f1-s", "M400 200 L500 200 L500 300 Z"),
        ),
    )
    return first_floor


@pytest.fixture
def coloured(client, member, coloured_floor):
    return floor_screen(client, member, coloured_floor)


def test_the_floor_screen_renders_with_the_layer_applied(client, member, coloured_floor):
    """A screen with the layer renders: an error in the rule or in the markup is caught here."""
    client.force_login(member)

    response = client.get(floor_url(coloured_floor))

    assert response.status_code == 200


def test_each_of_the_three_types_is_painted_its_own_way(coloured):
    """Leasable, common and technical are visible without reading a single caption.

    What each contour is filled with is compared, not what colour it is: colour is the
    palette's business, and were a test to name it, it would break on the first change of
    theme.
    """
    assert painted_on(coloured) == {
        "man-f1-a": "leasable",
        "man-f1-c": "common",
        "man-f1-b": "technical",
    }


def test_a_space_that_is_neither_leased_nor_common_reads_as_technical(
    client, member, first_floor
):
    """Technical is the absence of both flags, unset ones included.

    That is exactly how the heating substation, the air handling room and the switchboard
    room are found. An unset flag means "no": a fourth colour for "unknown" would talk
    about the completeness of the data rather than about the building.
    """
    Space.objects.filter(code="man-f1-b").update(is_leasable=None, is_common=None)
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)))

    page = floor_screen(client, member, first_floor)

    assert painted_on(page) == {"man-f1-b": "technical"}


def test_a_space_marked_both_leasable_and_common_is_drawn_as_leasable(
    client, member, first_floor
):
    """The flags contradict each other; a leasable space is not a common one."""
    Space.objects.filter(code="man-f1-a").update(is_leasable=True, is_common=True)
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)))

    page = floor_screen(client, member, first_floor)

    assert painted_on(page) == {"man-f1-a": "leasable"}


@pytest.mark.parametrize("type", ["void", "shaft", "stairwell"])
def test_a_space_outside_the_three_types_is_outlined_without_a_fill(
    client, member, first_floor, make_space, type
):
    """A void, a shaft and a stairwell are drawn so that the drawing has no gaps in it.

    Filling them with one of the three colours would call them a type of space they are
    not, so the layer gives them nothing: there is a contour on the plan but no fill on
    it. The absence of `data-paint` is exactly what "not filled" looks like on the wire;
    how an unfilled contour is drawn is known to the stylesheet.
    """
    make_space(first_floor, "man-f1-x", "Не тип помещения", type=type)
    make_plan(first_floor, plan_svg(("man-f1-x", ENTRANCE_PATH)))

    tag = contours_on(floor_screen(client, member, first_floor))["man-f1-x"]

    assert tag["d"] == ENTRANCE_PATH
    assert "data-paint" not in tag


def test_the_screen_shows_a_legend_for_the_colouring(coloured):
    """A colour without a legend has to be guessed, and a guess reads as a fact."""
    assert set(legend_on(coloured)) == {"leasable", "common", "technical"}
    assert "Арендопригодные" in coloured
    assert "МОП" in coloured
    assert "Технические" in coloured


def test_a_space_outside_the_three_types_gets_no_legend_entry(coloured):
    """The stairwell is on the drawing, but there is nothing to explain: it has no fill."""
    assert "man-f1-s" in contours_on(coloured)
    assert len(legend_on(coloured)) == 3


def test_the_legend_explains_the_colours_of_this_floor_and_no_others(
    client, member, first_floor
):
    """An entry for a colour absent from the drawing is a caption to an empty space."""
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)))

    page = floor_screen(client, member, first_floor)

    assert set(legend_on(page)) == {"technical"}


def test_hovering_a_contour_says_what_its_colour_means(coloured):
    """The layer answers for a single space too: no matching a colour against the legend.

    A contour outside the layer is captioned with its name alone: it has no fill, and
    there is nothing to explain.
    """
    hovered = {code: tag["title-text"] for code, tag in contours_on(coloured).items()}

    assert "арендопригодное" in hovered["man-f1-a"]
    assert "общего пользования" in hovered["man-f1-c"]
    assert "техническое" in hovered["man-f1-b"]
    assert hovered["man-f1-s"] == "ЛК-1"
