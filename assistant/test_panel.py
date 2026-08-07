"""Панель ИИ-управляющего — то, что видно по HTTP.

Шов тот же, что и на остальных экранах: граница HTTP. Тесты отправляют сообщение
тестовым клиентом и читают ответ как страницу. Разметка панели, её классы и способ
открытия не проверяются — на этом этапе проверяется поведение переписки, а не оболочка.
"""

import pytest
from django.urls import reverse

from building_passport.models import Space
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db

# Заглушка выписана буквально, а не импортирована из кода: тест должен разойтись с
# реализацией, если ответ поменяется незаметно.
CANNED_REPLY = (
    "Пока я не подключён к данным паспорта — отвечаю заглушкой. "
    "Полноценные ответы появятся на следующем этапе."
)


@pytest.fixture
def employee(django_user_model):
    """Сотрудник УК без членства: панель не зависит от того, какие БЦ ему видны."""
    return django_user_model.objects.create_user("engineer")


@pytest.fixture
def member(django_user_model, downtown):
    """Сотрудник с доступом к БЦ — переписка проверяется на переходе между ними."""
    user = django_user_model.objects.create_user("manager")
    OrgMembership.objects.create(user=user, org=downtown)
    return user


def send(client, text):
    response = client.post(reverse("assistant:message"), {"text": text})
    return response, response.content.decode()


def make_building(org, name):
    return Space.objects.create(org=org, type="building", code=name.lower(), name=name)


def test_a_sent_message_comes_back_with_a_reply(client, employee):
    """Оболочка заведена целиком: вопрос уходит, ответ приходит без перезагрузки."""
    client.force_login(employee)

    response, panel = send(client, "Какая общая площадь Manhattan?")

    assert response.status_code == 200
    assert "Какая общая площадь Manhattan?" in panel
    assert CANNED_REPLY in panel


def test_a_second_message_arrives_to_a_conversation_that_remembers_the_first(client, employee):
    """Панель — переписка, а не форма: предыдущий вопрос никуда не девается."""
    client.force_login(employee)

    send(client, "Какая общая площадь Manhattan?")
    _, panel = send(client, "А год постройки?")

    assert "Какая общая площадь Manhattan?" in panel
    assert "А год постройки?" in panel
    assert panel.count(CANNED_REPLY) == 2


def test_an_empty_message_leaves_the_conversation_as_it_was(client, employee):
    """Отправленная пустота — это не вопрос, и отвечать на неё панели нечем."""
    client.force_login(employee)

    send(client, "Какая общая площадь Manhattan?")
    _, panel = send(client, "   ")

    assert panel.count(CANNED_REPLY) == 1


def test_the_conversation_is_still_there_after_moving_to_another_bc(client, member, downtown):
    """Ради этого переписка и лежит в сессии: вопрос переживает уход с экрана."""
    make_building(downtown, "Manhattan")
    tokyo = make_building(downtown, "Tokyo")
    client.force_login(member)

    send(client, "Какая общая площадь Manhattan?")
    another_bc = client.get(reverse("building_passport:bc_detail", args=[tokyo.pk]))
    listing = client.get(reverse("building_passport:bc_list"))

    assert "Какая общая площадь Manhattan?" in another_bc.content.decode()
    assert "Какая общая площадь Manhattan?" in listing.content.decode()


def test_a_visitor_who_has_not_signed_in_gets_no_panel(client):
    """Панель отвечает про здания клиентов — до входа её на экране быть не должно."""
    login_page = client.get(reverse("login"))

    assert reverse("assistant:message") not in login_page.content.decode()


def test_a_message_sent_without_a_session_lands_on_the_login_page(client):
    """Эндпойнт закрыт так же, как экраны: анонимный POST уходит на вход, а не в сессию."""
    response = client.post(reverse("assistant:message"), {"text": "Кто владелец Manhattan?"})

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_an_expired_session_takes_the_whole_page_to_the_login_screen(client):
    """HTMX идёт за редиректом сам, и форма входа оказалась бы вклеена внутрь панели.

    Сессия кончается на открытом экране — это обычный конец рабочего дня, а не
    редкий случай: сотрудник должен увидеть вход целой страницей.
    """
    response = client.post(
        reverse("assistant:message"),
        {"text": "Кто владелец Manhattan?"},
        headers={"HX-Request": "true"},
    )

    assert response["HX-Redirect"] == reverse("login")
    assert "csrfmiddlewaretoken" not in response.content.decode()
