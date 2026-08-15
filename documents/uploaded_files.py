"""What a file must be to be stored, and what it is served back as.

One decision over three things a file is known by before it is written anywhere: its name,
its size and its first bytes. It is a place, not a view, because the same answer is needed
twice — on the way in, to accept the file, and on the way out, to say what type it is
served as. Two accounts of "what a PDF is" would drift, and the second one would be the
one handing a browser a type we never accepted. The form asks the same place what to offer
in the file dialog, so the list of formats is stated once for the whole section.

The format is decided by the content and not by the name: a name is what the sender typed,
while the signature is what the file actually is. That way a renamed executable does not
become a scan by ending in `.pdf`. The name is not thrown away either — it is what the
refusal is phrased in, because that is how the sender knows the file. Beyond the signature
nothing is parsed: whether a PDF is a well-formed PDF is not this stage's question.

The limits are stated here as well: fifty megabytes per file and two hundred files per
submission. They are numbers of the domain, not of the framework — an archive is moved in
folders of that order, and both are said out loud in the refusal, because a sender told
merely "too big" learns nothing about how to split the batch.
"""

import hashlib
from pathlib import Path
from typing import NamedTuple

from django import forms


class Format(NamedTuple):
    """An accepted format: what the file starts with, what it is called, what it is named
    by in a folder and how it is served."""

    name: str
    signature: bytes
    suffixes: tuple
    content_type: str


#: PDF and images — what a scanner and a phone produce. Nothing that executes in a browser
#: is on the list: SVG and HTML are served from our own domain, and the sandbox headers are
#: a second line of defence, not a licence to accept a script as a document.
ACCEPTED = (
    Format("PDF", b"%PDF-", (".pdf",), "application/pdf"),
    Format("JPEG", b"\xff\xd8\xff", (".jpg", ".jpeg"), "image/jpeg"),
    Format("PNG", b"\x89PNG\r\n\x1a\n", (".png",), "image/png"),
)

#: How many bytes it takes to tell the accepted formats apart — the longest signature.
HEAD = max(len(accepted.signature) for accepted in ACCEPTED)

MEGABYTE = 1024 * 1024
#: A scan of a multi-page act fits into this many times over; a video does not fit at all.
FILE_LIMIT = 50 * MEGABYTE
#: How many files go in one submission. Not a technical ceiling but a readable one: the
#: report on a batch of two hundred is still a list a human reads, and a folder larger than
#: that is transferred in parts anyway.
BATCH_LIMIT = 200

#: What a близнец's pictures may be: the picture formats among the accepted ones. A PDF is
#: not one of them — what is pulled out of a документ to stand beside its markdown is a
#: picture, and a PDF here would be a second документ smuggled in under a name the markdown
#: refers to.
IMAGES = tuple(accepted for accepted in ACCEPTED if accepted.content_type.startswith("image/"))


def named(formats):
    """The formats the way they are shown in a refusal — the list the sender converts to."""
    return ", ".join(accepted.name for accepted in formats)


def in_a_dialog(formats):
    """What the file dialog opens on. Extensions and types both: a dialog filters by
    extension, while a file dragged in from a mail client arrives with a type and no name
    worth reading."""
    return ",".join(
        [suffix for accepted in formats for suffix in accepted.suffixes]
        + [accepted.content_type for accepted in formats]
    )


ACCEPTED_NAMES = named(ACCEPTED)
ACCEPTED_IN_A_DIALOG = in_a_dialog(ACCEPTED)
IMAGE_NAMES = named(IMAGES)
IMAGES_IN_A_DIALOG = in_a_dialog(IMAGES)

#: What a markdown file is offered as in a dialog. It has no signature to be recognised by
#: — text does not begin with anything in particular — so the dialog is the only place its
#: extension is spoken of at all; what is asked of the file itself is that it decodes.
MARKDOWN_IN_A_DIALOG = ".md,.markdown,text/markdown"

#: How a близнец is served back. Stated here rather than at the view, beside the rule that
#: accepted it: the type a file goes out as and the reading that let it in are one decision.
MARKDOWN_CONTENT_TYPE = "text/markdown; charset=utf-8"


class MultipleFileInput(forms.ClearableFileInput):
    """A file input that takes more than one file — a folder is chosen in one go.

    It stands beside the rules about files rather than beside one of the forms: both the
    batch of документы and the pictures of a близнец arrive through it, and a second copy
    would be the one that quietly stopped allowing several.
    """

    allow_multiple_selected = True


def head_of(file):
    """The first bytes of a file, with the file left where it was found.

    Both the upload and the download ask it, and both go on to read the file from the
    start afterwards: a file left mid-way by the question is a file stored or served
    without its own beginning.
    """
    head = file.read(HEAD)
    file.seek(0)
    return head


def format_of(head):
    """The format of a file by its first bytes, or `None` if it is not one we accept."""
    return next((accepted for accepted in ACCEPTED if head.startswith(accepted.signature)), None)


def content_type_for(head):
    """The type a stored file is served as — the same reading as on the way in.

    A file whose format is no longer recognised is served as a stream of bytes rather than
    guessed at: the type is what a browser decides by, and a guess is exactly the kind of
    decision the sandbox headers are there to prevent.
    """
    accepted = format_of(head)
    return accepted.content_type if accepted else "application/octet-stream"


def refusal_for(name, size, head, accepted=ACCEPTED):
    """Why this file is not stored — or `None` if it is.

    The reason is a phrase and not a code: it is shown next to the file's name in the
    report on the batch, and the sender's next action follows from it — convert, split, or
    copy the file again.

    Which formats count is asked of the caller, because it differs by what the file is
    being stored as: a документ is a scan or a photograph, whereas a picture of a близнец
    is a picture and nothing else. The reading itself does not differ, and there must not
    be two of it.
    """
    if size == 0:
        return "файл пустой — до нас дошло его имя, но не содержимое"
    if format_of(head) not in accepted:
        return _wrong_format(name, accepted)
    return _too_large(size)


def text_of(file):
    """The content of a text file, or `None` if it is not text at all.

    A близнец is judged by neither signature nor extension: text does not begin with
    anything in particular, and what is asked of it is that it decodes. A file that is not
    UTF-8 is not the markdown the ИИ-управляющий would read, whatever it is called.

    The file is left where it was found — it is stored right after being read.
    """
    raw = file.read()
    file.seek(0)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def text_refusal_for(size, text):
    """Why this markdown is not stored — or `None` if it is.

    A файл that decodes to nothing but whitespace is refused along with one that does not
    decode at all: an empty близнец is worse than none, because the документ would then
    claim to be readable and answer with nothing.
    """
    if size == 0 or (text is not None and not text.strip()):
        return "файл пустой — близнеца из него не выйдет, а документ будет числиться прочитанным"
    if text is None:
        return "файл не читается как текст в UTF-8 — близнец должен быть маркдауном"
    return _too_large(size)


def _too_large(size):
    """The one limit on a single file, said in the one phrase — or `None` if it fits.

    The limit is the same for a скан and for a близнец, and it is stated once: two copies
    of the sentence would sooner or later name two different numbers, and the sender would
    be told the one that did not apply to them.
    """
    if size > FILE_LIMIT:
        return f"файл больше {FILE_LIMIT // MEGABYTE} МБ — столько за раз не принимается"
    return None


def _wrong_format(name, accepted):
    """What to say about a file whose content is not one of the accepted formats.

    Two different things happen to the sender here, and one phrase for both would lie about
    one of them. A `.docx` is simply not a format we take. A `.pdf` that does not begin
    like a PDF is a format we do take — and «формат .pdf не принимается» would send its
    owner off to convert a file that is already in the right format and is in fact
    something else entirely, or damaged in the copying.
    """
    suffix = Path(name).suffix.lower()
    names = named(accepted)
    claimed = next((one for one in accepted if suffix in one.suffixes), None)
    if claimed is not None:
        return (
            f"расширение {suffix}, но содержимое не {claimed.name} — "
            f"принимаются только {names}"
        )
    if suffix:
        return f"формат {suffix} не принимается — только {names}"
    # A file without an extension has nothing to be named by, and inventing a name for its
    # format would be worse than admitting there is none.
    return f"формат не распознан — принимаются только {names}"


def title_from(name):
    """The title of a document from the name of its file: hundreds are not typed by hand.

    The extension goes: it says what the file is, not what the document is, and «Акт
    разграничения.pdf» in the "Название" column reads as a file name that has ended up
    where a title should be. A name that is nothing but an extension keeps it — a document
    with an empty title is not found by anything at all.
    """
    stem = Path(name).stem
    return stem.strip() or name


def digest_of(file):
    """The hash of the content — what the next batch's duplicates are recognised by.

    Read in chunks: a file is up to fifty megabytes, and the copy that `read()` would make
    is a copy of the whole archive if a batch of two hundred is being hashed.
    """
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()
