"""Поэтажный план как данные: файл, его контуры и то, что видно на экране этажа.

Шов тот же, что у остальных экранов, — граница HTTP: тесты открывают этаж и файл
плана тестовым клиентом от имени пользователя с известным членством. Ниже HTTP
проверяется только то, чего по HTTP не наблюдать: что создание плана и разбор его
контуров — одна операция. Сам разбор SVG живёт в своём шве, `test_floor_plan_svg`.

Опора в разметке — атрибуты `data-contour` на контуре, `data-plan` на этаже в
переключателе, `data-select` с `data-drawn` на том, чем выбирают помещение,
`data-paint` с `data-legend` на окраске по слою и `data-unmatched` на пути, которому
не нашлось помещения. Это договор экрана, а не оформление: по ним план и дерево
находят друг друга, видно, есть ли на этаже чертёж, какие помещения на него не
нанесены, чем окрашен каждый контур и какие `id` в чертеже повисли.
"""

import re
from datetime import date, timedelta
from html.parser import HTMLParser

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from building_passport import plan_layer
from building_passport.floor_plan_svg import PlanUnreadable
from building_passport.models import Contour, FloorPlan, Space

pytestmark = pytest.mark.django_db

VIEW_BOX = "0 0 800 600"
ENTRANCE_PATH = "M0 0 L100 0 L100 100 Z"
ITP_PATH = "M400 0 L500 0 L500 100 Z"


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


def make_plan(floor, source, valid_from=date(2020, 1, 1), valid_to=None):
    return FloorPlan.objects.create(
        floor=floor,
        file=SimpleUploadedFile("plan.svg", source.encode(), content_type="image/svg+xml"),
        valid_from=valid_from,
        valid_to=valid_to,
    )


def day(offset):
    """Дата в днях от сегодняшней: «действующий» — свойство именно сегодняшнего дня."""
    return timezone.localdate() + timedelta(days=offset)


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


def card_url(space):
    return reverse("building_passport:space_card", args=[space.pk])


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


def legend_on(page):
    """Записи легенды по ключу разновидности — тому же, каким помечен контур."""
    return {tag["data-legend"]: tag for tag in marked(page, "data-legend")}


def painted_on(page):
    """Чем окрашен каждый контур: код помещения → ключ разновидности слоя.

    Контур без заливки в набор не попадает: он не окрашен, а обведён.
    """
    return {
        code: tag["data-paint"]
        for code, tag in contours_on(page).items()
        if "data-paint" in tag
    }


def overlay(page):
    """Слой контуров поверх чертежа — то, что рисует приложение, а не сам файл.

    Нужен там, где проверяется отсутствие лишнего пути: в самом чертеже путей
    сколько угодно, и считать их вперемешку с контурами нечего.
    """
    return re.search(r'<svg[^>]*aria-label="Контуры помещений".*?</svg>', page, re.DOTALL).group()


def stated(page):
    """Страница одной строкой: фраза не должна ломаться о перенос в разметке."""
    return " ".join(page.split())


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
    assert "нет действующего поэтажного плана" not in response.content.decode()


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
    """Этаж просматривают, не проваливаясь в каждое помещение по очереди.

    Имя стоит первым, а не единственным: слой дописывает к нему свою строку — что
    означает цвет, которым помещение залито.
    """
    assert contours_on(floor_page)["man-f1-a"]["title-text"].startswith("каб101вход")


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


# План и дерево — два вида одного выбора


def test_a_contour_opens_the_card_of_the_space_it_outlines(floor_page):
    """План расспрашивают, показывая пальцем: щелчок по контуру выбирает помещение."""
    entrance = Space.objects.get(code="man-f1-a")

    assert contours_on(floor_page)["man-f1-a"]["hx-get"] == card_url(entrance)


def test_the_tree_marks_which_spaces_are_missing_from_the_plan(floor_page):
    """План — самый острый инструмент проекта для поиска незаведённого.

    «каб101» на чертеже не обведён, и в дереве это видно, не сличая список с
    картинкой.
    """
    marks = {tag["data-select"]: tag["data-drawn"] for tag in marked(floor_page, "data-drawn")}

    assert marks == {"man-f1-a": "yes", "man-f1-a1": "no", "man-f1-b": "yes"}
    assert "нет контура" in floor_page


def test_a_space_missing_from_the_plan_is_still_selectable_from_the_tree(floor_page):
    """Именно эти помещения важнее прочих, а щёлкнуть по ним на чертеже негде."""
    undrawn = Space.objects.get(code="man-f1-a1")
    node = {tag["data-select"]: tag for tag in marked(floor_page, "data-drawn")}["man-f1-a1"]

    assert node["hx-get"] == card_url(undrawn)


def test_nothing_is_marked_in_the_tree_when_no_plan_is_in_force(
    client, member, first_floor
):
    """Без действующего плана не нанесено ничего, и метка на каждом узле — шум.

    План будущей перепланировки на этаже уже заведён: сегодня он не действует, и
    сказать по нему, что нанесено, а что нет, нельзя.
    """
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(30))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert marked(page, "data-drawn") == []
    assert "нет контура" not in page


# Полнота: сколько нанесено и что на чертеже повисло


def test_the_floor_screen_states_how_many_spaces_are_drawn_out_of_how_many_exist(floor_page):
    """Экран считает то, чего на плане нет, — и это самое ценное, что он умеет сказать.

    На этаже три помещения, обведены два: «каб101» не нанесён. Сличать дерево с
    чертежом глазами для этого не нужно.
    """
    assert "Нанесено 2 из 3 помещений" in stated(floor_page)


def test_a_space_with_no_contour_counts_into_the_figure_of_what_is_not_drawn(
    client, member, plan, make_space
):
    """Заведённое после плана помещение на чертеже не появляется — и счёт это говорит.

    Контуры плана не пересобираются (ADR 0003), поэтому новое помещение растит
    знаменатель, а не числитель.
    """
    make_space(plan.floor, "man-f1-c", "каб102")
    client.force_login(member)

    page = client.get(floor_url(plan.floor)).content.decode()

    assert "Нанесено 2 из 4 помещений" in stated(page)


def test_completeness_is_counted_in_spaces_rather_than_in_square_metres(client, member, plan):
    """Метрам нужен масштаб, которого план не объявляет, и площадь есть не у всех.

    Выдуманный масштаб дал бы цифру, которая выглядит точной и не является таковой.
    """
    Space.objects.filter(code="man-f1-a").update(area_m2=100)
    client.force_login(member)

    page = client.get(floor_url(plan.floor)).content.decode()

    assert "Нанесено 2 из 3 помещений" in stated(page)
    assert "м²" not in page


def test_no_contour_is_drawn_for_the_uncovered_remainder_of_the_floor(floor_page):
    """Разрыв между площадью этажа и суммой помещений — это находка, а не дыра в картинке.

    Синтетический контур «прочее» закрыл бы её выдуманной формой — той же ошибкой,
    что и `-1 м²`, только в другой среде. Поверх чертежа лежит ровно столько путей,
    сколько помещений обведено.
    """
    assert overlay(floor_page).count("<path") == len(contours_on(floor_page)) == 2


def test_nothing_is_counted_when_no_plan_is_in_force(client, member, first_floor):
    """Без действующего плана не нанесено ничего: «0 из 3» сказало бы то же, что пустой центр."""
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(30))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert "Нанесено" not in page


def test_a_path_matching_no_space_is_reported_on_the_floor_screen(client, member, first_floor):
    """Опечатка в `id` должна быть видна: план загрузился, а путь помещением не стал.

    Экран этажа — то место, где это обнаруживается: контуров на нём меньше, чем
    ожидал рисовавший, и причина названа рядом.
    """
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)))
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert {tag["data-unmatched"] for tag in marked(page, "data-unmatched")} == {"man-f1-zz"}
    assert "Нанесено 1 из 3 помещений" in stated(page)


def test_one_id_on_two_paths_is_named_once(client, member, first_floor):
    """Названа опечатка, а не каждый путь с нею: дважды она читается сбоем экрана.

    Дубликат `id` за известным помещением файл бы отклонил, а за неизвестным —
    переживает: план грузится и против неполного дерева.
    """
    make_plan(
        first_floor,
        plan_svg(("man-f1-zz", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)),
    )
    client.force_login(member)

    page = client.get(floor_url(first_floor)).content.decode()

    assert [tag["data-unmatched"] for tag in marked(page, "data-unmatched")] == ["man-f1-zz"]


def test_a_plan_whose_every_path_matched_reports_nothing_unmatched(floor_page):
    """Исправный чертёж не должен нести на экране предупреждения ни о чём."""
    assert marked(floor_page, "data-unmatched") == []


def test_the_unmatched_paths_are_kept_with_the_plan_that_was_read(first_floor):
    """Непривязанные пути замечаются при разборе, а показываются на экране этажа.

    Между этими двумя моментами их надо где-то держать, и держит их сам план:
    заново чертёж не разбирается.
    """
    plan = make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH), ("man-f1-zz", ITP_PATH)))

    assert plan.unmatched_ids == ["man-f1-zz"]


def test_the_unmatched_paths_are_not_recomputed_when_the_period_is_edited(plan):
    """Разбор был один раз (ADR 0003): правка периода не пересчитывает и непривязанное.

    Помещению меняют код — при повторном разборе его путь стал бы непривязанным.
    План остаётся с тем, с чем был прочитан.
    """
    Space.objects.filter(code="man-f1-b").update(code="man-f1-renamed")

    plan.valid_to = date(2026, 1, 1)
    plan.save()

    assert plan.unmatched_ids == []


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


# История планировок: действующий план и непересекающиеся периоды


@pytest.fixture
def superseded(first_floor):
    """Прежний план: его период закончился вчера, но сам он остаётся в истории."""
    return make_plan(
        first_floor,
        plan_svg(("man-f1-a", ENTRANCE_PATH)),
        valid_from=day(-365),
        valid_to=day(-1),
    )


@pytest.fixture
def in_force(first_floor):
    """Действующий план: период начался месяц назад и не закрыт."""
    return make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30))


def floor_screen(client, member, floor, **address):
    """Экран этажа глазами сотрудника. `address` — параметры адреса, вроде `layer`."""
    client.force_login(member)
    return client.get(floor_url(floor), address).content.decode()


def test_the_floor_screen_renders_the_plan_in_force_today(
    client, member, first_floor, superseded
):
    """Работы планируют по сегодняшнему чертежу, а не по тому, что был до перепланировки."""
    current = make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    page = floor_screen(client, member, first_floor)

    assert set(contours_on(page)) == {"man-f1-b"}
    assert file_url(current) in page
    assert file_url(superseded) not in page


def test_a_plan_whose_period_has_not_begun_is_not_rendered(client, member, first_floor):
    """Перепланировка назначена на будущее: до её даты этаж выглядит так, как сейчас.

    Назначить её можно, только назвав день, которым закрывается нынешний план, —
    иначе периоды пересекаются и новый план не принимается.
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
    """Пустой центр честнее будущего чертежа: сегодня этаж выглядит не так.

    И говорит он «нет действующего», а не «не загружен»: план у этажа есть, просто
    его период ещё не начался, и загружать второй раз то же самое незачем.
    """
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(30))

    page = floor_screen(client, member, first_floor)

    assert contours_on(page) == {}
    assert "нет действующего поэтажного плана" in page


def test_the_switcher_marks_a_floor_by_the_plan_in_force_today(
    client, member, first_floor, in_force, make_floor, make_space
):
    """Значок обещает чертёж: этаж с одним лишь будущим планом обещать его не должен."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")
    make_plan(second, plan_svg(("man-f2-a", ENTRANCE_PATH)), valid_from=day(30))

    page = floor_screen(client, member, first_floor)

    marks = {tag["data-floor"]: tag["data-plan"] for tag in marked(page, "data-floor")}
    assert marks == {"man-f1": "yes", "man-f2": "no"}


def test_a_superseded_plan_is_kept_rather_than_deleted(first_floor, superseded):
    """История планировок и есть то, ради чего у плана период: прежний чертёж остаётся."""
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert FloorPlan.objects.filter(pk=superseded.pk).exists()


def test_a_superseded_plan_keeps_the_contours_it_was_drawn_with(
    first_floor, superseded, make_space
):
    """Старый план не перерисовывается сегодняшними помещениями (ADR 0003).

    После перепланировки на этаже появилось помещение, которого на прежнем чертеже
    не было. Его контур принадлежит новому плану, а старый остаётся с тем, с чем
    был нарисован: иначе это не устаревшая картинка, а неверная.
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
    """У этажа не бывает двух действующих планов: какой из них сегодняшний — неизвестно."""
    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))


def test_a_rejected_overlap_leaves_the_existing_plan_in_force(
    client, member, first_floor, in_force
):
    """Отказ ничего не меняет: действующим остаётся тот план, что действовал."""
    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert list(FloorPlan.objects.all()) == [in_force]
    assert set(contours_on(floor_screen(client, member, first_floor))) == {"man-f1-a"}


def test_creating_a_plan_does_not_close_the_period_of_the_previous_one(first_floor, in_force):
    """Закрыть прежний период задним числом — записать перепланировку административным днём.

    Дату называет загружающий; система её не выдумывает, поэтому пересечение — отказ,
    а не молчаливое закрытие предыдущего плана.
    """
    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    in_force.refresh_from_db()
    assert in_force.valid_to is None


def test_a_plan_beginning_the_day_the_previous_one_ends_is_rejected(first_floor):
    """В этот день действовали бы оба: период включает и свой последний день."""
    make_plan(
        first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30), valid_to=day(-10)
    )

    with pytest.raises(ValidationError):
        make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(-10))


def test_a_plan_beginning_the_day_after_the_previous_one_ends_is_accepted(
    client, member, first_floor
):
    """Смежные периоды — это и есть история: у каждого дня свой единственный план."""
    make_plan(
        first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)), valid_from=day(-30), valid_to=day(-10)
    )

    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(-9))

    assert FloorPlan.objects.count() == 2
    assert set(contours_on(floor_screen(client, member, first_floor))) == {"man-f1-b"}


def test_a_plan_of_another_floor_may_hold_the_same_period(
    first_floor, in_force, make_floor, make_space
):
    """Непересечение — правило одного этажа: у каждого этажа свой действующий план."""
    second = make_floor(first_floor.building, 2)
    make_space(second, "man-f2-a", "каб201")

    make_plan(second, plan_svg(("man-f2-a", ENTRANCE_PATH)), valid_from=in_force.valid_from)

    assert FloorPlan.objects.count() == 2


def test_editing_a_period_into_an_overlap_is_rejected(first_floor, superseded):
    """Правка периода — тот же путь записи: правило принадлежит плану, а не форме."""
    current = make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    current.valid_from = superseded.valid_to
    with pytest.raises(ValidationError):
        current.save()

    current.refresh_from_db()
    assert current.valid_from == day(0)


def test_a_period_that_ends_before_it_begins_is_rejected(first_floor):
    """Период, кончающийся раньше начала, — не период: действующим он не станет никогда."""
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
    """Отказ называет причину на форме: иначе дату правят наугад, глядя на пустую страницу."""
    response = admin_upload(
        admin_client, first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0)
    )

    assert response.status_code == 200
    assert re.search(r"период.*пересекается", response.content.decode(), re.IGNORECASE)
    assert FloorPlan.objects.count() == 1


def test_the_history_of_plans_does_not_write_the_validity_of_the_spaces_themselves(
    first_floor, superseded
):
    """`Space.valid_from` означает, когда существовало помещение, а не когда — его чертёж."""
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)), valid_from=day(0))

    assert set(Space.objects.values_list("valid_from", "valid_to")) == {(None, None)}


# Слой «тип помещения»: окраска контуров и легенда


@pytest.fixture
def coloured_floor(first_floor, make_space):
    """Этаж, на котором есть все три типа помещений и то, что ни к одному не относится.

    «каб101вход» сдаётся, «Коридор» — МОП, ИТП не сдаётся и общим не является,
    а лестничная клетка — не тип помещения вовсе.
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
    """Экран со слоем отрисовывается: ошибка правила или разметки обнаруживается здесь."""
    client.force_login(member)

    response = client.get(floor_url(coloured_floor))

    assert response.status_code == 200


def test_each_of_the_three_types_is_painted_its_own_way(coloured):
    """Сдаваемое, общее и техническое видно, не читая ни одной подписи.

    Сверяется, чем залит каждый контур, а не какого он цвета: цвет — дело палитры,
    и назови его тест, он сломался бы на первой же смене темы.
    """
    assert painted_on(coloured) == {
        "man-f1-a": "leasable",
        "man-f1-c": "common",
        "man-f1-b": "technical",
    }


def test_a_space_that_is_neither_leased_nor_common_reads_as_technical(
    client, member, first_floor
):
    """Техническое — это отсутствие обоих признаков, в том числе непроставленных.

    ИТП, венткамера и электрощитовая находятся именно так. Непроставленный признак
    означает «нет»: четвёртый цвет для «неизвестно» рассказывал бы о полноте данных,
    а не о здании.
    """
    Space.objects.filter(code="man-f1-b").update(is_leasable=None, is_common=None)
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)))

    page = floor_screen(client, member, first_floor)

    assert painted_on(page) == {"man-f1-b": "technical"}


def test_a_space_marked_both_leasable_and_common_is_drawn_as_leasable(
    client, member, first_floor
):
    """Признаки противоречат друг другу; сдаваемое помещение не является общим."""
    Space.objects.filter(code="man-f1-a").update(is_leasable=True, is_common=True)
    make_plan(first_floor, plan_svg(("man-f1-a", ENTRANCE_PATH)))

    page = floor_screen(client, member, first_floor)

    assert painted_on(page) == {"man-f1-a": "leasable"}


@pytest.mark.parametrize("type", ["void", "shaft", "stairwell"])
def test_a_space_outside_the_three_types_is_outlined_without_a_fill(
    client, member, first_floor, make_space, type
):
    """Проём, шахта и лестничная клетка нарисованы, чтобы на чертеже не было провалов.

    Залить их одним из трёх цветов значило бы назвать их типом помещения, которым
    они не являются, поэтому слой не даёт им ничего: контур на плане есть, а заливки
    у него нет. Отсутствие `data-paint` — это и есть «не залит» на проводе; чем
    рисуется незалитый контур, знает таблица стилей.
    """
    make_space(first_floor, "man-f1-x", "Не тип помещения", type=type)
    make_plan(first_floor, plan_svg(("man-f1-x", ENTRANCE_PATH)))

    tag = contours_on(floor_screen(client, member, first_floor))["man-f1-x"]

    assert tag["d"] == ENTRANCE_PATH
    assert "data-paint" not in tag


def test_the_screen_shows_a_legend_for_the_colouring(coloured):
    """Цвет без легенды приходится угадывать, а угаданное читается как факт."""
    assert set(legend_on(coloured)) == {"leasable", "common", "technical"}
    assert "Арендопригодные" in coloured
    assert "МОП" in coloured
    assert "Технические" in coloured


def test_a_space_outside_the_three_types_gets_no_legend_entry(coloured):
    """Лестничная клетка на чертеже есть, но объяснять в легенде нечего: она не залита."""
    assert "man-f1-s" in contours_on(coloured)
    assert len(legend_on(coloured)) == 3


def test_the_legend_explains_the_colours_of_this_floor_and_no_others(
    client, member, first_floor
):
    """Запись о цвете, которого на чертеже нет, — это подпись к пустому месту."""
    make_plan(first_floor, plan_svg(("man-f1-b", ITP_PATH)))

    page = floor_screen(client, member, first_floor)

    assert set(legend_on(page)) == {"technical"}


def test_hovering_a_contour_says_what_its_colour_means(coloured):
    """Слой отвечает и по одному помещению: незачем сверять цвет с легендой глазами.

    Контур вне слоя подписан одним именем: заливки у него нет, и объяснять нечего.
    """
    hovered = {code: tag["title-text"] for code, tag in contours_on(coloured).items()}

    assert "арендопригодное" in hovered["man-f1-a"]
    assert "общего пользования" in hovered["man-f1-c"]
    assert "техническое" in hovered["man-f1-b"]
    assert hovered["man-f1-s"] == "ЛК-1"


# Слой выбирается адресом экрана


#: Адреса, на которых экран показывает слой по умолчанию: слой не назван, назван
#: тип помещения, имя стёрто до пустого и написано с опечаткой. Последние два — не
#: выдумка теста: адрес пересылают и правят руками, и правка приходит на экран так
#: же, как имя.
DEFAULT_LAYER_ADDRESSES = [
    {},
    {"layer": "space-type"},
    {"layer": ""},
    {"layer": "space_type"},
]


@pytest.mark.parametrize("address", DEFAULT_LAYER_ADDRESSES)
def test_the_floor_screen_opens_on_space_type_unless_the_address_names_another_layer(
    client, member, coloured_floor, address
):
    """Ни один адрес не роняет экран, и все три показывают один и тот же слой.

    Слой по умолчанию — тип помещения: он считается по данным, заведённым на всех
    помещениях, и открывшийся экран говорит о здании, а не о полноте данных.
    """
    client.force_login(member)

    response = client.get(floor_url(coloured_floor), address)
    page = response.content.decode()

    assert response.status_code == 200
    assert painted_on(page) == {
        "man-f1-a": "leasable",
        "man-f1-c": "common",
        "man-f1-b": "technical",
    }
    assert list(legend_on(page)) == ["leasable", "common", "technical"]
    assert "Слой: тип помещения" in stated(page)


def test_a_registered_layer_is_reached_by_the_name_it_is_registered_under(
    client, member, coloured_floor, monkeypatch
):
    """Второй слой — строка в реестре: экрану для него не нужно ничего, кроме имени.

    Слой здесь заведён поддельный, потому что проверяется не правило окраски, а то,
    что правило экрану неизвестно: он берёт слой по имени из адреса и рисует то,
    что слой дал. Собирается слой из адреса, которым назван, — тем и берёт своё
    следующий слой, которому мало одних контуров.
    """
    everything = plan_layer.Paint(
        key="everything", label="Всё разом", note="контур", colour="var(--plan-common)"
    )

    class EverythingLayer:
        def apply(self, contours):
            return plan_layer.Painting(
                title="Всё разом",
                contours=tuple(
                    plan_layer.PaintedContour(
                        space=contour.space, path_d=contour.path_d, paint=everything
                    )
                    for contour in contours
                ),
                legend=(everything,),
            )

    monkeypatch.setitem(plan_layer.LAYERS, "everything", lambda address: EverythingLayer())

    page = floor_screen(client, member, coloured_floor, layer="everything")

    assert set(painted_on(page).values()) == {"everything"}
    assert list(legend_on(page)) == ["everything"]
    assert "Слой: всё разом" in stated(page)
