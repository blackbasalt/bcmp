"""How the documents section reads on screen.

Three rules: how a date is written, how many documents are on screen, and what is said
about a batch that has just been uploaded. The last two are numbers, and both are said as
phrases rather than as figures beside the table: «Показано 12 документов» answers a
question, while «12» next to a table is a quantity the reader has to guess at. The same
device as «нанесено 47 из 82 помещений» on a floor.

Agreement with the numeral is worked out here rather than assembled in the markup:
«Показано 1 документов» reads as a glitch on the screen, not as a single document, and it
is a place, not a template, that should sort this out.
"""

from django.contrib import messages

#: A non-breaking space: a number and the word attached to it must not drift apart across
#: lines — the same rule as for the areas in the building passport.
NBSP = "\u00a0"


def day(value):
    """A date as it is read in this section: 14.03.2024.

    The format is stated once and not twice: the same date stands in the table and on the
    document's own page, and two accounts of how a date looks would drift — the reader
    would then be told the same day in two notations on two screens of one section.

    A date that was never filled in stays None: the dash over it is `or_missing`'s business,
    the same rule as everywhere else in the project.
    """
    return value.strftime("%d.%m.%Y") if value else None


def agreeing_with(count, one, few, many):
    """The form of the word for a number: 1 документ, 2 документа, 5 документов.

    Eleven is not «одиннадцать документ»: the second digit of the number cancels the
    first, so tens are checked before ones.
    """
    if 11 <= count % 100 <= 14:
        return many
    ones = count % 10
    if ones == 1:
        return one
    if 2 <= ones <= 4:
        return few
    return many


def documents_shown(count):
    """How many documents are on screen — as a phrase, fully agreeing with the number."""
    documents = agreeing_with(count, "документ", "документа", "документов")
    # The predicate agrees with the same number as the noun: «Показан 1 документ», but
    # «Показано 2 документа». It is not worked out separately — that would create a second
    # place deciding whether the number is singular.
    shown = "Показан" if documents == "документ" else "Показано"
    return f"{shown} {count}{NBSP}{documents}"


def batch_report(report):
    """What to say about an uploaded batch: how loudly, and in what words.

    Three phrases at most, and each one about a different next action — nothing further to
    do, look at the document that is already there, send these files again. Not one line
    per file: a batch of two hundred would bury the count of what got through under the
    list of what did not.

    How many files were stored is said even when everything went through: the screen after
    the upload is the confirmation, but a folder of hundreds arrives on it looking much the
    same as before, and «загружено 96» is the only place the ninety-six are counted.
    """
    said = [(_level_of(report), files_stored(len(report.stored)))]
    if report.already_stored:
        said.append((messages.INFO, _listed("Уже загружены", _as_stored(report.already_stored))))
    if report.refused:
        said.append((messages.WARNING, _listed("Не сохранены", report.refused)))
    return said


def _level_of(report):
    """How loudly the count is said.

    A batch that stored nothing because every file was refused is not a success, and a
    green alert over it would be read as one — the colour is seen before the sentence. A
    batch that stored nothing because everything in it was already on the shelf is not a
    failure either: nothing needed doing, and that is worth saying quietly.
    """
    if report.stored:
        return messages.SUCCESS
    return messages.WARNING if report.refused else messages.INFO


def files_stored(count):
    """How many files a batch stored — as a phrase agreeing with the number."""
    if count == 0:
        return "Не сохранено ни одного файла."
    files = agreeing_with(count, "файл", "файла", "файлов")
    loaded = "Загружен" if files == "файл" else "Загружено"
    return f"{loaded} {count}{NBSP}{files}."


#: The word for a picture in each of its three forms — a picture is counted in more than one
#: phrase, and two lists would sooner or later disagree about the middle one.
PICTURES = ("картинка", "картинки", "картинок")


def twin_report(twin):
    """What to say about a близнец that has just been attached — and how loudly.

    Attached is not the same as complete, and one green line for both would hide the
    difference. A close read of the count: «Близнец приложен, 3 картинки» is what a сотрудник
    reconciles against the folder they converted, while an unresolved reference is a finding
    and is said as one — the документ will be read by the модель without that схема, and
    nothing further will report it.
    """
    pictures = twin.images.count()
    attached = f"Близнец приложен, {pictures}{NBSP}{agreeing_with(pictures, *PICTURES)}."
    if not twin.unmatched_images:
        return messages.SUCCESS, attached
    return messages.WARNING, (
        f"{attached} Не разрешились ссылки на картинки: "
        f"{', '.join(twin.unmatched_images)}. Эти изображения ИИ-управляющий не прочтёт."
    )


def twin_removed():
    """What is said when a близнец is taken off.

    The документ is named as untouched out loud: «снят» alone leaves whoever withdrew a bad
    conversion wondering what else went with it, and the answer — nothing — is the reason
    a близнец is a row of its own.
    """
    return "Близнец снят. Документ и его оригинал остались на месте."


def _as_stored(already_stored):
    """A file already on the shelf, named by the document it is stored as.

    The document is named rather than the fact of the match stated: «этот файл уже
    загружен» leaves the reader to find it themselves among hundreds.
    """
    return [(name, f"уже загружен как «{document.title}»") for name, document in already_stored]


def _listed(heading, files):
    """Files by name, each with what is said about it — the list a sender acts on."""
    return f"{heading}: " + "; ".join(f"{name} — {reason}" for name, reason in files) + "."
