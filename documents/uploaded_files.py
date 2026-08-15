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

#: The formats named the way they are shown in a refusal — the list the sender converts to.
ACCEPTED_NAMES = ", ".join(accepted.name for accepted in ACCEPTED)

#: What the file dialog opens on. Extensions and types both: a dialog filters by extension,
#: while a file dragged in from a mail client arrives with a type and no name worth reading.
ACCEPTED_IN_A_DIALOG = ",".join(
    [suffix for accepted in ACCEPTED for suffix in accepted.suffixes]
    + [accepted.content_type for accepted in ACCEPTED]
)


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


def refusal_for(name, size, head):
    """Why this file is not stored — or `None` if it is.

    The reason is a phrase and not a code: it is shown next to the file's name in the
    report on the batch, and the sender's next action follows from it — convert, split, or
    copy the file again.
    """
    if size == 0:
        return "файл пустой — до нас дошло его имя, но не содержимое"
    if format_of(head) is None:
        return _wrong_format(name)
    if size > FILE_LIMIT:
        return f"файл больше {FILE_LIMIT // MEGABYTE} МБ — столько за раз не принимается"
    return None


def _wrong_format(name):
    """What to say about a file whose content is not one of the accepted formats.

    Two different things happen to the sender here, and one phrase for both would lie about
    one of them. A `.docx` is simply not a format we take. A `.pdf` that does not begin
    like a PDF is a format we do take — and «формат .pdf не принимается» would send its
    owner off to convert a file that is already in the right format and is in fact
    something else entirely, or damaged in the copying.
    """
    suffix = Path(name).suffix.lower()
    claimed = next((accepted for accepted in ACCEPTED if suffix in accepted.suffixes), None)
    if claimed is not None:
        return (
            f"расширение {suffix}, но содержимое не {claimed.name} — "
            f"принимаются только {ACCEPTED_NAMES}"
        )
    if suffix:
        return f"формат {suffix} не принимается — только {ACCEPTED_NAMES}"
    # A file without an extension has nothing to be named by, and inventing a name for its
    # format would be worse than admitting there is none.
    return f"формат не распознан — принимаются только {ACCEPTED_NAMES}"


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
