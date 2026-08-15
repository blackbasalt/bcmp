"""An organisation administrator uploading a plan — the first write path outside the admin.

The seam is the same as for the other screens — the HTTP boundary: the tests open a
floor and submit the form with the test client on behalf of a user with a known
membership. What is checked is observable: whether the form is shown, which status code
the request answers with, what is left in the database after a rejection and what is
visible on the screen after a success.

The foothold in the markup is the `data-upload` attribute on the form itself. That is a
contract of the screen: it shows whether the upload is offered, and to an employee
without the administrator right it is not offered at all.

The drawing, the parsing of its markup and the floor address are taken from
`test_floor_plan` — the plan fixtures live there, and a second definition of the same
drawing would drift from the first. Only what is missing there is defined here: the
organisation administrator and the form submission itself.
"""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from building_passport.models import Contour, FloorPlan, Space
from parties.models import OrgMembership

from .test_floor_plan import (
    ENTRANCE_PATH,
    ITP_PATH,
    day,
    floor_url,
    marked,
    plan_svg,
    stated,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Uploaded files go into a temporary directory rather than into the working copy.

    It stands here as its own copy instead of being imported: a fixture is auto-applied
    only in the module where it is declared.
    """
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def administrator(django_user_model, downtown):
    """An organisation administrator: the same employee, with the right to maintain data."""
    user = django_user_model.objects.create_user("director")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    return user


def open_floor(client, user, floor):
    client.force_login(user)
    return client.get(floor_url(floor)).content.decode()


def upload(client, floor, source=None, valid_from=None, file_name="plan.svg"):
    """Submit the upload form — to the same address the floor is opened at."""
    source = plan_svg(("man-f1-a", ENTRANCE_PATH)) if source is None else source
    return client.post(
        floor_url(floor),
        {
            "file": SimpleUploadedFile(file_name, source.encode(), content_type="image/svg+xml"),
            "valid_from": (valid_from or day(0)).isoformat(),
        },
    )


def upload_form(page):
    """The upload form on the screen — or nothing, if it is not offered."""
    forms = marked(page, "data-upload")
    return forms[0] if forms else None


# Who may upload


def test_an_administrator_of_the_organisation_is_offered_the_upload(
    client, administrator, first_floor
):
    """Maintaining one's own buildings no longer requires the Django admin."""
    assert upload_form(open_floor(client, administrator, first_floor)) is not None


def test_a_member_without_the_flag_is_offered_no_upload_control_at_all(
    client, member, first_floor
):
    """An action an employee cannot perform is not offered to them either."""
    assert upload_form(open_floor(client, member, first_floor)) is None


def test_a_platform_wide_staff_flag_grants_nothing(client, django_user_model, downtown, first_floor):
    """The write right is granted by a flag on the membership, not by `is_staff` (ADR 0005).

    All ten current users are marked `is_staff` — an accident of how the database was
    filled, not a decision. Were the right derived from it, an employee maintaining one
    client would write into the data of any of them.
    """
    staffer = django_user_model.objects.create_user("clerk", is_staff=True)
    OrgMembership.objects.create(user=staffer, org=downtown, is_admin=False)
    client.force_login(staffer)

    assert upload_form(client.get(floor_url(first_floor)).content.decode()) is None
    assert upload(client, first_floor).status_code == 403


def test_administering_one_organisation_does_not_administer_another(
    client, django_user_model, downtown, central, make_floor
):
    """Administratorship belongs to the pair "employee + organisation" (ADR 0005).

    One and the same employee maintains the data of one client and stays an ordinary
    reader at another — a global flag cannot say that.
    """
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=False)
    ours = make_floor(Space.objects.create(org=downtown, type="building", code="man"), 1)
    theirs = make_floor(Space.objects.create(org=central, type="building", code="ctr"), 1)

    assert upload_form(open_floor(client, user, ours)) is not None
    assert upload_form(open_floor(client, user, theirs)) is None


def test_a_member_without_the_flag_cannot_upload_even_by_posting_directly(
    client, member, first_floor
):
    """It is not only the button that is withheld: the right is checked on the request itself."""
    client.force_login(member)

    response = upload(client, first_floor)

    assert response.status_code == 403
    assert FloorPlan.objects.count() == 0


def test_an_anonymous_request_to_the_upload_path_is_sent_to_login(client, first_floor):
    """Before signing in nothing is written — just as nothing is read."""
    response = upload(client, first_floor)

    assert response.status_code == 302
    assert reverse("login") in response.url
    assert FloorPlan.objects.count() == 0


def test_uploading_to_a_floor_of_another_organisation_is_missing_rather_than_forbidden(
    client, administrator, central, make_floor
):
    """Another client's floor answers reads and writes the same way: it does not exist.

    A 403 would confirm that the floor is there — exactly the leak the checkpoint exists
    for (ADR 0001).
    """
    theirs = make_floor(Space.objects.create(org=central, type="building", code="ctr"), 1)
    client.force_login(administrator)

    assert upload(client, theirs).status_code == 404
    assert FloorPlan.objects.count() == 0


def test_a_superuser_uploads_without_granting_themselves_a_membership(
    client, django_user_model, first_floor
):
    """A platform administrator writes through the admin anyway; no point forbidding it here."""
    client.force_login(django_user_model.objects.create_superuser("developer"))

    assert upload(client, first_floor).status_code == 302
    assert FloorPlan.objects.count() == 1


# What happens on upload


@pytest.fixture
def uploaded(client, administrator, first_floor):
    """A successful upload: a drawing with one space outlined, in force today."""
    client.force_login(administrator)
    return upload(client, first_floor)


def test_a_successful_upload_returns_to_the_floor_screen(uploaded, first_floor):
    """The uploader comes back to where they clicked — and sees the result, not the form."""
    assert uploaded.status_code == 302
    assert uploaded.url == floor_url(first_floor)


def test_the_contours_of_the_new_plan_come_from_the_uploaded_file(uploaded):
    """Geometry is not entered by hand: the contours are taken from the paths of the drawing."""
    contour = Contour.objects.get()

    assert contour.space.code == "man-f1-a"
    assert contour.path_d == ENTRANCE_PATH


def test_the_upload_records_the_date_the_layout_took_effect(client, administrator, first_floor):
    """A plan records when the building changed, not when someone got round to the upload."""
    client.force_login(administrator)

    upload(client, first_floor, valid_from=date(2019, 3, 14))

    assert FloorPlan.objects.get().valid_from == date(2019, 3, 14)


def test_the_new_plan_replaces_the_old_one_on_screen_without_further_action(
    client, administrator, first_floor
):
    """After a rebuild the screen shows today's drawing, not yesterday's.

    The previous plan is closed with the date of the rebuild — today that is done in the
    admin (ADR 0004), and the upload form offers no such action.
    """
    client.force_login(administrator)
    upload(client, first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30))
    previous = FloorPlan.objects.get()
    previous.valid_to = day(-1)
    previous.save()

    upload(client, first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    page = client.get(floor_url(first_floor)).content.decode()
    assert {tag["data-contour"] for tag in marked(page, "data-contour")} == {"man-f1-b"}


def test_the_screen_confirms_that_the_plan_was_loaded(client, administrator, first_floor):
    """The reloaded screen is the confirmation — but it still has to be said in words."""
    client.force_login(administrator)

    upload(client, first_floor)

    assert "План загружен" in stated(client.get(floor_url(first_floor)).content.decode())


def test_a_plan_dated_ahead_is_said_not_to_be_on_the_screen_yet(
    client, administrator, first_floor
):
    """Otherwise an unchanged screen reads as a lost file.

    Nothing will be said about the previous plan: the floor may have had none at all, and
    promising a drawing that does not exist is the same invention as a pre-filled date.
    """
    client.force_login(administrator)

    upload(client, first_floor, valid_from=day(30))

    page = client.get(floor_url(first_floor)).content.decode()
    assert "экран этажа его не показывает" in stated(page)
    assert "нет действующего поэтажного плана" in page


def test_the_upload_is_offered_on_a_floor_with_no_plan_at_all(
    client, administrator, first_floor
):
    """The empty state is where an absence is noticed and where it gets fixed."""
    page = open_floor(client, administrator, first_floor)

    assert "нет действующего поэтажного плана" in page
    assert upload_form(page) is not None


def test_the_upload_stays_offered_on_a_floor_that_already_has_a_plan(
    client, administrator, first_floor
):
    """A rebuild is ordinary: the next plan is created where the current one is looked at."""
    client.force_login(administrator)
    upload(client, first_floor, valid_from=day(-30))

    page = client.get(floor_url(first_floor)).content.decode()

    assert upload_form(page) is not None


# What is rejected, and with what explanation


def test_an_upload_overlapping_an_existing_plan_is_rejected_with_an_explanation(
    client, administrator, first_floor
):
    """A floor never has two plans in force (ADR 0004), and the reason is named on the form."""
    client.force_login(administrator)
    upload(client, first_floor, valid_from=day(-30))

    response = upload(client, first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert response.status_code == 200
    assert "пересекается" in stated(response.content.decode())


def test_a_rejected_overlap_leaves_the_existing_plan_in_force(
    client, administrator, first_floor
):
    """A rejection changes nothing: the plan that was in force stays in force."""
    client.force_login(administrator)
    upload(client, first_floor, valid_from=day(-30))
    existing = FloorPlan.objects.get()

    upload(client, first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert list(FloorPlan.objects.all()) == [existing]
    existing.refresh_from_db()
    assert existing.valid_to is None
    page = client.get(floor_url(first_floor)).content.decode()
    assert {tag["data-contour"] for tag in marked(page, "data-contour")} == {"man-f1-a"}


def test_a_file_that_is_not_a_usable_svg_is_rejected_with_a_reason(
    client, administrator, first_floor
):
    """The reason is named so the export gets fixed instead of guesses about an empty plan."""
    client.force_login(administrator)

    response = upload(client, first_floor, "<svg viewBox='0 0 10 10'>")

    assert response.status_code == 200
    assert "не читается как SVG" in stated(response.content.decode())
    assert FloorPlan.objects.count() == 0


def test_a_file_without_a_view_box_is_rejected_with_a_reason(
    client, administrator, first_floor
):
    """Without a coordinate system there is nothing to align the contours with."""
    client.force_login(administrator)

    response = upload(
        client,
        first_floor,
        '<svg xmlns="http://www.w3.org/2000/svg"><path id="man-f1-a" d="M0 0 L1 1 Z"/></svg>',
    )

    assert response.status_code == 200
    assert "нет viewBox" in stated(response.content.decode())
    assert FloorPlan.objects.count() == 0


def test_a_rejected_upload_shows_the_form_again_on_the_floor_screen(
    client, administrator, first_floor
):
    """The rejection arrives on the same screen: the floor, the tree and the form stay in place."""
    client.force_login(administrator)

    page = upload(client, first_floor, "<svg viewBox='0 0 10 10'>").content.decode()

    assert upload_form(page) is not None
    assert "каб101вход" in page


# What is not rejected


def test_an_upload_with_unmatched_paths_succeeds_with_the_problems_reported(
    client, administrator, first_floor
):
    """A plan finds what has not been recorded, so it must load against an incomplete tree."""
    client.force_login(administrator)

    response = upload(
        client,
        first_floor,
        plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)),
    )

    assert response.status_code == 302
    page = client.get(floor_url(first_floor)).content.decode()
    assert {tag["data-unmatched"] for tag in marked(page, "data-unmatched")} == {"man-f1-zz"}
    assert "Нанесено 1 из 3 помещений" in stated(page)


def test_an_upload_leaving_spaces_without_a_contour_succeeds(
    client, administrator, first_floor
):
    """A space with no path in the drawing is a finding, not a reason to refuse the upload."""
    client.force_login(administrator)

    response = upload(client, first_floor)

    assert response.status_code == 302
    page = client.get(floor_url(first_floor)).content.decode()
    assert "Нанесено 1 из 3 помещений" in stated(page)
