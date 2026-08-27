"""Вид помещения — арендопригодное, МОП или техническое: the rule, in one place.

Вид is not stored. It is read off two flags — is the помещение let to a tenant, is it open
to everyone — and the three answers are what a сотрудник УК actually asks a building for:
what earns, what everybody walks through, what keeps the building running.

Two screens ask it, and they must not each carry their own copy. The план colours contours
by it (`plan_layer`); the полка помещений narrows by it and prints it in a column. One of
them holds a `Space` and wants a вид; the other holds a queryset and wants a condition —
so the rule is given out in both shapes here, worked out once from the same two flags.

Colours, legend captions and the order of the legend are deliberately absent: those belong
to the план, and the вид of a помещение is the same whether or not anything is drawn.

Three readings are settled here and nowhere else:

- **Техническое is the remainder.** Neither let nor common, and that is the definition —
  not a fourth state. A помещение whose flags nobody filled in reads as техническое, which
  is why the полка offers «вид не заведён» as a condition of its own: it is a statement
  about the record rather than about the building, and it is the only way to find those
  помещения before they quietly count as технические.
- **A contradictory pair reads as арендопригодное.** What is let to a tenant is never
  common, so `is_leasable` is asked first and answers alone.
- **An unset flag means "no".** The columns are nullable, and NULL is spelled out rather
  than left to the database: `NOT (is_common = 1)` drops a NULL row on SQLite as on
  PostgreSQL, so «техническое» would lose exactly the помещения it is the remainder for.
"""

from django.db.models import Q

#: The screen's keys for the three виды. They are the same keys the план marks a contour
#: and its legend entry with, so a test reading the план and a test reading the полка speak
#: about one вид in one word.
LEASABLE = "leasable"
COMMON = "common"
TECHNICAL = "technical"

#: The three виды in the order they are read: what earns, what is shared, what serves.
#: Stated here so that the полка's list and the план's legend cannot be ordered differently
#: — a reader who moves between the two screens must not have to look for the same word in
#: a new place.
KINDS = (LEASABLE, COMMON, TECHNICAL)


#: The rule itself: which flag decides which вид, in the order the flags are asked. It is a
#: list and not two cascades because it is read twice — once of a помещение in hand, once of
#: a queryset — and two cascades in two shapes would be two places to change the order in,
#: with nothing to catch the day only one of them was changed.
#:
#: Техническое is absent on purpose: it asks no flag, because it is what is left when every
#: flag has said no. That is what "remainder" means, and writing it in would make it look
#: like a fourth question the data could answer.
DECIDED_BY = ((LEASABLE, "is_leasable"), (COMMON, "is_common"))


def kind_of(space) -> str:
    """The вид of a помещение."""
    for kind, flag in DECIDED_BY:
        if getattr(space, flag):
            return kind
    return TECHNICAL


def being(kind: str) -> Q:
    """The condition selecting помещения of one вид — `kind_of`, said to a queryset.

    The same walk down the same list, so what a row is filled with on the план and what the
    полка finds by that вид cannot disagree. Every flag asked before the wanted one has to
    have said no: that is how «арендопригодное и общее сразу» reads as арендопригодное and
    is not also counted among the МОП.
    """
    so_far = Q()
    for candidate, flag in DECIDED_BY:
        if candidate == kind:
            return so_far & _yes(flag)
        so_far &= _no(flag)
    # Техническое, or a вид nobody defined: what is left when no flag said yes.
    return so_far


def unrecorded() -> Q:
    """Помещения nobody has classified: both flags left unset.

    Not a fourth вид — `kind_of` still answers three things and only three, and these
    помещения are технические by the remainder rule above. This asks about the record, and
    it is asked from here because these are the very two flags the rule reads: a second
    place looking at them would one day disagree with this one about what "unset" is.
    """
    return Q(is_leasable__isnull=True) & Q(is_common__isnull=True)


def _yes(flag: str) -> Q:
    return Q(**{flag: True})


def _no(flag: str) -> Q:
    """The flag is anything but true — false or never filled in.

    Written out rather than negated: `~Q(flag=True)` becomes `NOT (flag = 1)` in SQL, and
    NULL compared to anything is NULL, so a помещение with the flag unset would fall out of
    both sides of the question at once.
    """
    return Q(**{flag: False}) | Q(**{f"{flag}__isnull": True})
