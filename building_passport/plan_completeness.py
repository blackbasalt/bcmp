"""Plan completeness: how many spaces of a floor are drawn and what is left over on the drawing.

The plan is the project's sharpest tool for finding what has not been recorded, and its
sharpness lies in counting not what is drawn but what is not: "нанесено 47 из 82
помещений" names at once both what is missing from the drawing and what is missing from
the tree. The spatial equivalent of the building passport's "— нет данных".

The count is in spaces, not in square metres, and that is a decision rather than an
omission. Metres need a scale, which a plan does not declare, and not every space has an
area recorded: a figure in m² would look precise without being so. No scale field is
added for its sake.

The denominator is every space under the floor, with no exceptions: a space that merely
groups the ones nested inside it has no contour and still counts as undrawn. That is not
a hole in the data, but it cannot be subtracted here either — the rule "this one needs
no contour" would have to come from somewhere, and there is nowhere to take it from.

The uncovered remainder of the floor is not closed off with a contour: 561 m² of
`man-f1` against 170 m² of its modelled children is a finding, not a hole in the
picture, and a synthetic "other" would close it with an invented shape. So there is
nothing here that would be drawn: only numbers and a list of paths that found no space.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Contour, Space


@dataclass(frozen=True)
class Completeness:
    """What is drawn on the plan, what is left without a contour and what dangles on the drawing.

    Drawn and undrawn are held as space keys rather than as counts: the tree on the left
    marks its nodes from the same sets, and there is no need to match contours against
    the tree a second time to obtain them again.
    """

    drawn: frozenset[uuid.UUID]
    undrawn: frozenset[uuid.UUID]
    #: The `id`s of paths in the drawing that found no space on the floor — typos stay visible.
    unmatched: tuple[str, ...]

    @property
    def drawn_count(self) -> int:
        """How many spaces of the floor are drawn — the numerator of the count."""
        return len(self.drawn)

    @property
    def space_count(self) -> int:
        """How many spaces exist on the floor — the denominator of the count."""
        return len(self.drawn) + len(self.undrawn)


def completeness_of(
    spaces: Iterable["Space"],
    contours: Iterable["Contour"],
    unmatched: Iterable[str],
) -> Completeness:
    """Match the spaces of a floor against the contours of the plan in force.

    The spaces are the same ones that go into the tree, and the contours the same ones
    that go onto the drawing: otherwise the screen would count one thing and show
    another. For a floor with no plan in force both are empty — nothing is drawn, and
    nothing is counted.

    Repeats among the unmatched paths collapse: the parse hands back one record per
    path, but what is named on screen is the typo, and naming it twice reads as a glitch
    of the screen rather than as a second path with the same `id`.
    """
    outlined = {contour.space_id for contour in contours}
    on_the_floor = {space.pk for space in spaces}
    return Completeness(
        drawn=frozenset(on_the_floor & outlined),
        undrawn=frozenset(on_the_floor - outlined),
        unmatched=tuple(dict.fromkeys(unmatched)),
    )
