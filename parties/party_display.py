"""How the раздел «Стороны» reads on screen: how much of the полка is shown, what a Сторона
rents, and when her ближайший повод falls.

All three are phrases rather than figures put beside a table. «Показано 12 из 637 Сторон»
answers a question; «12 / 637» is a quantity the reader has to guess at — the same device as
«Показано 47 из 583 помещений» beneath the полка помещений and «нанесено 47 из 82» beneath a
план.

Agreement with the numeral is worked out here rather than assembled in the markup: «из 1
Сторон» reads as a glitch on the screen, not as a single Сторона. Two numerals stand in this
раздел and they take two different rules — one is governed by «из» and one is not — so
neither is the other's rule with the words swapped, and each says so where it is written.
"""

from building_passport.passport_display import NBSP

from .occasions import Occasion

#: Сторона, не арендующая ни одного помещения: a bare dash, and deliberately not
#: `or_missing`'s «— нет данных». 637 of the 699 Стороны are поставщики who rent nothing at
#: all, and that is an answer rather than a gap in the record — «нет данных» would report
#: what BCMP knows as what it does not. The same reading `lease_display.NOBODY` gives the
#: empty «Арендатор» cell, spelled out here because it is a different question: there nobody
#: sits in the помещение, here the Сторона sits nowhere.
NOTHING = "—"


def parties_shown(shown: int, whole: int) -> str:
    """«Показано 12 из 637 Сторон» — how much of the полка the отбор left standing.

    Two numbers and not one: a narrowed полка must still say the size of what was narrowed,
    or the reader is left holding 12 with nothing to compare it against.

    The noun agrees with the second number, not the first: it is «из 637» that governs it.
    The predicate stays «Показано» throughout — the subject is «12 из 637», a part of
    something, and a part is neuter however small it is.

    «из» takes the genitive, so there are two forms here and not three — «из 1 Стороны», «из
    2 Сторон», «из 5 Сторон». It is the rule `room_display.rooms_shown` follows and not the
    one `document_display.agreeing_with` states; it is spelled out again rather than imported
    from помещения because a Сторона and a помещение share a grammar and nothing else, and an
    import between the two разделы for the sake of three lines would be the first thing to
    look wrong when either of them moves.

    The rows are counted and named Сторонами though the полка is a полка учётных карточек: a
    Сторона two of the reader's clients both know is two rows, and the line describes what is
    on the screen. A count that saw one Сторона there would contradict the table above it.
    """
    parties = "Стороны" if whole % 10 == 1 and whole % 100 != 11 else "Сторон"
    return f"Показано {shown} из {whole}{NBSP}{parties}"


def rooms_rented(count: int) -> str:
    """«5 помещений» — what one row says under «Арендует», or a dash where nothing is rented.

    Counted in помещениях and never in метрах: a Сторона sitting in a помещение inside
    another помещение would be counted twice by an unknown amount, because nothing in a row
    tells that nesting from the other one (ADR 0015, ADR 0019). A помещение cannot be counted
    twice — it is one row of the полка помещений and one помещение here.

    Three forms and not two, because this numeral governs a nominative: it is the rule
    `document_display.agreeing_with` states, and not `parties_shown`'s above, where «из»
    takes the genitive and the forms collapse to two. Whoever unifies the two will break this
    one without breaking the other.

    The phrase the ticket reads by — «Арендует 5 помещений» — is the heading and the cell
    together, as «Арендатор» and «3 арендатора» already are on the полка помещений: the
    column says what is being counted once, at the top, rather than in every row.
    """
    if not count:
        return NOTHING
    if 11 <= count % 100 <= 14:
        rooms = "помещений"
    elif count % 10 == 1:
        rooms = "помещение"
    elif 2 <= count % 10 <= 4:
        rooms = "помещения"
    else:
        rooms = "помещений"
    return f"{count}{NBSP}{rooms}"


def nearest_occasion(occasion: Occasion | None) -> str:
    """«09.08.2026 · День строителя» — what one row says under «Ближайший повод».

    The день first and the name after it: the column is sorted by how soon, and it is read
    down the table by an eye hunting for what to prepare for first — the name answers a
    question the date has already raised.

    The year is printed though a повод recurs every year: the ближайший повод asked about in
    December falls in January of the next one, and «05.01» would keep quiet about exactly
    what the reader needs to know.

    Whose повод it is stands after a dash and only where it is anybody's: a профессиональный
    has no person behind it, and a физлицо's день рождения needs none — her name is already
    the first cell of the row. A bare dash where there is no повод at all, and `NOTHING`
    rather than `or_missing`'s «нет данных» for the reason the «Арендует» cell above uses it:
    637 of the 699 Стороны are поставщики nobody has written a день рождения for, and that is
    an answer rather than a gap in the record.
    """
    if occasion is None:
        return NOTHING
    whose = f" — {occasion.whose}" if occasion.whose else ""
    return f"{occasion.on:%d.%m.%Y}{NBSP}· {occasion.name}{whose}"
