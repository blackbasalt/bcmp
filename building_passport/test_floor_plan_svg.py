"""Разбор SVG поэтажного плана в контуры — единственный шов ниже HTTP.

Он заведён потому, что интересные случаи здесь — испорченные и враждебные файлы:
без `viewBox`, с `id` несуществующего помещения, с повторяющимся `id`, вовсе без
путей. Выразить их загрузкой файла через форму можно, но тогда набор тестов экрана
превращается в фабрику файловых заглушек, а причина отказа читается через сообщение
на странице вместо самой причины.

Проверяется наблюдаемое разбором: что стало контуром, что осталось непривязанным и
на чём файл отвергается. Сама отрисовка контуров проверяется через экран этажа.
"""

import pytest

from building_passport.floor_plan_svg import PlanUnreadable, read_plan

# Настоящий план — это в основном чертёж: стены, штриховки, подписи. Контуром
# становится только путь с `id`, поэтому в образцах есть и то, и другое.
WALL = '<path d="M0 0 L100 0" />'


def svg(body, view_box='0 0 100 100', **root):
    attrs = "".join(f' {name}="{value}"' for name, value in root.items())
    box = f' viewBox="{view_box}"' if view_box is not None else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg"{box}{attrs}>{body}</svg>'


def contour(code, d="M0 0 L10 0 L10 10 Z"):
    return f'<path id="{code}" d="{d}" />'


# Что становится контуром


def test_a_valid_file_yields_one_contour_per_matched_path():
    """Разобранный план — это помещения, нарисованные; лишнего в нём нет."""
    reading = read_plan(svg(contour("man-f1-a") + contour("man-f1-b")), ["man-f1-a", "man-f1-b"])

    assert {c.code for c in reading.contours} == {"man-f1-a", "man-f1-b"}


def test_the_geometry_of_a_contour_is_kept_as_it_was_drawn():
    """Контур — геометрия из файла, а не её пересчёт: чертёж авторится снаружи."""
    reading = read_plan(svg(contour("man-f1-a", d="M1 2 L3 4 Z")), ["man-f1-a"])

    assert reading.contours[0].path_d == "M1 2 L3 4 Z"


def test_the_drawing_itself_does_not_become_contours():
    """Стены и штриховки `id` не носят — контур ставит помещение, а не линия."""
    reading = read_plan(svg(WALL + contour("man-f1-a")), ["man-f1-a"])

    assert len(reading.contours) == 1
    assert reading.unmatched == ()


def test_a_contour_drawn_inside_a_group_is_found():
    """Редакторы SVG раскладывают чертёж по слоям; вложенность — их дело, не наше."""
    reading = read_plan(svg(f"<g><g>{contour('man-f1-a')}</g></g>"), ["man-f1-a"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_a_file_without_a_namespace_is_read_all_the_same():
    """Экспорт без `xmlns` — обычное дело, и планом файл от этого быть не перестаёт."""
    body = contour("man-f1-a")

    reading = read_plan(f'<svg viewBox="0 0 100 100">{body}</svg>', ["man-f1-a"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_bytes_are_read_the_same_as_text():
    """Файл приезжает байтами: разбор не должен зависеть от того, кто их декодировал."""
    reading = read_plan(svg(contour("man-f1-a")).encode(), ["man-f1-a"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


# Неполные данные — план грузится против них, а не после них


def test_a_path_matching_no_space_is_reported_rather_than_dropped():
    """Опечатка в `id` должна быть видна: молча потерянный путь — потерянное помещение."""
    reading = read_plan(svg(contour("man-f1-a") + contour("man-f1-zz")), ["man-f1-a"])

    assert reading.unmatched == ("man-f1-zz",)
    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_a_space_with_no_path_yields_no_contour_of_its_own():
    """Помещения без пути на плане нет — выдуманной формы ему не рисуют."""
    reading = read_plan(svg(contour("man-f1-a")), ["man-f1-a", "man-f1-b"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_a_file_with_no_paths_at_all_is_a_plan_with_no_contours():
    """План — инструмент поиска незаведённого, поэтому грузится и против пустого дерева."""
    reading = read_plan(svg(""), ["man-f1-a"])

    assert reading.contours == ()
    assert reading.unmatched == ()


def test_a_path_carrying_an_id_but_no_geometry_is_not_a_contour():
    """Контур — это форма; путь без `d` формы не задаёт и границей помещения не станет."""
    reading = read_plan(svg('<path id="man-f1-a" />'), ["man-f1-a"])

    assert reading.contours == ()


# Отказы: файл, который планом не является


def test_a_file_without_a_viewbox_is_rejected():
    """Без `viewBox` контуры не с чем совместить: система координат объявляется им."""
    with pytest.raises(PlanUnreadable, match="viewBox"):
        read_plan(svg(contour("man-f1-a"), view_box=None), ["man-f1-a"])


def test_a_viewbox_that_is_not_four_numbers_is_rejected():
    """Испорченный `viewBox` хуже отсутствующего: он выглядит рабочим."""
    with pytest.raises(PlanUnreadable, match="viewBox"):
        read_plan(svg(contour("man-f1-a"), view_box="0 0 100"), ["man-f1-a"])


def test_a_viewbox_with_no_extent_is_rejected():
    """План нулевой ширины не нарисовать, а деление на его размер — ошибка на экране."""
    with pytest.raises(PlanUnreadable, match="viewBox"):
        read_plan(svg(contour("man-f1-a"), view_box="0 0 0 100"), ["man-f1-a"])


def test_a_file_that_is_not_xml_is_rejected():
    """Загрузили не тот файл — это причина отказа, а не пустой план на экране."""
    with pytest.raises(PlanUnreadable):
        read_plan(b"%PDF-1.7 \n1 0 obj", ["man-f1-a"])


def test_an_xml_file_that_is_not_svg_is_rejected():
    """Разобрать разобралось, но планом не является."""
    with pytest.raises(PlanUnreadable, match="SVG"):
        read_plan("<drawing><path id='man-f1-a' d='M0 0'/></drawing>", ["man-f1-a"])


def test_two_paths_outlining_one_space_are_rejected():
    """У помещения один контур на плане: две формы — это вопрос, какая из них верна."""
    with pytest.raises(PlanUnreadable, match="man-f1-a"):
        read_plan(svg(contour("man-f1-a") + contour("man-f1-a", d="M5 5 L6 6 Z")), ["man-f1-a"])


def test_the_same_id_on_two_paths_of_no_space_does_not_reject_the_file():
    """Повторённая опечатка — всё та же опечатка: план грузится и показывает её.

    Отказ здесь означал бы, что план нельзя загрузить, пока дерево помещений не
    безупречно, — а он для того и нужен, чтобы неполноту в нём стало видно.
    """
    reading = read_plan(svg(contour("man-f1-zz") + contour("man-f1-zz")), ["man-f1-a"])

    assert reading.unmatched == ("man-f1-zz", "man-f1-zz")


# Система координат плана


def test_the_viewbox_is_carried_out_of_the_file():
    """Тот же `viewBox` получает наложенный слой контуров — иначе они разъедутся."""
    reading = read_plan(svg(contour("man-f1-a"), view_box="-10 -20 800 600"), ["man-f1-a"])

    assert reading.view_box == "-10 -20 800 600"


def test_the_viewbox_is_normalised_to_the_numbers_it_carries():
    """В файле разделителем бывает запятая и перевод строки; на экран едет одна запись."""
    reading = read_plan(svg("", view_box="0,0\n800, 600"), [])

    assert reading.view_box == "0 0 800 600"
