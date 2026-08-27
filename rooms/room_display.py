"""How the полка помещений reads on screen: what a вид is called and what the count says.

Both are phrases rather than figures put beside a table. «Показано 47 из 583 помещений»
answers a question; «47 / 583» is a quantity the reader has to guess at — the same device
as «нанесено 47 из 82 помещений» beneath a план.

Agreement with the numeral is worked out here rather than assembled in the markup: «из 1
помещений» reads as a glitch on the screen, not as a single помещение.
"""

from building_passport import space_kind
from building_passport.passport_display import NBSP

#: A вид as the полка names it: about one помещение, because a row is one помещение. The
#: план's legend says the same three things in the plural — «Арендопригодные» captions a
#: colour covering many contours at once — so the words are not shared between the two
#: screens even though the виды are.
NAME_OF = {
    space_kind.LEASABLE: "Арендопригодное",
    space_kind.COMMON: "МОП",
    space_kind.TECHNICAL: "Техническое",
}

#: The виды as a list to choose from, in the order the rule states them.
KIND_CHOICES = [(kind, NAME_OF[kind]) for kind in space_kind.KINDS]


def rooms_shown(shown: int, whole: int) -> str:
    """«Показано 47 из 583 помещений» — how much of the полка the отбор left standing.

    Two numbers and not one: a narrowed полка must still say the size of what was narrowed,
    or the reader is left holding 47 with nothing to compare it against.

    The noun agrees with the second number, not the first: it is «из 583» that governs it.
    The predicate stays «Показано» throughout — the subject is «1 из 583», a part of
    something, and a part is neuter however small it is.

    Deliberately not `document_display.agreeing_with`, which is a different rule and not the
    same rule copied: «из» takes the genitive, so there are two forms here and not three —
    «из 1 помещения», «из 2 помещений», «из 5 помещений». Run through the three-way rule the
    line would read «из 2 помещения». Whoever unifies the two will break this without
    breaking that.
    """
    rooms = "помещения" if whole % 10 == 1 and whole % 100 != 11 else "помещений"
    return f"Показано {shown} из {whole}{NBSP}{rooms}"
