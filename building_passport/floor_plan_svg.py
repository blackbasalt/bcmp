"""Parsing the SVG of a floor plan: a drawing becomes the contours of its spaces.

The drawing is authored in an external editor, and the `id` of a path equals the
`Space.code` of the space it outlines. Everything else in the file is the drawing
itself: walls, hatching, captions. The parse separates one from the other and matches
the paths against the codes of the floor's spaces.

The parse is tolerant of incompleteness and strict about the coordinate system. A path
with an `id` that found no space, and a space missing from the drawing, are states of
the data: the plan exists precisely so that such things become visible, which means it
must load against an incomplete tree of spaces. A file without a `viewBox`, on the
other hand, is not a plan: there is nothing to align the contours with, and a silent
default here would mean rendering that has drifted apart.

The numbers of the `viewBox` are normalised while parsing: in a file the separator may
be a comma or a newline, whereas one single form must reach the screen — the same one
the contours on top of the drawing are drawn under.

Parsing goes through `xml.etree`: it loads no external entities and does not expand
internal ones — on an undefined entity it stops with an error, which becomes a
rejection with a reason here.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from xml.etree import ElementTree


class PlanUnreadable(ValueError):
    """The file is not a floor plan. The message is the reason, for whoever uploaded it."""


@dataclass(frozen=True)
class ReadContour:
    """A space boundary taken from the drawing: the space's code and the path outlining it."""

    code: str
    path_d: str


@dataclass(frozen=True)
class PlanReading:
    """A parsed plan: its coordinate system, its contours and its unmatched paths."""

    view_box: str
    contours: tuple[ReadContour, ...]
    #: The `id`s of paths that found no space on the floor — typos stay visible instead
    #: of being lost.
    unmatched: tuple[str, ...]


#: The separators between the numbers of a `viewBox` — spaces and commas in any mix.
SEPARATORS = re.compile(r"[,\s]+")


def read_plan(source: bytes | str, codes: Iterable[str]) -> PlanReading:
    """Read the drawing of a floor, matching its paths against the codes of its spaces.

    A file is rejected if it does not parse as XML, if its root is not `<svg>`, if it
    has no usable `viewBox`, or if two paths outline the same space: a space has one
    contour on a plan, and two shapes raise the question of which one is right. A
    repeated `id` with no space behind it does not kill the file: that is a typo, and
    typos are something a plan survives and shows.
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
    # Text is encoded back into bytes: otherwise the parser rejects an encoding
    # declaration inside the file itself, and exports do carry one.
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
    """Paths with an `id` and a shape, in file order. Editors nest them in `<g>` groups."""
    drawn: list[tuple[str, str]] = []
    for element in root.iter():
        if _name(element) != "path":
            continue
        code, path_d = element.get("id"), element.get("d")
        # A path with no `id` is the drawing itself, and a path with no shape will
        # never become the boundary of a space.
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
    """The tag name without its namespace: exports carry `xmlns` sometimes and sometimes not."""
    return str(element.tag).rsplit("}", 1)[-1]
