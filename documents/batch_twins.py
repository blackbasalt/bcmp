"""What each file of a batch is, when a converted folder arrives in one go.

A folder that has been through a converter holds three kinds of file side by side: the
документы, the маркдаун-близнецы made from them and the картинки those близнецы refer to.
Nothing but the names tells them apart, and the names are the contract (ADR 0012):
`akt-2024-03.md` is the близнец of `akt-2024-03.pdf`, and `![](p3-img1.png)` is the file
called `p3-img1.png`.

The sorting happens before anything is stored, because it cannot be done file by file: a
картинка is a документ in its own right — a photograph of a signed акт is exactly that —
unless some близнец of the same batch refers to it, and that is only known once every
markdown in the batch has been read.

A name in a batch names one file. Where it names two, it resolves to neither: attaching
either would be a coin toss recorded afterwards as a complete близнец, which is the half-
stored близнец the references are parsed to prevent (ADR 0011).
"""

from dataclasses import dataclass, field

from django.core.files.uploadedfile import UploadedFile

from .twin_attach import images_referenced, pictures_refusal
from .uploaded_files import (
    IMAGES,
    head_of,
    is_markdown,
    refusal_for,
    stem_of,
    stored_name,
    text_of,
    text_refusal_for,
)

#: A name held by more than one file names none of them. Kept as a value rather than as an
#: absence, so that "there is no such file in the batch" and "there are two of them" stay
#: two different answers: the first is an unresolved reference and a finding about the
#: близнец, the second is a refusal and a finding about the folder.
AMBIGUOUS = object()

#: What is said about a reference that names two files at once — the sender renames one of
#: them, which is not something a refusal can do for them.
AMBIGUOUS_PICTURE = "в пачке несколько картинок с этим именем, и ссылка на него неоднозначна"


@dataclass
class BatchedTwin:
    """One близнец of a batch: the markdown, the документ it looks for and its картинки.

    It is assembled before anything is written and carries its own refusal, if it has one:
    a близнец is attached whole or not at all (ADR 0011), so everything that could stop it
    is decided while the batch is being sorted, and storing is left with nothing to decide.
    """

    uploaded: UploadedFile
    #: The name of the документ this близнец belongs to — its own name without the extension.
    stem: str
    #: The markdown as text, decoded once while it was being judged. `None` if it is not
    #: text at all, and then the близнец is refused and nothing was parsed out of it.
    text: str | None
    #: The картинки it asks for, as the markdown wrote them. Parsed once, on reading: which
    #: files of the batch are картинки at all is decided by these, and a second parsing
    #: could only ever be a second answer to that.
    references: list = field(default_factory=list)
    #: The картинки it refers to and the batch holds and accepts, each under the name the
    #: markdown refers to it by. Kept even when the близнец is refused: they are halves of
    #: it, they land with it or not at all, and a report that did not name them would leave
    #: them looking as if they had gone onto the shelf as документы.
    pictures: list = field(default_factory=list)
    #: Why this близнец cannot be attached at all, in the words the report prints beside its
    #: name. `None` while it still can be.
    refusal: str | None = None

    @property
    def name(self):
        """The file name — how the sender knows this близнец, and how the report names it."""
        return self.uploaded.name


def sort_out(files):
    """Split a submission into the документы it stores and the близнецы it attaches.

    Two passes and not one: which files are картинки of a близнец is a question about the
    batch as a whole, and a file judged before that question is answered would be judged as
    the wrong kind of thing.
    """
    batched = [_read(uploaded) for uploaded in files if is_markdown(uploaded.name)]
    rest = [uploaded for uploaded in files if not is_markdown(uploaded.name)]
    referenced = {reference for twin in batched for reference in twin.references}
    # A file some близнец names is that близнец's картинка and not a документ of its own: it
    # is a half of a документ already on the shelf, and stored twice it would be a paper
    # nobody uploaded. Everything else is a документ, a photograph among the scans included.
    claimed = _by_name(
        (uploaded for uploaded in rest if stored_name(uploaded.name) in referenced),
        lambda uploaded: stored_name(uploaded.name),
    )
    documents = [uploaded for uploaded in rest if stored_name(uploaded.name) not in referenced]
    for twin in batched:
        _resolve(twin, claimed)
    _refuse_twins_sharing_a_name(batched)
    return documents, batched


def _read(uploaded):
    """A markdown of the batch, decoded and judged in one reading.

    Decoded here rather than at the moment of storing: the references have to be parsed out
    of the text before it is known which of the other files are картинки, and one decoding
    cannot disagree with itself.
    """
    text = text_of(uploaded)
    return BatchedTwin(
        uploaded=uploaded,
        stem=stem_of(uploaded.name),
        text=text,
        # A file that did not decode asks for nothing: there is no text to have written a
        # reference in, and the близнец is refused on the same reading.
        references=images_referenced(text) if text is not None else [],
        refusal=text_refusal_for(uploaded.size, text),
    )


def _by_name(items, name_of):
    """The things of a batch by the name they answer to — the one place that rule is applied.

    Both a картинка and a близнец are found by a name, and the name is the whole contract,
    so a name claimed twice is answered the same way in both cases: with `AMBIGUOUS`, which
    is neither of them.
    """
    found = {}
    for item in items:
        name = name_of(item)
        found[name] = AMBIGUOUS if name in found else item
    return found


def _resolve(twin, claimed):
    """Match one близнец's references against the картинки the batch holds.

    Three outcomes, and they are not the same finding. A reference nothing in the batch
    answers is recorded on the близнец and shown on the документ's page — the близнец is
    incomplete and says so. A reference answered by a file that is not a picture, or by two
    files at once, refuses the близнец whole: a картинка dropped here would come out as an
    unresolved reference, that is, as a finding the upload itself invented, and nothing
    would afterwards tell it from a схема that was never converted (ADR 0011).
    """
    if twin.refusal is not None:
        return
    refused = []
    for reference in twin.references:
        uploaded = claimed.get(reference)
        if uploaded is None:
            continue
        if uploaded is AMBIGUOUS:
            refused.append((reference, AMBIGUOUS_PICTURE))
            continue
        refusal = refusal_for(uploaded.name, uploaded.size, head_of(uploaded), IMAGES)
        if refusal is not None:
            refused.append((reference, refusal))
            continue
        twin.pictures.append((reference, uploaded))
    if refused:
        # The same sentence a близнец attached one at a time is refused with: one картинка
        # not taken, and the whole близнец is not attached — said in one place, so the two
        # ways of attaching cannot come to say it differently.
        twin.refusal = pictures_refusal(refused)


def _refuse_twins_sharing_a_name(batched):
    """Two близнеца under one name look for one документ, and the second would supersede the
    first without anyone asking for a replacement."""
    named = _by_name(batched, lambda twin: twin.stem)
    for twin in batched:
        if named[twin.stem] is AMBIGUOUS and twin.refusal is None:
            twin.refusal = (
                f"в пачке несколько близнецов с именем «{twin.stem}», и непонятно, "
                f"какой из них прикладывать"
            )
