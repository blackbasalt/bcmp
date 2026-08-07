"""Разбор SVG поэтажного плана: чертёж превращается в контуры помещений.

Чертёж авторится во внешнем редакторе, и `id` пути равен `Space.code` помещения,
которое он обводит. Всё остальное в файле — сам чертёж: стены, штриховки, подписи.
Разбор отделяет одно от другого и сводит пути с кодами помещений этажа.

Разбор терпим к неполноте и строг к системе координат. Путь с `id`, которому не
нашлось помещения, и помещение, которого нет на чертеже, — это состояние данных:
план и заводится ради того, чтобы такое стало видно, значит он обязан грузиться
против неполного дерева помещений. А файл без `viewBox` — не план: контуры не с чем
совместить, и молчаливое умолчание здесь означало бы разъехавшуюся отрисовку.

Числа `viewBox` нормализуются при разборе: в файле разделителем бывает и запятая,
и перевод строки, а на экран должна ехать одна запись — та же, под которой
рисуются контуры поверх чертежа.

Разбор идёт `xml.etree`: внешние сущности он не подгружает, а внутренние не
разворачивает — на неопределённой он останавливается с ошибкой, которая здесь
становится отказом с причиной.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from xml.etree import ElementTree


class PlanUnreadable(ValueError):
    """Файл не является поэтажным планом. Сообщение — причина для загрузившего."""


@dataclass(frozen=True)
class ReadContour:
    """Граница помещения, снятая с чертежа: код помещения и путь, которым он обведён."""

    code: str
    path_d: str


@dataclass(frozen=True)
class PlanReading:
    """Разобранный план: его система координат, контуры и непривязанные пути."""

    view_box: str
    contours: tuple[ReadContour, ...]
    #: `id` путей, которым не нашлось помещения на этаже, — опечатки видны, а не потеряны.
    unmatched: tuple[str, ...]


#: Разделители чисел `viewBox` — пробелы и запятые в любом сочетании.
SEPARATORS = re.compile(r"[,\s]+")


def read_plan(source: bytes | str, codes: Iterable[str]) -> PlanReading:
    """Прочитать чертёж этажа, сведя пути с кодами его помещений.

    Отвергается файл, который не разбирается как XML, чей корень не `<svg>`, у
    которого нет пригодного `viewBox` или в котором два пути обводят одно и то же
    помещение: контур у него на плане один, и две формы — это вопрос, какая верна.
    Повторяющийся `id`, за которым помещения нет, файл не рубит: это опечатка, а
    опечатки план переживает и показывает.
    """
    root = _root(source)
    view_box = _view_box(root)
    drawn = _drawn_paths(root)
    known = set(codes)
    contours = tuple(
        ReadContour(code=code, path_d=path_d) for code, path_d in drawn if code in known
    )
    _reject_repeats(contours)
    return PlanReading(
        view_box=view_box,
        contours=contours,
        unmatched=tuple(code for code, _ in drawn if code not in known),
    )


def _root(source: bytes | str) -> ElementTree.Element:
    # Текст кодируется обратно в байты: иначе объявление кодировки в самом файле
    # разбор не пропустит, а оно в экспортах встречается.
    document = source.encode() if isinstance(source, str) else source
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as error:
        raise PlanUnreadable(f"Файл не читается как SVG: {error}") from error
    if _name(root) != "svg":
        raise PlanUnreadable(f"Файл не является SVG: корневой элемент — <{_name(root)}>")
    return root


def _view_box(root: ElementTree.Element) -> str:
    declared = root.get("viewBox")
    if not declared:
        raise PlanUnreadable("У файла нет viewBox — системы координат, в которой лежат контуры")
    numbers = SEPARATORS.split(declared.strip())
    try:
        min_x, min_y, width, height = (float(number) for number in numbers)
    except ValueError as error:
        raise PlanUnreadable(f"viewBox не читается как четыре числа: «{declared}»") from error
    if width <= 0 or height <= 0:
        raise PlanUnreadable(f"viewBox не имеет размера: «{declared}»")
    return " ".join(f"{number:g}" for number in (min_x, min_y, width, height))


def _drawn_paths(root: ElementTree.Element) -> tuple[tuple[str, str], ...]:
    """Пути с `id` и формой, в порядке файла. Редакторы вкладывают их в группы `<g>`."""
    drawn: list[tuple[str, str]] = []
    for element in root.iter():
        if _name(element) != "path":
            continue
        code, path_d = element.get("id"), element.get("d")
        # Путь без `id` — сам чертёж, а путь без формы границей помещения не станет.
        if code and path_d:
            drawn.append((code, path_d))
    return tuple(drawn)


def _reject_repeats(contours: tuple[ReadContour, ...]) -> None:
    seen: set[str] = set()
    for contour in contours:
        if contour.code in seen:
            raise PlanUnreadable(f"Два пути обводят одно помещение: «{contour.code}»")
        seen.add(contour.code)


def _name(element: ElementTree.Element) -> str:
    """Имя тега без пространства имён: `xmlns` в экспортах то есть, то нет."""
    return str(element.tag).rsplit("}", 1)[-1]
