"""How a single документ reads on its own page.

The particulars are assembled here rather than in the markup, for the same reason the
passport's sections are: what a page says about a document is a rule about the data — which
particulars there are, in what order they are read and how each of them is written out —
and the template is left to print a ready list. The dash for an empty value is not put in
here: `or_missing` does it, once for the whole project.

The order is the order in which a paper is read: what kind of document this is, what it is
called, then its реквизиты — номер, дата выдачи, кем выдан — and last what says whether it
is still the current one, срок and ревизия. It is not sorted alphabetically: the page
answers "what is this document", and that question has an order.
"""

from dataclasses import dataclass
from typing import Any

from .document_display import day, twin_and_its_pictures
from .models import DocumentLink


@dataclass(frozen=True)
class Field:
    """A row of the page. An empty value stays None — the dash is put in by `or_missing`.

    The name is the page's contract: the markup carries it in `data-field`, so a particular
    can be pointed at from outside without knowing what the layout around it looks like.
    """

    name: str
    label: str
    value: Any


@dataclass(frozen=True)
class Taken:
    """One thing that goes with the документ when it is deleted: its name, and its words.

    Named as well as worded for the same reason a `Field` is: the markup carries the name in
    `data-taken`, so «что-то уносится» and «вот что уносится» are two different assertions —
    and the words themselves are free to be rewritten without anything losing sight of what
    they were about.
    """

    name: str
    said: str


def taken_with(document):
    """What goes with a документ when it is deleted, named one thing at a time.

    Named rather than counted, and named before anything is destroyed: «удалить документ»
    over a документ with a близнец means more than the row the reader is looking at, and
    saying so is the whole reason the question is put at all.

    One list for both moments — the confirmation before and the line said afterwards. Two
    would let the warning promise one thing and the report state another, and the reader
    would have no way of telling which of them was the truth.

    A документ with neither файл nor близнец takes nothing with it, and the list is empty:
    the привязки go too, but they are the документ's own presence on a building's card and
    outlive it in no form at all — naming them would offer the reader something to weigh
    that weighs nothing.
    """
    taken = []
    if document.file_uri:
        taken.append(Taken("original", "оригинал документа"))
    twin = document.attached_twin()
    if twin is not None:
        taken.append(Taken("twin", twin_and_its_pictures(twin.images.count())))
    return tuple(taken)


@dataclass(frozen=True)
class Deletion:
    """The deletion as the page holds it: whether the question is being asked, and what the
    answer would take with it.

    Two states of one thing rather than two separate offers, because they stand in the same
    place on the screen and mean the same action at two moments. The state is the page's
    contract — the markup carries it in `data-deletion` — and `taken` is filled in only
    while the question is being asked: on a page nobody asked it on, working out what would
    go would cost a query per render for a list nothing shows.
    """

    confirming: bool
    taken: tuple = ()


def particulars(document):
    """Everything recorded about a document, ready to print.

    `valid_until` and `revision` stand here as two particulars among the rest and are not
    marked out in any way: they are shown and they trigger nothing — no expiry screen, no
    warning, no count of what is overdue. A реестр сроков is a different stage, and until
    it exists a highlighted date would promise a watch that nobody keeps.
    """
    return (
        Field("kind", "Вид", document.get_kind_display()),
        Field("title", "Название", document.title),
        Field("doc_no", "Номер", document.doc_no),
        Field("issued_at", "Дата выдачи", day(document.issued_at)),
        # A party on screen is a name: you cannot call a party's identifier.
        Field("issuer", "Кем выдан", document.issuer_party.name if document.issuer_party else None),
        Field("valid_until", "Срок действия", day(document.valid_until)),
        Field("revision", "Ревизия", document.revision),
    )


def linked_buildings(document, buildings):
    """The BCs the document is attached to, taken through the buildings' own checkpoint.

    A привязка holds an identifier and not a building: it is resolved against the BCs the
    reader may see (ADR 0001), rather than by following the identifier straight to a row.
    The document is visible through its own organisation and not through its привязки
    (ADR 0006), so the two questions are asked separately — one about the paper, one about
    the building it names.

    Two of the nine entity types are narrowed away here, and for the same reason. `space`
    is the only one this stage forms, the other eight pointing at empty or non-existent
    tables (ADR 0008). And of the spaces only the BCs are resolved, because a BC is what
    the page leads to: every привязка on the page opens the building's card, and a link to
    a floor or a room — which the схема permits and the Django admin can create — has no
    card to open and would be an address that answers 404. Whichever stage starts attaching
    papers to rooms brings the screen those rooms are read on with it.
    """
    spaces = document.links.filter(entity_type=DocumentLink.EntityType.SPACE)
    return buildings.filter(pk__in=spaces.values("entity_id")).order_by("name", "code")
