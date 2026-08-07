"""Поэтажный план как данные: файл, его контуры и то, что видно на экране этажа.

Шов тот же, что у остальных экранов, — граница HTTP: тесты открывают этаж и файл
плана тестовым клиентом от имени пользователя с известным членством. Ниже HTTP
проверяется только то, чего по HTTP не наблюдать: что создание плана и разбор его
контуров — одна операция. Сам разбор SVG живёт в своём шве, `test_floor_plan_svg`.

Опора в разметке — атрибуты `data-contour` на контуре и `data-plan` на этаже в
переключателе. Это договор экрана, а не оформление: по первому план и дерево будут
находить друг друга, второй говорит, есть ли на этаже чертёж.
"""

import re
from datetime import date
from html.parser import HTMLParser

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from building_passport.floor_plan_svg import PlanUnreadable
from building_passport.models import Contour, FloorPlan, Space

pytestmark = pytest.mark.django_db

VIEW_BOX = "0 0 800 600"
ENTRANCE_PATH = "M0 0 L100 0 L100 100 Z"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Загруженные файлы уезжают во временный каталог, а не в рабочую копию."""
    settings.MEDIA_ROOT = tmp_path


def plan_svg(*contours, view_box=VIEW_BOX):
    """Чертёж этажа: обводки помещений по кодам плюс стена, которая контуром не станет."""
    paths = "".join(f'<path id="{code}" d="{d}" />' for code, d in contours)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">'
        f'<path d="M0 0 L800 0" />{paths}</svg>'
    )


def make_plan(floor, source, valid_from=date(2020, 1, 1)):
    return FloorPlan.objects.create(
        floor=floor,
        file=SimpleUploadedFile("plan.svg", source.encode(), content_type="image/svg+xml"),
        valid_from=valid_from,
    )


@pytest.fixture
def plan(first_floor):
    """План первого этажа: обведены «каб101вход» и ИТП, «каб101» не нанесён."""
    return make_plan(
        first_floor,
        plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-b", "M200 0 L300 0 L300 100 Z")),
    )


def floor_url(floor):
    return reverse("building_passport:floor", args=[floor.building_id, floor.pk])


def file_url(plan):
    return reverse("building_passport:floor_plan_svg", args=[plan.pk])


@pytest.fixture
def floor_page(client, member, plan):
    client.force_login(member)
    return client.get(floor_url(plan.floor)).content.decode()


@pytest.fixture
def their_plan(central, make_floor, make_space):
    """План другого клиента — то, чего не должно быть видно ни экраном, ни файлом."""
    theirs = Space.objects.create(org=central, type="building", code="ctr", name="Central Tower")
    floor = make_floor(theirs, 1)
    make_space(floor, "ctr-f1-a", "Кабинет")
    return make_plan(floor, plan_svg(("ctr-f1-a", ENTRANCE_PATH)))


class Marked(HTMLParser):
    """Теги, несущие атрибут-договор экрана: их атрибуты и их подпись.

    Подпись контура — вложенный в него `<title>`: имя помещения всплывает при
    наведении само, без единой строки на стороне браузера. Читается она разбором,
    а не поиском по тексту страницы: то же имя стоит в дереве слева, и поиск нашёл
    бы его там, даже если до плана оно не доехало.
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


# Файл плана


def test_a_member_gets_the_file_of_their_own_plan(client, member, plan):
    """Чертёж отдаёт приложение, поэтому он и доезжает до сотрудника целиком."""
    client.force_login(member)

    response = client.get(file_url(plan))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert b"man-f1-a" in b"".join(response.streaming_content)


def test_the_file_of_another_organisations_plan_is_missing_rather_than_forbidden(
    client, member, their_plan
):
    """Ровно та утечка, ради которой чокпоинт и заведён (ADR 0001): чужой план недоступен.

    403 отвечал бы, что такой план есть, — а адрес файла угадывается или утекает
    из чужой вкладки, и тогда ответ выдал бы чертёж другого клиента.
    """
    client.force_login(member)

    assert client.get(file_url(their_plan)).status_code == 404


def test_an_anonymous_request_for_the_file_is_sent_to_login(client, plan):
    """До входа не видно и чертежей: файл — такой же путь чтения, как экран."""
    response = client.get(file_url(plan))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_a_superuser_reaches_any_organisations_plan_and_its_file(
    client, django_user_model, their_plan
):
    """Разработчик воспроизводит проблему клиента, не выписывая себе членство."""
    client.force_login(django_user_model.objects.create_superuser("developer"))

    assert client.get(floor_url(their_plan.floor)).status_code == 200
    assert client.get(file_url(their_plan)).status_code == 200


def test_the_file_is_served_sandboxed(client, member, plan):
    """SVG — исполняемый формат: открытый по адресу напрямую, он бы выполнялся у нас.

    Файл приходит от загрузившего, а раздаётся с домена приложения, поэтому ответ
    отправляется в песочницу и без угадывания типа.
    """
    client.force_login(member)

    response = client.get(file_url(plan))

    assert "sandbox" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


# План на экране этажа


def test_a_floor_with_a_plan_opens(client, member, plan):
    """Экран с планом отрисовывается: ошибка шаблона обнаруживается здесь."""
    client.force_login(member)

    response = client.get(floor_url(plan.floor))

    assert response.status_code == 200
    assert "Поэтажный план для этого этажа не загружен" not in response.content.decode()


def test_each_drawn_space_is_outlined_on_the_plan(floor_page):
    """План — это помещения, нарисованные: обведено ровно то, что нанесено."""
    assert set(contours_on(floor_page)) == {"man-f1-a", "man-f1-b"}


def test_a_contour_is_drawn_along_the_geometry_it_was_authored_with(floor_page):
    """Помещение узнают по его форме, а не по прямоугольнику вместо неё."""
    assert contours_on(floor_page)["man-f1-a"]["d"] == ENTRANCE_PATH


def test_a_space_with_no_path_in_the_file_is_not_drawn(floor_page):
    """Помещению без контура форму не выдумывают — оно остаётся только в дереве."""
    assert "man-f1-a1" not in contours_on(floor_page)
    assert "man-f1-a1" in floor_page


def test_hovering_a_contour_shows_the_name_of_its_space(floor_page):
    """Этаж просматривают, не проваливаясь в каждое помещение по очереди."""
    assert contours_on(floor_page)["man-f1-a"]["title-text"] == "каб101вход"


def test_the_drawing_is_asked_for_through_the_application(floor_page, plan):
    """Чертёж едет через тот же чокпоинт, что и всё остальное, — а не из /media/."""
    assert file_url(plan) in floor_page
    assert "/media/" not in floor_page


def test_a_contour_over_a_space_of_another_organisation_is_not_drawn(
    client, member, central, first_floor
):
    """Чужая строка под этим этажом не должна проехать на экран именем и формой.

    Такой строки в исправных данных нет; проверяется, что контуры отбираются через
    чокпоинт, как и дерево, а не показываются просто потому, что лежат в плане.
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
    """План принадлежит этажу: соседний чертёж на этот экран не подмешивается."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    make_plan(second, plan_svg(("man-f2-a", ENTRANCE_PATH)))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert contours_on(page) == {}


# Переключатель этажей


def test_the_switcher_shows_which_floors_have_a_plan(
    client, member, plan, make_floor, make_space
):
    """Иначе по этажам щёлкают в надежде найти чертёж."""
    second = make_floor(plan.floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    client.force_login(member)

    page = client.get(floor_url(plan.floor)).content.decode()

    marks = {tag["data-floor"]: tag["data-plan"] for tag in marked(page, "data-floor")}
    assert marks == {"man-f1": "yes", "man-f2": "no"}


# План и его контуры появляются одной операцией


def test_a_space_of_any_type_under_the_floor_may_carry_a_contour(first_floor, make_space):
    """Лестничная клетка, шахта и проём второго света занимают площадь этажа не меньше кабинета."""
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
    """Кабина внутри уборной — тоже помещение этажа, и на чертеже она своя."""
    plan = make_plan(first_floor, plan_svg(("man-f1-a1", ENTRANCE_PATH)))

    assert [c.space.code for c in plan.contours.all()] == ["man-f1-a1"]


def test_a_path_naming_a_space_of_another_floor_is_not_a_contour_here(
    first_floor, make_floor, make_space
):
    """Контур принадлежит паре «план + помещение», и помещение — с этого этажа."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")

    plan = make_plan(first_floor, plan_svg(("man-f2-a", ENTRANCE_PATH)))

    assert plan.contours.count() == 0


def test_a_file_that_is_not_a_plan_leaves_no_plan_and_no_contours(first_floor):
    """Разбор атомарен с планом: иначе на этаже оказался бы план без контуров."""
    with pytest.raises(PlanUnreadable):
        make_plan(first_floor, "<svg xmlns='http://www.w3.org/2000/svg'></svg>")

    assert FloorPlan.objects.count() == 0
    assert Contour.objects.count() == 0


def test_a_plan_cannot_be_attached_to_a_space_that_is_not_a_floor(first_floor):
    """План принадлежит этажу — у кабинета своего чертежа не бывает."""
    room = Space.objects.get(code="man-f1-a")
    plan = FloorPlan(
        floor=room,
        file=SimpleUploadedFile("plan.svg", plan_svg().encode()),
        valid_from=date(2020, 1, 1),
    )

    with pytest.raises(ValidationError):
        plan.full_clean()


def test_the_contours_of_a_plan_are_not_rebuilt_when_its_period_is_edited(plan):
    """Чертёж уже разобран; правка периода не должна пересобрать его по сегодняшнему дереву.

    Помещению меняют код: при повторном разборе его путь стал бы непривязанным и
    контур бы исчез. Контур держится за помещение связью, а не за его сегодняшний код.
    """
    Space.objects.filter(code="man-f1-b").update(code="man-f1-renamed")

    plan.valid_to = date(2026, 1, 1)
    plan.save()

    assert plan.contours.count() == 2


# Загрузка через админку Django


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("developer"))
    return client


def admin_upload(client, floor, source):
    return client.post(
        reverse("admin:building_passport_floorplan_add"),
        {
            "floor": str(floor.pk),
            "file": SimpleUploadedFile("plan.svg", source.encode(), content_type="image/svg+xml"),
            "valid_from": "2020-01-01",
            "valid_to": "",
        },
    )


def test_a_plan_is_created_in_django_admin(admin_client, first_floor):
    """Пока формы загрузки нет, планы заводит администратор платформы."""
    response = admin_upload(
        admin_client, first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH))
    )

    assert response.status_code == 302
    assert [c.space.code for c in FloorPlan.objects.get().contours.all()] == ["man-f1-a"]


def test_a_file_that_is_not_a_plan_is_rejected_in_admin_with_a_reason(admin_client, first_floor):
    """Отказ называет причину: иначе экспорт правят наугад, глядя на пустой план."""
    response = admin_upload(admin_client, first_floor, "<svg viewBox='0 0 10 10'>")

    assert response.status_code == 200
    assert re.search(r"не читается как SVG", response.content.decode())
    assert FloorPlan.objects.count() == 0
