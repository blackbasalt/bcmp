import uuid

import pytest
from django.conf import settings
from django.urls import NoReverseMatch, reverse

from building_passport import urls as building_passport_urls

pytestmark = pytest.mark.django_db


def test_stage_1_routes_reverse_under_the_building_passport_namespace():
    """The app's app_name and the project include agree, so URL names reverse."""
    building_id = uuid.uuid4()

    assert reverse("building_passport:bc_list") == "/"
    assert reverse("building_passport:bc_detail", args=[building_id]) == f"/bc/{building_id}/"


def test_no_path_is_registered_more_than_once():
    """The view once registered twice under one path — as `home` and `board` — exists once."""
    paths = [str(route.pattern) for route in building_passport_urls.urlpatterns]

    assert sorted(paths) == sorted(set(paths))


def test_the_old_bp_namespace_is_gone():
    with pytest.raises(NoReverseMatch):
        reverse("bp:home")


@pytest.mark.parametrize(
    "url_name, args",
    [
        ("building_passport:bc_list", []),
        ("building_passport:bc_detail", [uuid.uuid4()]),
    ],
)
def test_anonymous_request_to_a_screen_redirects_to_login(client, url_name, args):
    response = client.get(reverse(url_name, args=args))

    assert response.status_code == 302
    assert response.url.startswith(settings.LOGIN_URL)


def test_login_redirects_to_the_bc_list_rather_than_back_to_login():
    assert reverse(settings.LOGIN_REDIRECT_URL) == reverse("building_passport:bc_list")
    assert reverse(settings.LOGIN_REDIRECT_URL) != settings.LOGIN_URL
