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


@pytest.fixture
def colleague(django_user_model):
    """Второй сотрудник за тем же адресом — из одной конторы входят через один IP."""
    return django_user_model.objects.create_user("manager", password=PASSWORD)


def sign_in(client, username, password):
    return client.post(reverse("login"), {"username": username, "password": password})


def fail_to_sign_in(client, username, times):
    for _ in range(times):
        sign_in(client, username, "не тот пароль")


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


def test_passwords_stop_being_checked_after_five_misses(client, employee):
    """Без предела вход — оракул: пароль подбирается со скоростью ответа сервера."""
    fail_to_sign_in(client, "engineer", times=5)

    response = sign_in(client, "engineer", PASSWORD)

    # Правильный пароль — и всё равно отказ: перебор упёрся в лимит, а не в неудачу.
    assert response.status_code == 429
    assert not response.wsgi_request.user.is_authenticated


def test_a_successful_login_forgives_the_earlier_misses(client, employee):
    """Иначе опечатки, накопленные за месяцы, однажды сложатся в блокировку.

    Второй заход опять не доводит до предела: сложились бы обе серии — восемь
    промахов при лимите в пять, — и правильный пароль уже не пустил бы.
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
    """Иначе перебор чужого логина запирает контору: у всех один внешний адрес."""
    fail_to_sign_in(client, "engineer", times=5)

    response = sign_in(client, "manager", PASSWORD)

    assert response.wsgi_request.user.is_authenticated


def test_logout_ends_the_session(client, employee):
    """Выход доступен с любого экрана — кнопкой в шапке, то есть POST-ом."""
    client.force_login(employee)

    response = client.post(reverse("logout"), follow=True)

    assert not response.wsgi_request.user.is_authenticated
