"""Вход в систему — то, что видно по HTTP.

Тесты обращаются к именованным адресам тестовым клиентом и проверяют наблюдаемое:
куда привело, какой код ответа, есть ли сообщение об ошибке. Разметка, классы и
заголовки не проверяются — они меняются на каждом проходе по дизайну.
"""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

pytestmark = pytest.mark.django_db


PASSWORD = "правильный-пароль"


@pytest.fixture
def employee(django_user_model):
    """Сотрудник УК без членства: вход не зависит от того, что ему видно."""
    return django_user_model.objects.create_user("engineer", password=PASSWORD)


def test_the_login_page_renders(client):
    """Шаблонов в проекте не было вовсе, и страница входа падала на рендере."""
    response = client.get(reverse("login"))

    assert response.status_code == 200


def test_valid_credentials_land_on_the_bc_list(client, employee):
    """Сотрудник попадает сразу на данные, а не на промежуточную страницу."""
    response = client.post(
        reverse("login"), {"username": "engineer", "password": PASSWORD}, follow=True
    )

    assert response.redirect_chain[-1][0] == reverse("building_passport:bc_list")
    assert response.status_code == 200


def test_wrong_credentials_come_back_with_a_message_instead_of_a_session(client, employee):
    """Пользователь должен понять, что ошибся паролем, а не что сайт лежит."""
    response = client.post(
        reverse("login"), {"username": "engineer", "password": "не тот пароль"}
    )

    assert not response.wsgi_request.user.is_authenticated
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Неверный логин или пароль"
    ]


def test_logout_ends_the_session(client, employee):
    """Выход доступен с любого экрана — кнопкой в шапке, то есть POST-ом."""
    client.force_login(employee)

    response = client.post(reverse("logout"), follow=True)

    assert not response.wsgi_request.user.is_authenticated
