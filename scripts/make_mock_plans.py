"""Мок-планы этажей Manhattan: SVG с `id`, равными `Space.code`, и таблица контуров.

Настоящих чертежей у нас пока нет, а модель, разбор и отрисовка проверяются только
на файле. Скрипт строит правдоподобный чертёж по тем же данным, что и база
(`scripts/populate_data/space.csv`): коридор посередине, помещения двумя рядами по
сторонам от него, ширина — по записанной площади. Кто рисуется, решает занимаемая
площадь: уборная, которая лишь содержит свои кабины, контура не имеет, а
объединяющий «каб101вход», у которого есть своя часть этажа, — имеет. Контуры не
пересекаются: вложенные помещения делят место родителя, а не ложатся поверх него.

    uv run python manage.py runscript make_mock_plans
    uv run python manage.py runscript make_mock_plans --script-args <каталог>

По умолчанию складывает `man-fN.svg` и `contours.csv` в `scripts/mock_plans/`. Базу
скрипт не трогает: он читает те же посевные данные и пишет файлы, а планы заводятся
из них в админке.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

SEED = Path(__file__).parent / "populate_data" / "space.csv"
OUT = Path(__file__).parent / "mock_plans"

#: Площадь помещения, которой в данных нет: чем-то делить место всё равно надо.
DEFAULT_AREA = 15.0
#: Уборная только содержит свои кабины и своего места на этаже не занимает.
CONTAINERS = ("-rr-f", "-rr-m")

MARGIN = 20
#: Полоса под названием этажа: подпись стоит над чертежом, а не на наружной стене.
HEADER = 34
CORRIDOR = 60
GAP = 6


def load_floors():
    """Этажи Manhattan и то, что под ними, — деревом, как в базе."""
    rows = list(csv.DictReader(SEED.open(encoding="utf-8")))
    children = defaultdict(list)
    for row in rows:
        children[row["parent"]].append(row)
    return [(row, children) for row in rows if row["type"] == "floor"]


def area_of(space):
    try:
        return float(space["area_m2"])
    except (TypeError, ValueError):
        return DEFAULT_AREA


def weight_of(space):
    """Место на чертеже — по корню из площади: иначе каморка в 2 м² выходит щелью.

    Настоящий чертёж и не обязан быть в масштабе — плана с объявленным масштабом у
    нас нет вовсе, — а вот прочитанным он быть обязан.
    """
    return area_of(space) ** 0.5


def is_drawn(space):
    """Помещение занимает собственную часть этажа — значит, у него есть контур."""
    return not space["code"].endswith(CONTAINERS)


def unit_of(space, children):
    """Помещение вместе с вложенными: они делят одно место на чертеже, не накладываясь."""
    family = [space, *children[space["code"]]]
    return {
        "members": [child for child in family if is_drawn(child)],
        "weight": sum(weight_of(child) for child in family),
    }


def rect(x, y, width, height):
    return f"M{x:.0f} {y:.0f} H{x + width:.0f} V{y + height:.0f} H{x:.0f} Z"


def lay_out(floor, children, width, height):
    """Коридор посередине, помещения двумя рядами: типовой офисный этаж."""
    units = [unit_of(space, children) for space in children[floor["code"]]]
    corridor = next(
        (unit for unit in units if unit["members"] and _is_corridor(unit["members"][0])), None
    )
    rest = [unit for unit in units if unit is not corridor]

    # Два ряда одной высоты и коридор между ними делят всё, что остаётся между
    # заголовком и наружной стеной: иначе нижний ряд уезжает за стену.
    row_height = (height - MARGIN - HEADER - CORRIDOR - 2 * GAP) / 2
    band_y = HEADER + row_height + GAP

    drawn = []
    if corridor:
        drawn.append((corridor["members"][0], rect(MARGIN, band_y, width - 2 * MARGIN, CORRIDOR)))

    top, bottom = _balance(rest)
    drawn += _row(top, MARGIN, HEADER, width - 2 * MARGIN, row_height)
    drawn += _row(bottom, MARGIN, band_y + CORRIDOR + GAP, width - 2 * MARGIN, row_height)
    return drawn


def _is_corridor(space):
    return space["code"].endswith("-cor") or space["name"].startswith("Лобби")


def _balance(units):
    """Тяжёлые помещения раскладываются по рядам поочерёдно, чтобы ряды вышли соразмерными."""
    top, bottom = [], []
    for unit in sorted(units, key=lambda unit: -unit["weight"]):
        (top if sum(u["weight"] for u in top) <= sum(u["weight"] for u in bottom) else bottom).append(unit)
    return top, bottom


def _row(units, x, y, width, height):
    """Помещения ряда по горизонтали; вложенные делят место родителя стопкой."""
    drawn = []
    total = sum(unit["weight"] for unit in units) or 1
    left = x
    for unit in units:
        span = (width - GAP * (len(units) - 1)) * unit["weight"] / total
        inner = sum(weight_of(member) for member in unit["members"]) or 1
        top = y
        for member in unit["members"]:
            share = (height - GAP * (len(unit["members"]) - 1)) * weight_of(member) / inner
            drawn.append((member, rect(left, top, span, share)))
            top += share + GAP
        left += span + GAP
    return drawn


def render(floor, drawn, width, height):
    """Чертёж: стены и подписи — обычные элементы, контуры — пути с `id` помещения."""
    wall = rect(MARGIN / 2, MARGIN / 2, width - MARGIN, height - MARGIN)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"'
            f' width="{width}" height="{height}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff" />',
        # Наружная стена и подпись — сам чертёж: `id` они не несут и контурами не станут.
        f'<path d="{wall}" fill="none" stroke="#4b5563" stroke-width="6" />',
        (
            f'<text x="{MARGIN}" y="24" font-family="sans-serif" font-size="14" fill="#9ca3af">'
            f'{floor["name"]} — Manhattan</text>'
        ),
    ]
    for space, path_d in drawn:
        parts.append(
            f'<path id="{space["code"]}" d="{path_d}" fill="#f9fafb" '
            'stroke="#6b7280" stroke-width="2" />'
        )
    parts.extend(_label(space, path_d) for space, path_d in drawn)
    parts.append("</svg>")
    return "\n".join(part for part in parts if part)


def _label(space, path_d):
    """Название помещения посередине его контура — вдоль той стороны, вдоль которой влезет.

    В узкое помещение подпись ставится боком, а в то, где она не помещается и боком,
    не ставится вовсе: вылезшая за стену подпись читается как чужая.
    """
    x, y, right, bottom = _corners(path_d)
    name = _escape(space["name"])
    length = len(space["name"]) * 6.6 + 10
    turned = right - x < length and bottom - y > length
    if min(right - x, bottom - y) < 14 or (right - x < length and not turned):
        return ""
    middle_x, middle_y = round((x + right) / 2), round((y + bottom) / 2 + 4)
    turn = f' transform="rotate(-90 {middle_x} {middle_y})"' if turned else ""
    return (
        f'<text x="{middle_x}" y="{middle_y}"{turn} font-family="sans-serif" font-size="11" '
        f'fill="#374151" text-anchor="middle">{name}</text>'
    )


def _corners(path_d):
    numbers = path_d.replace("M", " ").replace("H", " ").replace("V", " ").replace("Z", " ").split()
    return tuple(float(numbers[i]) for i in (0, 1, 2, 3))


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def run(*args):
    """Точка входа `runscript`, как у соседних скриптов; каталог — первым аргументом."""
    out = Path(args[0]) if args else OUT
    out.mkdir(parents=True, exist_ok=True)
    table = []
    for floor, children in load_floors():
        under = _all_under(floor, children)
        width, height = (1200, 800) if len(under) > 6 else (700, 500)
        drawn = lay_out(floor, children, width, height)
        (out / f"{floor['code']}.svg").write_text(render(floor, drawn, width, height), encoding="utf-8")
        for space, path_d in drawn:
            table.append(
                {
                    "floor_code": floor["code"],
                    "floor_name": floor["name"],
                    "space_code": space["code"],
                    "space_name": space["name"],
                    "space_type": space["type"],
                    "path_d": path_d,
                }
            )
        print(f"{floor['code']}.svg — контуров {len(drawn)} из {len(under)} помещений этажа")

    with (out / "contours.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    print(f"contours.csv — строк {len(table)}; всё в {out}")


def _all_under(floor, children):
    found = []
    queue = [floor["code"]]
    while queue:
        for child in children[queue.pop()]:
            found.append(child)
            queue.append(child["code"])
    return found


if __name__ == "__main__":
    # Django скрипту не нужен — файлы строятся из посевного CSV, — поэтому он
    # запускается и напрямую, без `runscript`.
    run(*sys.argv[1:])
