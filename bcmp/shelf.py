"""What a полка is, apart from what any one полка is about.

Полка документов, полка помещений, полка Сторон: three different questions, and two things
none of them is about. Whether anything was asked at all, and what becomes of a condition
that did not read, are true of a полка because it is a полка — so they are held here, in the
project, rather than in one раздел, where the other two would be borrowing them from a
neighbour whose domain they have no part in.

Held in each раздел instead they would be three copies, and copies drift quietly: a полка
that silently dropped an unreadable condition looks like it is working (ADR 0014).

`BuildingChoice` is deliberately not here. It is about a domain field — which БЦ — and stays
in `documents`, where the three forms that offer it take it from today.
"""

from django import forms


class Search(forms.Form):
    """The отбор of a полка: what was asked of it, and what the полка narrows to.

    A полка says what its conditions are and how each of them narrows, in `answering`. What
    it does not have to say again is that an отбор nobody filled in was never asked, and
    that one that did not read narrows to nothing.
    """

    @property
    def asked(self):
        """Whether anything was asked of the полка at all.

        Read off what came in rather than off what came back: a полка can be empty and
        narrowed at the same time, and which of the two an empty screen is cannot be seen in
        the rows that came back — «ничего не нашлось» sends the reader to change what they
        asked, «ничего не загружено» sends them to whoever loads the data.

        What each полка makes of the reading is its own. The полка документов branches its
        empty screen on it; the полка помещений branches on the size of the un-narrowed
        полка and asks this only whether there is a question worth offering to drop. Both
        ask the same thing of the отбор, and neither should have to work it out for itself.

        A condition that is present but unreadable counts as asked. It matched nothing, and
        that is what the reader is told; the alternative is a screen that silently ignores
        half of what was typed into it.
        """
        return any(self.data.get(name) for name in self.fields)

    def narrow(self, shelf):
        """The rows that answer the отбор, out of the ones the reader may see.

        It narrows what it is handed and does not go looking for rows itself: whose rows
        these are is decided by the chokepoint before this is called (ADR 0001, ADR 0006),
        and a second place selecting rows would be a second place to one day disagree about
        whose they are.

        An отбор that did not read narrows to nothing rather than being dropped (ADR 0014).
        Dropped, a tampered address naming another client's building would answer with the
        whole полка — the reader's own, so nothing leaks, but the screen would state an
        отбор it never performed. The guard stands here rather than at the head of each
        `answering` because it belongs to no one полка: left to each of them, the third copy
        is the one that quietly goes missing.
        """
        if not self.is_valid():
            return shelf.none()
        return self.answering(shelf)

    def answering(self, shelf):
        """The rows this полка's own conditions leave of the ones they are handed.

        Reached only once the отбор has read, so it works off `cleaned_data` and asks
        nothing about validity.
        """
        raise NotImplementedError
