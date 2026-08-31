"""Правка и удаление аренды — что карточка держит на каждой строке и что на одной из них.

Ставка исправляется на месте, в самой аренде, а не вторым «правильным» рядом рядом с
неправильным. Аренда, заведённая по ошибке, удаляется целиком — а съезд арендатора
удалением не является.

Those two are one screen apart and must never read alike. A съезд is a дата «по»: the аренда
stays in the base, the карточка stops listing the departed арендатор on its own and the
складка keeps them (ADR 0004's reading of an empty end). Deleting one instead would erase
the помещение's history every time somebody moved out, and «по какой ставке сдавалось в
марте» would lose its answer along with them.

For the same reason there is no «продлить» here: продление на новый срок is a new аренда and
not a shifted end on the old one (ADR 0017). A button offering it would invite exactly the
правка that costs the история.

Удаление takes two presses: the first asks, the second destroys. У записи нет отмены, и
промах мыши не должен её стоить — what makes the misclick impossible is the two presses in
two different places, the second reachable only through a redrawn карточка. Where the
submissions go and how they are told apart is `SpaceCardView.post`'s to state; what is
settled here is what the screen holds between them.

Every row carries its own form, and the question stands on the very аренда it was asked
about. One form for the whole block would leave «which of the three аренды is it editing»
answered by the state of the screen rather than by the screen itself.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .lease_form import LeaseForm

if TYPE_CHECKING:
    from .models import Lease


@dataclass(frozen=True)
class Row:
    """Одна аренда на карточке: сама аренда и то, что с ней разрешено сделать.

    An empty `form` is the refusal itself: whoever may not write into this организация's
    data is offered neither правка nor удаление, and the карточка stays a screen rather than
    a бланк (ADR 0005).

    `confirming` says whether this row is holding the question over its own deletion. It is
    the state of a row and not of the block: the question was asked about one аренда, and
    the row beside it must not look as though it had been asked too.
    """

    lease: "Lease"
    form: LeaseForm | None = None
    confirming: bool = False


@dataclass(frozen=True)
class AtHand:
    """Аренда, о которой запрос, и то, что запрос на ней оставил: отказ или вопрос.

    A `Row` with the аренда left out, and not a `Row` itself, precisely because the аренда
    is what it must not carry: a refused form holds an instance already overwritten with
    what was typed, and drawing the row from that would print what was not saved as though
    it had been. The строка is drawn from the аренда as the base holds it, and what is taken
    from here is the reason on the form and the question over the deletion — nothing else.
    """

    key: str
    form: LeaseForm | None = None
    confirming: bool = False


def rows(leases, *, space, offered: bool, at_hand: AtHand | None = None) -> tuple[Row, ...]:
    """Аренды подряд, каждая со своей формой правки, и одна — с тем, что принёс запрос.

    Every form comes up filled in with the аренда it stands on: правка corrects what is
    recorded, and a form that arrived empty would erase the rest of the аренда with the
    first save.

    A reader gets no form at all — neither folded away nor disabled: offered and refused at
    once reads as a breakage.
    """
    if not offered:
        return tuple(Row(lease) for lease in leases)
    return tuple(_row(lease, space, at_hand) for lease in leases)


def fold_stands_open(behind) -> bool:
    """Приходится ли открыть складку за читателя — есть ли за ней вопрос или отказ.

    A question asked about an аренда that is not today's, or a refusal on one, is answered
    into a складка that is shut: the карточка comes back looking exactly as it went, and the
    press is made again. A складка with nothing behind it but аренды stays shut, which is
    what it is for.
    """
    return any(row.confirming or (row.form is not None and row.form.errors) for row in behind)


def _row(lease, space, at_hand: AtHand | None) -> Row:
    """One row, and the аренда the request is about is the one that differs."""
    if at_hand is None or str(lease.pk) != at_hand.key:
        return Row(lease, LeaseForm(space=space, instance=lease))
    return Row(lease, at_hand.form or LeaseForm(space=space, instance=lease), at_hand.confirming)
