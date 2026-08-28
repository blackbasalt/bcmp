"""The one rule every период in this project keeps, whatever the период belongs to.

A период is a pair of dates with both ends included, an empty end reading «по сей день»
(ADR 0004). What is checked here is the only thing that is wrong about a период no matter
what carries it: an end before the beginning. Everything else — plans of one floor not
overlapping, аренды of one помещение overlapping freely — is a rule about the thing, not
about the период, and stays with the thing.

It stands in a module of its own, read by the план and by the аренда, for the same reason
вид помещения stands in `space_kind`: one rule handed out in one shape. Two copies would be
two wordings of one refusal, and the second to be reworded would be the one nobody was
reading.
"""

from django.core.exceptions import ValidationError


def refuse_a_period_that_ends_before_it_begins(valid_from, valid_to):
    """A период that ends before it begins is a typo in a date, caught where it is made.

    The refusal is named on «по»: of the two dates that is the one just typed, and the one
    a form should put the message next to.

    An unset end is not a mistake but a период that has not finished, and an unset
    beginning is a form not filled in yet — both leave nothing to compare, and both are
    somebody else's refusal.
    """
    if valid_from is None or valid_to is None:
        return
    if valid_to < valid_from:
        raise ValidationError({"valid_to": "Период заканчивается раньше, чем начинается."})
