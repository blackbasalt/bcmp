"""Занятость помещения — «действующая на день», «сдано X из Y» и «свободно», в одном месте.

Two screens ask about occupancy and must not each carry their own copy of it. The карточка
помещения holds one `Space` and wants the аренды standing on it today together with the two
numbers; the полка помещений holds a queryset and wants a condition to narrow it by. So the
rule is given out in both shapes here — the pattern `space_kind` established for вид and
`plan_completeness` for полнота плана. Two copies would be two answers to one question, and
the day they disagreed nobody would know which screen was lying.

Three readings are settled here and nowhere else:

- **Действующая на день** is `valid_from <= день` and («по» is empty or `valid_to >= день`):
  both ends included, an empty end reading «по сей день» — the same arithmetic the
  действующий план already uses (ADR 0004).
- **Сдано X из Y** counts the арендуемые площади of the действующие аренды against the
  площадь of the помещение itself, and counts nothing else. An аренда with no арендуемая
  площадь is left out of the sum and counted separately: a missing number of metres read as
  zero metres would quietly shrink X. The sum may exceed Y — арендуемая площадь carries a
  share of the МОП by a coefficient (ADR 0017) — and that is printed as it stands.
- **Свободно** is an **арендопригодное** помещение with not a single действующая аренда —
  both halves, as the словарь defines it. A МОП standing empty is not свободно: it was
  never on offer, and calling it that reports a лобби as a leasing opportunity. Свободные
  are counted in помещениях, never in metres (ADR 0019).

Nothing here reads the tree: сдача входного тамбура кабинеты за ним не сдаёт, and сдача
уборной кабины в ней — сдаёт, and nothing in a row tells the two apart (ADR 0019). Every
помещение counts its own аренды and only its own.

The module has no tests of its own, exactly as `space_kind` and `plan_completeness` have
none: it is read by both screens, and both screens check it. A test of its own would be a
second account of one rule, and the two would eventually disagree.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Q

from building_passport import space_kind

if TYPE_CHECKING:
    from .models import Lease


def in_force_on(day) -> Q:
    """The condition selecting аренды standing on this day — the rule, said to a queryset.

    The empty «по» is spelled out rather than negated: `~Q(valid_to__lt=day)` becomes
    `NOT (valid_to < day)` in SQL, and NULL compared to anything is NULL, so a бессрочная
    аренда — the ordinary case — would fall out of both sides of the question at once.
    """
    return Q(valid_from__lte=day) & (Q(valid_to__isnull=True) | Q(valid_to__gte=day))


def ended_before(day) -> Q:
    """Аренды that are over: «по» is filled in and it is behind us."""
    return Q(valid_to__lt=day)


def begins_after(day) -> Q:
    """Аренды that have not started: a продление is entered while the current срок runs."""
    return Q(valid_from__gt=day)


@dataclass(frozen=True)
class Occupancy:
    """Who sits in one помещение today, who sat there before, and who is yet to move in.

    The аренды are held as they will be read — in the model's own order, newest срок first
    — because the screen names each of them; the numbers are worked out from the same rows
    rather than by a second query, so what is listed and what is counted cannot differ.
    """

    #: The площадь of the помещение itself, as recorded — the Y of «сдано X из Y».
    area_m2: Decimal | None
    #: Whether the помещение may be let at all — the half of «свободно» that is about the
    #: помещение rather than about its аренды. Read by the same rule the план colours
    #: contours by, so that «арендопригодное» means one thing on both screens.
    is_leasable: bool
    in_force: tuple["Lease", ...]
    past: tuple["Lease", ...]
    future: tuple["Lease", ...]

    @property
    def let_m2(self) -> Decimal:
        """The X: the арендуемые площади of the действующие аренды, added up."""
        let = (lease.area_m2 for lease in self.in_force if lease.area_m2 is not None)
        return sum(let, Decimal(0))

    @property
    def leases_without_area(self) -> int:
        """How many действующие аренды the sum could not count — stated, not hidden."""
        return sum(1 for lease in self.in_force if lease.area_m2 is None)

    @property
    def is_free(self) -> bool:
        """Свободно: an арендопригодное помещение with not a single действующая аренда.

        A МОП with nobody in it is not свободно — it is a лобби. The word answers «что
        стоит пустым», and a помещение that was never on offer is not an answer to it.
        """
        return self.is_leasable and not self.in_force

    @property
    def behind(self) -> tuple["Lease", ...]:
        """Аренды за складкой: those that are over and those that have not begun yet.

        One group and not two on screen: what a reader looks for behind a складка is an
        аренда that is not today's, and which side of today it lies on is written in its
        own срок. The складка names both when both are there, so nothing there is called
        «прошлая» that is not.
        """
        return self.past + self.future

    @property
    def has_any(self) -> bool:
        """Whether BCMP knows of any аренда here at all, in force or not."""
        return bool(self.in_force or self.past or self.future)


def occupancy_of(space, day) -> Occupancy:
    """The занятость of one помещение on one day — `in_force_on`, asked about a `Space`.

    The three groups are selected by the conditions above rather than sorted out in Python:
    the same rule that narrows the полка decides what the карточка lists, and there is no
    second date comparison to drift from the first.
    """
    leases = space.leases.select_related("tenant")
    return Occupancy(
        area_m2=space.area_m2,
        is_leasable=space_kind.kind_of(space) == space_kind.LEASABLE,
        in_force=tuple(leases.filter(in_force_on(day))),
        past=tuple(leases.filter(ended_before(day))),
        future=tuple(leases.filter(begins_after(day))),
    )
