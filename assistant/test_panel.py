"""The AI manager panel — what is visible over HTTP.

The seam is the same as on the other screens: the HTTP boundary. The tests send a message
with the test client and read the response as a page. The panel's markup, its classes and
the way it opens are not checked — at this stage the behaviour of the conversation is
checked, not the shell.
"""

import pytest
from django.urls import reverse

from building_passport.models import Space
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db

# The stub is written out literally rather than imported from the code: the test must
# diverge from the implementation if the reply changes unnoticed.
CANNED_REPLY = (
    "Пока я не подключён к данным паспорта — отвечаю заглушкой. "
    "Полноценные ответы появятся на следующем этапе."
)


@pytest.fixture
def employee(django_user_model):
    """A management-company employee without a membership: the panel does not depend on
    which BCs are visible to them."""
    return django_user_model.objects.create_user("engineer")


@pytest.fixture
def member(django_user_model, downtown):
    """An employee with access to BCs — the conversation is checked on moving between them."""
    user = django_user_model.objects.create_user("manager")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


def send(client, text):
    response = client.post(reverse("assistant:message"), {"text": text})
    return response, response.content.decode()


def make_building(org, name):
    return Space.objects.create(org=org, type="building", code=name.lower(), name=name)


def test_a_sent_message_comes_back_with_a_reply(client, employee):
    """The shell is wired end to end: the question goes out, the answer comes back without a reload."""
    client.force_login(employee)

    response, panel = send(client, "Какая общая площадь Manhattan?")

    assert response.status_code == 200
    assert "Какая общая площадь Manhattan?" in panel
    assert CANNED_REPLY in panel


def test_a_second_message_arrives_to_a_conversation_that_remembers_the_first(client, employee):
    """The panel is a conversation, not a form: the previous question does not go anywhere."""
    client.force_login(employee)

    send(client, "Какая общая площадь Manhattan?")
    _, panel = send(client, "А год постройки?")

    assert "Какая общая площадь Manhattan?" in panel
    assert "А год постройки?" in panel
    assert panel.count(CANNED_REPLY) == 2


def test_an_empty_message_leaves_the_conversation_as_it_was(client, employee):
    """Sent emptiness is not a question, and the panel has nothing to answer it with."""
    client.force_login(employee)

    send(client, "Какая общая площадь Manhattan?")
    _, panel = send(client, "   ")

    assert panel.count(CANNED_REPLY) == 1


def test_the_conversation_is_still_there_after_moving_to_another_bc(client, member, downtown):
    """This is what the conversation lies in the session for: the question survives leaving the screen."""
    make_building(downtown, "Manhattan")
    tokyo = make_building(downtown, "Tokyo")
    client.force_login(member)

    send(client, "Какая общая площадь Manhattan?")
    another_bc = client.get(reverse("building_passport:bc_detail", args=[tokyo.pk]))
    listing = client.get(reverse("building_passport:bc_list"))

    assert "Какая общая площадь Manhattan?" in another_bc.content.decode()
    assert "Какая общая площадь Manhattan?" in listing.content.decode()


def test_a_visitor_who_has_not_signed_in_gets_no_panel(client):
    """The panel answers about clients' buildings — before sign-in it must not be on the screen."""
    login_page = client.get(reverse("login"))

    assert reverse("assistant:message") not in login_page.content.decode()


def test_a_message_sent_without_a_session_lands_on_the_login_page(client):
    """The endpoint is closed the same way the screens are: an anonymous POST goes to sign-in,
    not into a session."""
    response = client.post(reverse("assistant:message"), {"text": "Кто владелец Manhattan?"})

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_an_expired_session_takes_the_whole_page_to_the_login_screen(client):
    """HTMX follows a redirect on its own, and the sign-in form would end up pasted inside
    the panel.

    A session ending while a screen is open is an ordinary end of the working day, not a
    rare case: the employee must see the sign-in as a whole page.
    """
    response = client.post(
        reverse("assistant:message"),
        {"text": "Кто владелец Manhattan?"},
        headers={"HX-Request": "true"},
    )

    assert response["HX-Redirect"] == reverse("login")
    assert "csrfmiddlewaretoken" not in response.content.decode()
