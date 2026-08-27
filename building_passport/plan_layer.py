"""A layer: the rule by which the contours of a floor plan are coloured.

A layer gives every contour three things at once — a fill colour, a legend entry and a
tooltip line — and it is computed on the server. Otherwise the rule drifts apart: the
browser would know which colour to paint with, while the legend next to the plan would
explain the colours from a list of its own, and nothing would stop the two diverging.

One layer is defined here — the вид of the помещение. Tenant arrears, lease terms and
faults in the engineering systems arrive later as new layers on the same plan, not as
new screens: the screen draws what the layer handed it (`Painting`) and knows nothing
about the rule itself. A plan shows one layer at a time.

A colour is named as a variable, not as a value: the project's palette lives as a
single list in the theme (`assets/css/app.css`), and the layer picks from it instead of
defining colours of its own alongside. The fill stays semi-transparent — behind it is
the drawing, which must remain readable through the colouring.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dictionary.models import DictSpaceType

from . import space_kind

if TYPE_CHECKING:
    from .models import Contour, Space


@dataclass(frozen=True)
class Paint:
    """What the layer fills a contour with: a colour, a legend entry and a tooltip line.

    The legend caption and the tooltip line differ: the legend names all the spaces of
    one colour at once ("Арендопригодные"), while the tooltip names the single one the
    pointer is over.
    """

    #: The screen's contract: this key marks both the contour on the plan and the
    #: legend entry.
    key: str
    label: str
    note: str
    colour: str


LEASABLE = Paint(
    key=space_kind.LEASABLE,
    label="Арендопригодные",
    note="арендопригодное помещение",
    colour="var(--plan-leasable)",
)
COMMON = Paint(
    key=space_kind.COMMON,
    label="МОП",
    note="место общего пользования",
    colour="var(--plan-common)",
)
TECHNICAL = Paint(
    key=space_kind.TECHNICAL,
    label="Технические",
    note="техническое помещение",
    colour="var(--plan-technical)",
)

#: What is not a type of space: stairwells, lift shafts and double-height voids. They
#: have to be drawn — otherwise the drawing is left with unexplained gaps — but there
#: is nothing to fill them with: any of the three colours would call them something
#: they are not. The layer gives them nothing: no fill, no legend entry, no tooltip.
OUTSIDE_THE_TYPES = frozenset({DictSpaceType.VOID, DictSpaceType.SHAFT, DictSpaceType.STAIRWELL})


@dataclass(frozen=True)
class PaintedContour:
    """A contour coloured by the layer — what gets drawn on top of the drawing."""

    space: "Space"
    path_d: str
    #: What it is filled with; `None` — a contour outside the layer, an outline with no fill.
    paint: Paint | None


@dataclass(frozen=True)
class Painting:
    """The layer applied to a plan's contours: the coloured contours and their legend.

    Everything the screen needs to know about the layer. The next layer will hand back
    the same record, and the markup will need nothing new for it.
    """

    title: str
    contours: tuple[PaintedContour, ...]
    legend: tuple[Paint, ...]


#: Which вид is drawn with which colour. The keys are `space_kind`'s, so a colour cannot
#: quietly come to mean something the rule does not say.
COLOUR_OF = {
    space_kind.LEASABLE: LEASABLE,
    space_kind.COMMON: COMMON,
    space_kind.TECHNICAL: TECHNICAL,
}


class SpaceKindLayer:
    """The "вид помещения" layer: a space is leasable, common, or serves the building.

    The only layer computed from data recorded on every space — with it an employee of
    the management company judges the leasable area of a floor, and an engineer finds
    the heating substation, the air handling room and the switchboard room without
    reading a single caption.

    Which вид a space is, is not decided here: that rule is `space_kind`'s, and the полка
    помещений narrows by the same one. What is decided here is what the план does with it
    — the colour, the legend caption and the order of the legend, which belong to the
    drawing and are of no use to a table.

    It is called вид and not тип, because тип is what tells a помещение from an этаж and a
    здание, while вид divides помещения among themselves. Two axes shared one word until
    the полка had to put three of them side by side.
    """

    title = "Вид помещения"
    #: The order of the legend. It is also the order of the виды — the legend must not
    #: be rearranged by whatever happened to be drawn first in the file.
    palette = tuple(COLOUR_OF[kind] for kind in space_kind.KINDS)

    def paint_of(self, space: "Space") -> Paint | None:
        """What a space is filled with, or `None` if it falls outside the layer.

        Outside the layer are the things that are not помещения at all — a stairwell, a
        shaft, a double-height void. They have to be drawn, or the drawing is left with
        unexplained gaps, but there is no вид to give them: `space_kind` answers about a
        помещение, and these are not one.
        """
        if space.type in OUTSIDE_THE_TYPES:
            return None
        return COLOUR_OF[space_kind.kind_of(space)]

    def apply(self, contours: Iterable["Contour"]) -> Painting:
        """Apply the layer to the contours of a plan.

        The legend is assembled from what is actually drawn on this floor: an entry for
        a colour absent from the drawing would be a caption to an empty space.
        """
        painted = tuple(
            PaintedContour(
                space=contour.space, path_d=contour.path_d, paint=self.paint_of(contour.space)
            )
            for contour in contours
        )
        drawn = {contour.paint for contour in painted}
        return Painting(
            title=self.title,
            contours=painted,
            legend=tuple(paint for paint in self.palette if paint in drawn),
        )


SPACE_KIND = SpaceKindLayer()
