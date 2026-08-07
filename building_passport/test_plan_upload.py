"""Загрузка плана администратором организации — первый путь записи вне админки.

Шов тот же, что и у остальных экранов, — граница HTTP: тесты открывают этаж и
отправляют форму тестовым клиентом от имени пользователя с известным членством.
Проверяется наблюдаемое: показана ли форма, каким кодом отвечает запрос, что
осталось в базе после отказа и что видно на экране после успеха.

Опора в разметке — атрибут `data-upload` на самой форме. Это договор экрана: по
нему видно, предложена ли загрузка, а сотруднику без права администратора она не
предлагается вовсе.

Чертёж, разбор его разметки и адрес этажа берутся у `test_floor_plan` — плановая
оснастка там и заведена, и второе определение того же чертежа разошлось бы с первым.
Здесь заводится только то, чего там нет: администратор организации и сама отправка
формы.
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
    """Загруженные файлы уезжают во временный каталог, а не в рабочую копию.

    Стоит здесь своей копией, а не берётся импортом: автоприменение фикстуры
    действует в том модуле, где она объявлена.
    """
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def administrator(django_user_model, downtown):
    """Администратор организации: тот же сотрудник УК, но с правом вести данные."""
    user = django_user_model.objects.create_user("director")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    return user


def open_floor(client, user, floor):
    client.force_login(user)
    return client.get(floor_url(floor)).content.decode()


def upload(client, floor, source=None, valid_from=None, file_name="plan.svg"):
    """Отправить форму загрузки — тем же адресом, каким этаж и открывают."""
    source = plan_svg(("man-f1-a", ENTRANCE_PATH)) if source is None else source
    return client.post(
        floor_url(floor),
        {
            "file": SimpleUploadedFile(file_name, source.encode(), content_type="image/svg+xml"),
            "valid_from": (valid_from or day(0)).isoformat(),
        },
    )


def upload_form(page):
    """Форма загрузки на экране — или ничего, если она не предложена."""
    forms = marked(page, "data-upload")
    return forms[0] if forms else None


# Кто может загружать


def test_an_administrator_of_the_organisation_is_offered_the_upload(
    client, administrator, first_floor
):
    """Ведение своих зданий перестаёт требовать админки Django."""
    assert upload_form(open_floor(client, administrator, first_floor)) is not None


def test_a_member_without_the_flag_is_offered_no_upload_control_at_all(
    client, member, first_floor
):
    """Действие, которого сотруднику не совершить, ему и не предлагается."""
    assert upload_form(open_floor(client, member, first_floor)) is None


def test_a_platform_wide_staff_flag_grants_nothing(client, django_user_model, downtown, first_floor):
    """Право на запись даёт флаг на членстве, а не `is_staff` (ADR 0005).

    Все десять нынешних пользователей помечены `is_staff` — это случайность
    наполнения базы, а не решение. Если бы право выводилось из неё, сотрудник,
    ведущий одного клиента, писал бы в данные любого.
    """
    staffer = django_user_model.objects.create_user("clerk", is_staff=True)
    OrgMembership.objects.create(user=staffer, org=downtown, is_admin=False)
    client.force_login(staffer)

    assert upload_form(client.get(floor_url(first_floor)).content.decode()) is None
    assert upload(client, first_floor).status_code == 403


def test_administering_one_organisation_does_not_administer_another(
    client, django_user_model, downtown, central, make_floor
):
    """Администраторство принадлежит паре «сотрудник + организация» (ADR 0005).

    Один и тот же сотрудник ведёт данные одного клиента и остаётся обычным
    читателем у другого — глобальный флаг такого сказать не может.
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
    """Отказано не только показу кнопки: право проверяется на самом запросе."""
    client.force_login(member)

    response = upload(client, first_floor)

    assert response.status_code == 403
    assert FloorPlan.objects.count() == 0


def test_an_anonymous_request_to_the_upload_path_is_sent_to_login(client, first_floor):
    """До входа не пишут ничего — как и не читают."""
    response = upload(client, first_floor)

    assert response.status_code == 302
    assert reverse("login") in response.url
    assert FloorPlan.objects.count() == 0


def test_uploading_to_a_floor_of_another_organisation_is_missing_rather_than_forbidden(
    client, administrator, central, make_floor
):
    """Чужой этаж отвечает одинаково на чтение и на запись: его не существует.

    403 подтверждал бы, что этаж есть, — ровно та утечка, ради которой заведён
    чокпоинт (ADR 0001).
    """
    theirs = make_floor(Space.objects.create(org=central, type="building", code="ctr"), 1)
    client.force_login(administrator)

    assert upload(client, theirs).status_code == 404
    assert FloorPlan.objects.count() == 0


def test_a_superuser_uploads_without_granting_themselves_a_membership(
    client, django_user_model, first_floor
):
    """Администратор платформы и так пишет через админку: запрещать ему то же в приложении незачем."""
    client.force_login(django_user_model.objects.create_superuser("developer"))

    assert upload(client, first_floor).status_code == 302
    assert FloorPlan.objects.count() == 1


# Что происходит при загрузке


@pytest.fixture
def uploaded(client, administrator, first_floor):
    """Успешная загрузка: чертёж с одним обведённым помещением, действующий сегодня."""
    client.force_login(administrator)
    return upload(client, first_floor)


def test_a_successful_upload_returns_to_the_floor_screen(uploaded, first_floor):
    """Загрузивший возвращается туда, где нажимал, — и видит результат, а не форму."""
    assert uploaded.status_code == 302
    assert uploaded.url == floor_url(first_floor)


def test_the_contours_of_the_new_plan_come_from_the_uploaded_file(uploaded):
    """Геометрия руками не заводится: контуры сняты с путей чертежа."""
    contour = Contour.objects.get()

    assert contour.space.code == "man-f1-a"
    assert contour.path_d == ENTRANCE_PATH


def test_the_upload_records_the_date_the_layout_took_effect(client, administrator, first_floor):
    """План записывает, когда изменилось здание, а не когда до загрузки дошли руки."""
    client.force_login(administrator)

    upload(client, first_floor, valid_from=date(2019, 3, 14))

    assert FloorPlan.objects.get().valid_from == date(2019, 3, 14)


def test_the_new_plan_replaces_the_old_one_on_screen_without_further_action(
    client, administrator, first_floor
):
    """После перепланировки экран показывает сегодняшний чертёж, а не вчерашний.

    Прежний план закрывается датой перепланировки — сегодня это делают в админке
    (ADR 0004), и форма загрузки такого действия не предлагает.
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
    """Перезагруженный экран и есть подтверждение — но сказать о нём надо словами."""
    client.force_login(administrator)

    upload(client, first_floor)

    assert "План загружен" in stated(client.get(floor_url(first_floor)).content.decode())


def test_a_plan_dated_ahead_is_said_not_to_be_on_the_screen_yet(
    client, administrator, first_floor
):
    """Иначе неизменившийся экран читается как потерянный файл.

    Про прежний план сказано при этом не будет: этаж мог не иметь ни одного, и
    обещание чертежа, которого нет, — та же выдумка, что и подставленная дата.
    """
    client.force_login(administrator)

    upload(client, first_floor, valid_from=day(30))

    page = client.get(floor_url(first_floor)).content.decode()
    assert "экран этажа его не показывает" in stated(page)
    assert "нет действующего поэтажного плана" in page


def test_the_upload_is_offered_on_a_floor_with_no_plan_at_all(
    client, administrator, first_floor
):
    """Пустое состояние — то место, где отсутствие замечают и где его исправляют."""
    page = open_floor(client, administrator, first_floor)

    assert "нет действующего поэтажного плана" in page
    assert upload_form(page) is not None


def test_the_upload_stays_offered_on_a_floor_that_already_has_a_plan(
    client, administrator, first_floor
):
    """Перепланировка — обычное событие: следующий план заводят там же, где смотрят нынешний."""
    client.force_login(administrator)
    upload(client, first_floor, valid_from=day(-30))

    page = client.get(floor_url(first_floor)).content.decode()

    assert upload_form(page) is not None


# Что отклоняется, и с каким объяснением


def test_an_upload_overlapping_an_existing_plan_is_rejected_with_an_explanation(
    client, administrator, first_floor
):
    """У этажа не бывает двух действующих планов (ADR 0004), и причина названа на форме."""
    client.force_login(administrator)
    upload(client, first_floor, valid_from=day(-30))

    response = upload(client, first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert response.status_code == 200
    assert "пересекается" in stated(response.content.decode())


def test_a_rejected_overlap_leaves_the_existing_plan_in_force(
    client, administrator, first_floor
):
    """Отказ ничего не меняет: действующим остаётся тот план, что действовал."""
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
    """Причина названа, чтобы экспорт правили, а не гадали, почему план пуст."""
    client.force_login(administrator)

    response = upload(client, first_floor, "<svg viewBox='0 0 10 10'>")

    assert response.status_code == 200
    assert "не читается как SVG" in stated(response.content.decode())
    assert FloorPlan.objects.count() == 0


def test_a_file_without_a_view_box_is_rejected_with_a_reason(
    client, administrator, first_floor
):
    """Без системы координат контуры не с чем совместить — это не план."""
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
    """Отказ приходит на тот же экран: этаж, дерево и форма остаются на месте."""
    client.force_login(administrator)

    page = upload(client, first_floor, "<svg viewBox='0 0 10 10'>").content.decode()

    assert upload_form(page) is not None
    assert "каб101вход" in page


# Что не отклоняется


def test_an_upload_with_unmatched_paths_succeeds_with_the_problems_reported(
    client, administrator, first_floor
):
    """План — инструмент поиска незаведённого, и грузиться он обязан против неполного дерева."""
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
    """Помещение без пути на чертеже — находка, а не причина отказать в загрузке."""
    client.force_login(administrator)

    response = upload(client, first_floor)

    assert response.status_code == 302
    page = client.get(floor_url(first_floor)).content.decode()
    assert "Нанесено 1 из 3 помещений" in stated(page)
