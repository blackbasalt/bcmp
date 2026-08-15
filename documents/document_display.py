"""How the documents section reads on screen.

There is one rule here — the count of what is shown. The number is said as a phrase rather
than a figure beside the table: «Показано 12 документов» answers a question, while «12»
next to a table is a quantity the reader has to guess at. The same device as «нанесено 47
из 82 помещений» on a floor.

Agreement with the numeral is worked out here rather than assembled in the markup:
«Показано 1 документов» reads as a glitch on the screen, not as a single document, and it
is a place, not a template, that should sort this out.
"""

#: A non-breaking space: a number and the word attached to it must not drift apart across
#: lines — the same rule as for the areas in the building passport.
NBSP = "\u00a0"


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
