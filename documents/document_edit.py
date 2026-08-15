"""Filling in a document's реквизиты — the other half of the bulk transfer.

A batch arrives with nothing but a name (ADR 0008): the вид is chosen once for the whole
folder, the название comes from the file name, and номер, дата выдачи, кем выдан, срок and
ревизия stay empty because whoever carries the archive across does not have them to hand.
This form is where they arrive later, one document at a time, from the document's own page.

Exactly those five fields, and not the вид or the название: those two were answered when
the file was stored, and a batch of a hundred filed under one вид is corrected by moving
the batch, not by editing a hundred pages. Nothing here is required — the point of the form
is that a document is enriched over time, and a form demanding all five at once would keep
a known номер out until a дата выдачи is found for it.
"""

from django import forms

from parties.models import Party

from .models import Document


class DateEntered(forms.DateInput):
    """A date typed into a date field, not into a line of free text.

    The browser's own picker writes `2024-03-14`, and the field must be told to read and to
    show that: left to the locale, a date already stored would come back to the form empty
    and be saved away by whoever came to fill in the номер.
    """

    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class DocumentParticularsForm(forms.ModelForm):
    """The реквизиты of one document. The document itself comes from the page, not a field."""

    class Meta:
        model = Document
        fields = ("doc_no", "issued_at", "issuer_party", "valid_until", "revision")
        labels = {
            "doc_no": "Номер",
            "issued_at": "Дата выдачи",
            "issuer_party": "Кем выдан",
            # A field without behaviour: the date is stored and shown, and threatens
            # nothing — there is no register of deadlines and no screen counting what is
            # overdue. Naming it «Действителен до» would promise exactly such a watch.
            "valid_until": "Срок действия",
            "revision": "Ревизия",
        }
        widgets = {"issued_at": DateEntered(), "valid_until": DateEntered()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        issuer = self.fields["issuer_party"]
        # Parties are set up system-wide — the same directory the passport names an owner
        # and an operator from. It is not narrowed to the organisation here: there is no
        # such narrowing anywhere in the project, and inventing one on this form alone
        # would be a second answer to "whose contractors are these" (ADR 0006).
        issuer.queryset = Party.objects.order_by("name")
        # Not «---------»: an unfilled issuer is a state of the data, and it is said in the
        # same words the page says it in.
        issuer.empty_label = "Не указан"
