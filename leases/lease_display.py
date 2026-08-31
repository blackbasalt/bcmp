"""Как аренда читается на экране: две цифры одной фразой, срок, метры и ставка.

The phrases live here rather than in the markup for the reason `room_display` states: «сдано
210 из 300 м²» answers a question, «210 / 300» is a quantity the reader has to guess at, and
agreement with a numeral worked out between tags is agreement nobody checks.

Метры are printed without an empty tail: «сдано 210 из 300 м²» is a phrase read aloud, and
«210,00 из 300,00» makes the reader parse four decimals that say nothing. Where there is
something in the tail it stays — «сдано 64,50 из 66,43 м²» — and the паспорт keeps its «6,55
м²» throughout: there a площадь is an обмер and the hundredths are the measurement itself.
The ставка keeps its копейки for the opposite reason: it is a sum of money, and money with
its tail cut off reads as a rounded figure rather than as a condition of an agreement.
"""

from building_passport.passport_display import NBSP, is_missing, measure, quantity

#: Свободно: an арендопригодное помещение with nobody sitting in it today. The словарь's own
#: word for that state, and the one the полка помещений is to say when it comes to ask the
#: same question — «вакансия» is not this project's word for it.
FREE = "Свободно"


def metres(value) -> str | None:
    """A number of metres as a phrase counts them: «300», «66,43», «1 250».

    The notation is the паспорт's own; what is dropped is an empty tail and only an empty
    one, so «66,43» keeps its hundredths and «300,00» does not print two zeros a reader has
    to look past.
    """
    if is_missing(value):
        return None
    return quantity(value).removesuffix(",00")


def lease_area(value) -> str | None:
    """The арендуемая площадь of one аренда. Missing stays missing — the row prints a dash."""
    metric = metres(value)
    return None if metric is None else f"{metric}{NBSP}м²"


def lease_rate(value) -> str | None:
    """The ставка with its unit: without «за м² в месяц» 4500 reads as the rent for the lot.

    The unit is the метры and the месяц and not the currency: every ставка in BCMP is in
    тенге, there is no currency field to read one off, and a screen naming a currency the
    record does not hold would be the first to be wrong when a договор in another one
    arrives.
    """
    return measure(value, "за м² в месяц")


def lease_term(lease) -> str:
    """The срок as the словарь reads it: «с 01.01.2026 по 31.12.2026», «… по сей день»."""
    ends = f"{lease.valid_to:%d.%m.%Y}" if lease.valid_to else "сей день"
    return f"с {lease.valid_from:%d.%m.%Y} по {ends}"


def shows_leases(occupancy, entry_offered) -> bool:
    """Whether the карточка carries the аренда block at all.

    On every арендопригодное помещение, empty or not: «свободно» has to read as an answer
    and not as a section that failed to load. On a МОП or a техническое only when there is
    an аренда to show — the банкомат in the лобби is visible where it stands, and a section
    promising data that does not exist is not put in front of a reader.

    And wherever заведение is offered, whatever the вид: the form is the reason the block is
    there for an администратор организации, and an empty лобби with no block is a лобби the
    банкомат standing in it can never be entered on. What a reader is spared is a section
    with nothing in it; a form is not nothing.
    """
    return occupancy.is_leasable or occupancy.has_any or entry_offered


def occupancy_line(occupancy) -> str | None:
    """«Сдано 210 из 300 м², ещё у 2 аренд площадь не заведена» — or «Свободно», or nothing.

    Three states and not one number. Свободно is said first and only where it is true: it is
    an answer on its own, and «сдано 0 из 300 м²» makes the reader work out the same thing
    from arithmetic. A МОП with nobody in it says nothing — it is not свободно, and the
    складка below carries whoever has left. A помещение whose own площадь is not recorded
    gets no отношение at all — a gap in the данные помещения is not dressed up as a доля —
    and the аренды under the line still name themselves.
    """
    if not occupancy.in_force:
        return FREE if occupancy.is_free else None
    if is_missing(occupancy.area_m2):
        return None
    line = f"Сдано {metres(occupancy.let_m2)} из {metres(occupancy.area_m2)}{NBSP}м²"
    silent = occupancy.leases_without_area
    if silent:
        line += f", ещё у {silent} {_leases_in(silent)} площадь не заведена"
    return line


def fold_title(occupancy) -> str:
    """What the складка promises: «Прошлые аренды (2)» — so opening it is a choice.

    Аренды that have not begun stand behind the same складка and are named in it: a
    продление entered while the current срок runs is neither today's nor gone, and calling
    it «прошлая» is the one thing about it that would be false.
    """
    behind = len(occupancy.past) + len(occupancy.future)
    named = "Прошлые и будущие аренды" if occupancy.future else "Прошлые аренды"
    return f"{named} ({behind})"


def _leases_in(count: int) -> str:
    """«у 1 аренды», «у 2 аренд», «у 5 аренд» — «у» takes the genitive, so there are two forms.

    Deliberately not `room_display.rooms_shown`'s rule and not `document_display`'s: those
    agree with a different governor. Whoever unifies the three will break this one without
    breaking the others.
    """
    return "аренды" if count % 10 == 1 and count % 100 != 11 else "аренд"
