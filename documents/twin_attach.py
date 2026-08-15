"""Attaching a близнец to one документ: the markdown, its pictures and the references between.

BCMP stores близнецы and does not make them (ADR 0007): what arrives here has been
converted somewhere else, and this form is where a one-off conversion lands without
requiring a batch. It asks for two things — the markdown and the pictures it refers to —
and answers one question about them: does every reference the markdown makes find a
picture.

That question is put here rather than on the model, because it is the only place where both
halves are in hand at once: the markdown is a file, the pictures are rows that do not exist
yet, and after they are stored nobody re-asks it. The same arrangement as a поэтажный план,
whose paths are matched against the spaces once, while it is being read, and never again.

All or nothing, unlike the batch of документы (ADR 0011). A batch is a hundred independent
papers, and refusing all of them over one bad file would cost the sender the afternoon; a
близнец is one thing, and stored by halves it would be exactly the incomplete близнец the
references are parsed to prevent.
"""

import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import DocumentTwin, TwinImage
from .uploaded_files import (
    BATCH_LIMIT,
    IMAGE_NAMES,
    IMAGES,
    IMAGES_IN_A_DIALOG,
    MARKDOWN_IN_A_DIALOG,
    MultipleFileInput,
    head_of,
    refusal_for,
    stored_name,
    text_of,
    text_refusal_for,
)

#: An image reference in markdown: `![подпись](p3-img1.png)`. Only the inline form is read,
#: because that is the form the contract is stated in — a converter that writes references
#: some other way writes them for a reader BCMP does not have.
IMAGE_REFERENCE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)>\s]+)")


def images_referenced(markdown):
    """The pictures the markdown asks for, in the order it asks and each one once.

    Once, because a схема referred to twice is one missing picture and not two, and the
    report on the документ's page is a list of what to go and find.
    """
    return list(dict.fromkeys(reference[1] for reference in IMAGE_REFERENCE.finditer(markdown)))


def unresolved(markdown, names):
    """The references no attached picture answers — written the way the markdown wrote them.

    A reference is matched to a name exactly, and that is the contract (ADR 0007): pictures
    are addressed **by name and not by URL**, so `![](images/p3-img1.png)` names no attached
    picture and is reported, even when a `p3-img1.png` was in fact attached. Dropping the
    folder here to be helpful would make the близнец complete only at this moment: whoever
    later shows it to a human resolves the same markdown against the same names, finds
    nothing, and by then nobody is being told.

    Reported as written, because that is the line whoever prepares the близнец has to fix.
    And asked of the references only: a picture attached and never mentioned costs a file,
    whereas a reference with nothing behind it costs an answer — the модель reads the
    документ without its схема and never learns that it did.
    """
    attached = set(names)
    return [reference for reference in images_referenced(markdown) if reference not in attached]


def pictures_refusal(refused):
    """Why a близнец is not attached, naming every картинка at fault.

    One sentence and one place for it: a близнец arrives one at a time from the документ's
    page and a hundred at a time in a batch, and both refuse it for the same reasons. Two
    accounts of the sentence would sooner or later name two different sets of formats.

    Every name, because a refusal without one does not say which of twenty схемы is not on
    the list of what is accepted (ADR 0011).
    """
    return (
        "; ".join(f"{name} — {refusal}" for name, refusal in refused)
        + f". Картинками принимаются {IMAGE_NAMES}"
    )


def attach_twin(document, markdown, text, pictures):
    """Put a близнец on a документ, discarding whatever stood in its place.

    The one account of what attaching means, asked by both the form on the документ's page
    and the batch that carries a converted folder in one go: whichever way a близнец
    arrives, it arrives whole and it supersedes the previous one whole.

    The previous one goes first and goes whole — rows and files — because there is at most
    one близнец per документ and the replacement takes its place literally. Should the new
    one then fail to be written, the документ is left without a близнец: it says so on its
    own page, and it can be attached again. What must not happen is the other order, where
    the store keeps pictures from a близнец nobody can reach any more.

    The rows of the new one are written in one transaction, and the files it wrote are taken
    back out by hand if that transaction does not hold. A transaction rolls back rows and
    knows nothing about the store, so a failure on the third picture would otherwise leave
    the first two lying there with no row pointing at them — the very orphan a близнец is a
    row of its own for (ADR 0007).
    """
    superseded = document.attached_twin()
    if superseded is not None:
        superseded.discard()
    written = []
    try:
        with transaction.atomic():
            twin = DocumentTwin.objects.create(
                document=document,
                markdown=markdown,
                unmatched_images=unresolved(text, [name for name, _ in pictures]),
            )
            written.append(twin.markdown)
            for name, uploaded in pictures:
                # The name is the contract the markdown refers to the picture by, and it is
                # stored apart from the file: the file's own path is where Django put it,
                # which is neither what the markdown says nor anything it could say.
                image = TwinImage.objects.create(twin=twin, name=name, file=uploaded)
                written.append(image.file)
    except Exception:
        for file in written:
            file.delete(save=False)
        raise
    return twin


class TwinPictures(forms.FileField):
    """The pictures of one близнец, judged one at a time and accepted or refused together.

    Each is judged by its content, by the same reading that lets a документ in — but against
    the picture formats alone: a PDF among the схемы would be a second документ smuggled in
    under a name the markdown refers to.
    """

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, list) else ([data] if data else [])
        if len(files) > BATCH_LIMIT:
            raise ValidationError(
                f"За раз принимается не больше {BATCH_LIMIT} картинок, а прислано "
                f"{len(files)}."
            )
        refused = [
            (uploaded.name, refusal)
            for uploaded in files
            if (refusal := refusal_for(uploaded.name, uploaded.size, head_of(uploaded), IMAGES))
        ]
        if refused:
            raise ValidationError(f"Близнец не приложен: {pictures_refusal(refused)}.")
        self._check_names(files)
        return files

    @staticmethod
    def _check_names(files):
        """Two pictures under one name make a reference ambiguous — said here, in words.

        The database says the same thing with a constraint, but it says it as a failure of
        the save; whoever is attaching a близнец needs to hear which of their names collided.
        """
        names = [stored_name(uploaded.name) for uploaded in files]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValidationError(
                "Под одним именем прислано несколько картинок, и ссылка на такое имя "
                f"неоднозначна: {', '.join(repeated)}."
            )


class DocumentTwinForm(forms.Form):
    """The близнец of one документ. The документ itself comes from the page, not a field.

    Attaching and replacing are one form and one submission: a близнец is replaced whole,
    and «приложить» over an empty slot and «заменить» over a full one differ in what is
    already there, not in what is sent.
    """

    markdown = forms.FileField(
        label="Маркдаун",
        help_text=(
            "Содержимое документа в маркдауне и картинки, на которые он ссылается. "
            "BCMP близнеца не изготавливает — он его хранит."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": MARKDOWN_IN_A_DIALOG}),
    )
    images = TwinPictures(
        label="Картинки",
        required=False,
        help_text=(
            f"{IMAGE_NAMES}. Ссылка «![](p3-img1.png)» разрешается в картинку с этим "
            f"именем; неразрешённые показываются на странице документа."
        ),
        widget=MultipleFileInput(attrs={"accept": IMAGES_IN_A_DIALOG}),
    )

    def __init__(self, *args, document, **kwargs):
        super().__init__(*args, **kwargs)
        self.document = document
        #: The markdown as text, read while it was being judged and kept for the references
        #: to be parsed out of. It stands here rather than being read a second time in
        #: `save`: the file is decoded once, and one decoding cannot disagree with itself.
        self.text = None

    def clean_markdown(self):
        """The markdown is read here, once: it is judged by decoding and stored by the same
        reading, and the references are parsed out of the text this produced."""
        uploaded = self.cleaned_data["markdown"]
        self.text = text_of(uploaded)
        refusal = text_refusal_for(uploaded.size, self.text)
        if refusal is not None:
            raise ValidationError(f"{uploaded.name} — {refusal}.")
        return uploaded

    def save(self):
        """Store the близнец — by the one account of what attaching means.

        The pictures are handed over already named: the name is what the markdown refers to
        them by, and this form is where a browser's file name becomes that name.
        """
        images = self.cleaned_data.get("images") or []
        return attach_twin(
            self.document,
            self.cleaned_data["markdown"],
            self.text,
            [(stored_name(uploaded.name), uploaded) for uploaded in images],
        )
