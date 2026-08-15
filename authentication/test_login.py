"""Signing in — what is visible over HTTP.

The tests hit named addresses with the test client and check what is observable: where it
led, what the response code is, whether there is an error message. Markup, classes and
headings are not checked — they change on every pass over the design.
"""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

pytestmark = pytest.mark.django_db


PASSWORD = "правильный-пароль"


@pytest.fixture
def employee(django_user_model):
    """A management-company employee without a membership: signing in does not depend on
    what is visible to them."""
    return django_user_model.objects.create_user("engineer", password=PASSWORD)


@pytest.fixture
def colleague(django_user_model):
    """A second employee behind the same address — one office signs in through one IP."""
    return django_user_model.objects.create_user("manager", password=PASSWORD)


def sign_in(client, username, password):
    return client.post(reverse("login"), {"username": username, "password": password})


def fail_to_sign_in(client, username, times):
    for _ in range(times):
        sign_in(client, username, "не тот пароль")


def test_the_login_page_renders(client):
    """There were no templates in the project at all, and the login page crashed on render."""
    response = client.get(reverse("login"))

    assert response.status_code == 200


def test_valid_credentials_land_on_the_bc_list(client, employee):
    """The employee lands straight on the data, not on an intermediate page."""
    response = client.post(
        reverse("login"), {"username": "engineer", "password": PASSWORD}, follow=True
    )

    assert response.redirect_chain[-1][0] == reverse("building_passport:bc_list")
    assert response.status_code == 200


def test_wrong_credentials_come_back_with_a_message_instead_of_a_session(client, employee):
    """The user must understand that they got the password wrong, not that the site is down."""
    response = client.post(
        reverse("login"), {"username": "engineer", "password": "не тот пароль"}
    )

    assert not response.wsgi_request.user.is_authenticated
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Неверный логин или пароль"
    ]


def test_passwords_stop_being_checked_after_five_misses(client, employee):
    """Without a limit, sign-in is an oracle: a password is guessed at the speed of the
    server's response."""
    fail_to_sign_in(client, "engineer", times=5)

    response = sign_in(client, "engineer", PASSWORD)

    # The right password — and still a refusal: the guessing hit the limit, not a failure.
    assert response.status_code == 429
    assert not response.wsgi_request.user.is_authenticated


def test_a_successful_login_forgives_the_earlier_misses(client, employee):
    """Otherwise typos accumulated over months would one day add up to a lock-out.

    The second run again stops short of the limit: had both series added up — eight misses
    against a limit of five — the right password would no longer have let anyone in.
    """
    fail_to_sign_in(client, "engineer", times=4)
    sign_in(client, "engineer", PASSWORD)
    client.post(reverse("logout"))

    fail_to_sign_in(client, "engineer", times=4)
    response = sign_in(client, "engineer", PASSWORD)

    assert response.wsgi_request.user.is_authenticated


def test_a_locked_login_does_not_lock_the_colleague_at_the_same_address(
    client, employee, colleague
):
    """Otherwise guessing at someone else's login locks the whole office out: everyone
    shares one external address."""
    fail_to_sign_in(client, "engineer", times=5)

    response = sign_in(client, "manager", PASSWORD)

    assert response.wsgi_request.user.is_authenticated


def test_logout_ends_the_session(client, employee):
    """Sign-out is available from any screen — by the button in the header, that is, by POST."""
    client.force_login(employee)

    response = client.post(reverse("logout"), follow=True)

    assert not response.wsgi_request.user.is_authenticated
