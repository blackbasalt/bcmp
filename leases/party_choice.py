"""Выбор Стороны поиском — как из реестра в 699 строк выбирают одну.

Two fields on the аренда name a Сторона — арендатор and арендодатель — and neither of them
can be a list: the реестр holds 699 Сторон, mostly поставщики, and a `<select>` over it is
a scroll rather than a choice. So the list is what a поиск found, and nothing until
something is looked for.

The поиск travels as a parameter on the карточка's own address (`…/card/?tenant_q=аль`)
rather than through an автодополнение of its own: the stage adds no address, and отбор
travelling in the address is what the словарь already says about every other screen. This
module holds the two halves that are not about the address — what «нашлось» means, and how
a found Сторона stands on the form.

Two readings are settled here:

- **Ищется по названию и по БИН/ИИН.** Two companies with similar названия are told apart
  by the number, and whoever has the number to hand types it. The regular-expression route
  and not `icontains`: on SQLite `LIKE` folds case for ASCII alone, so «альфа» would not
  find «Альфа» (ADR 0014). Whoever "tidies" this into `icontains` breaks the search for
  Russian without breaking one ASCII test.
- **Поиск идёт по всем Сторонам.** The реестр is system-wide and the isolation stands on
  the помещение (ADR 0018): narrowed to the reader's own организация, a new арендатор
  nobody has met yet would be unfindable, which is the one case заведение аренды exists
  for. Nothing about another client is disclosed by it — a Сторона belongs to no client.

«Не нашлось — завести Сторону» is deliberately **not** here and not on the form: a Сторона
is entered as a separate step, or the реестр of 699 rows fills with «ТОО Альфа», «Альфа
ТОО» and «ТОО «Альфа»» — three writings of one company, and no screen able to tell which of
them the аренда means.
"""

import re

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from parties.models import Party


def matching(text) -> Q:
    """Название or БИН/ИИН containing the text, whatever the case of either."""
    wanted = re.escape(text)
    return Q(name__iregex=wanted) | Q(bin_iin__iregex=wanted)


def found(text):
    """The Стороны a поиск turned up — and none at all until something is asked.

    An empty поиск is not a поиск over everything: 699 rows are not an answer, and offering
    them would be the very list the поиск exists instead of.
    """
    text = (text or "").strip()
    if not text:
        return Party.objects.none()
    return Party.objects.filter(matching(text)).order_by("name")


class PartyChoice(forms.ModelChoiceField):
    """Одна Сторона из общесистемного реестра — та, что нашлась, а не та, что в списке.

    What may be **chosen** and what is **offered** are two different sets here, and that is
    the point. The queryset stays the whole реестр, because that is what a submitted key is
    checked against: narrowed to the matches of the поиск, a Сторона picked and then
    searched away from the list would be refused as «недопустимый выбор» — a refusal about
    the screen's own bookkeeping rather than about the аренда. What the list shows is set by
    `offer`, and only the list moves when the поиск does.
    """

    #: What the list stands on until a поиск has been made: nothing. Pairs of key and
    #: label rather than Стороны, because the markup writes the options out itself — a
    #: template cannot call `label_from_instance`, and a name printed by hand there would
    #: be a second wording of how a Сторона is named.
    offered = ()

    def offer(self, parties, chosen=None):
        """The Стороны this list stands on: what нашлось, plus whoever is already chosen.

        A choice already made never disappears from its own list: a refusal redraws the
        form, and a Сторона picked before it must still be there to be sent again — or the
        отказ would quietly cost the very field it did not complain about.
        """
        standing = list(parties)
        kept = self._chosen(standing, chosen)
        if kept is not None:
            standing.insert(0, kept)
        self.offered = [(party.pk, self.label_from_instance(party)) for party in standing]

    def _chosen(self, standing, chosen):
        """The Сторона already picked, if it is one and is not on the list already.

        A key that is not a key at all — an address typed by hand, a stale form — is nobody:
        the field refuses it when the form is checked, and there is nothing to put on the
        list for it meanwhile.
        """
        if not chosen or any(str(party.pk) == str(chosen) for party in standing):
            return None
        try:
            return self.queryset.filter(pk=chosen).first()
        except (ValidationError, ValueError, TypeError):
            return None

    def label_from_instance(self, party):
        """«ТОО «Альфа» — 050340008889»: the number is what tells two similar названия apart.

        A Сторона with no БИН/ИИН recorded is named by its название alone — a dash after the
        name would promise a number the реестр does not hold.
        """
        return f"{party.name} — {party.bin_iin}" if party.bin_iin else party.name
