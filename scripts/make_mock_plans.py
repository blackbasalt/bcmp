"""Mock plans of Manhattan's floors: SVGs whose `id`s equal `Space.code`, plus a table of
contours.

We have no real drawings yet, while the model, the parse and the rendering can only be
checked against a file. The script builds a plausible drawing from the same data as the
database (`scripts/populate_data/space.csv`): a corridor down the middle, spaces in two
rows on either side of it, widths taken from the recorded area. What gets drawn is decided
by the floor area a space occupies: a lavatory, which merely contains its own cubicles, has
no contour, whereas the grouping «каб101вход», which has a part of the floor of its own,
does. The contours do not overlap: nested spaces share their parent's place rather than
lying on top of it.

    uv run python manage.py runscript make_mock_plans
    uv run python manage.py runscript make_mock_plans --script-args <directory>

By default it puts `man-fN.svg` and `contours.csv` into `scripts/mock_plans/`. The script
does not touch the database: it reads the same seed data and writes files, and the plans
are created from them in the admin.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

SEED = Path(__file__).parent / "populate_data" / "space.csv"
OUT = Path(__file__).parent / "mock_plans"

#: A space's area when the data has none: the place has to be divided by something anyway.
DEFAULT_AREA = 15.0
#: A lavatory merely contains its own cubicles and occupies no place of its own on the floor.
CONTAINERS = ("-rr-f", "-rr-m")

MARGIN = 20
#: The band under the floor's name: the caption stands above the drawing, not on the outer wall.
HEADER = 34
CORRIDOR = 60
GAP = 6


def load_floors():
    """Manhattan's floors and what lies under them — as a tree, the way it is in the database."""
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
    """Place on the drawing goes by the square root of the area: otherwise a 2 m² cubbyhole
    comes out as a slit.

    A real drawing is not obliged to be to scale — we have no plan with a declared scale at
    all — but it is obliged to be legible.
    """
    return area_of(space) ** 0.5


def is_drawn(space):
    """The space occupies a part of the floor of its own — so it has a contour."""
    return not space["code"].endswith(CONTAINERS)


def unit_of(space, children):
    """A space together with those nested in it: they share one place on the drawing without
    overlapping."""
    family = [space, *children[space["code"]]]
    return {
        "members": [child for child in family if is_drawn(child)],
        "weight": sum(weight_of(child) for child in family),
    }


def rect(x, y, width, height):
    return f"M{x:.0f} {y:.0f} H{x + width:.0f} V{y + height:.0f} H{x:.0f} Z"


def lay_out(floor, children, width, height):
    """A corridor down the middle, spaces in two rows: a typical office floor."""
    units = [unit_of(space, children) for space in children[floor["code"]]]
    corridor = next(
        (unit for unit in units if unit["members"] and _is_corridor(unit["members"][0])), None
    )
    rest = [unit for unit in units if unit is not corridor]

    # Two rows of the same height and the corridor between them share everything left
    # between the heading and the outer wall: otherwise the bottom row runs past the wall.
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
    """Heavy spaces are dealt out to the rows in turn, so that the rows come out comparable."""
    top, bottom = [], []
    for unit in sorted(units, key=lambda unit: -unit["weight"]):
        (top if sum(u["weight"] for u in top) <= sum(u["weight"] for u in bottom) else bottom).append(unit)
    return top, bottom


def _row(units, x, y, width, height):
    """The spaces of a row go horizontally; nested ones share the parent's place in a stack."""
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
    """The drawing: walls and captions are ordinary elements, contours are paths carrying a
    space's `id`."""
    wall = rect(MARGIN / 2, MARGIN / 2, width - MARGIN, height - MARGIN)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"'
            f' width="{width}" height="{height}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff" />',
        # The outer wall and the caption are the drawing itself: they carry no `id` and will
        # not become contours.
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
    """The space's name in the middle of its contour — along whichever side it fits.

    In a narrow space the caption is set sideways, and in one where it does not fit even
    sideways it is not set at all: a caption sticking out past a wall reads as belonging to
    someone else.
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
    """The `runscript` entry point, as in the neighbouring scripts; the directory comes as
    the first argument."""
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
    # The script does not need Django — the files are built from the seed CSV — so it can
    # also be run directly, without `runscript`.
    run(*sys.argv[1:])
