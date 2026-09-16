"""Фильтры разметки над правилами написания полки договоров.

Сами правила лежат в `contract_display`, потому что читает их не одна разметка: тем же
словом «бессрочный» будет названа шапка экрана договора, а «срок не заведён» стоит ещё и
находкой на строке счёта. То же устройство, что у `passport`, `documents`, `rooms` и
`parties`.
"""

from django import template

from ..contract_display import counterparty_said, ending_said, kind_said

register = template.Library()


@register.filter
def kind(contract):
    """Вид договора, как его называет строка полки."""
    return kind_said(contract)


@register.filter
def counterparty(contract):
    """Контрагент договора — вторая сторона, а не «кем выдан»."""
    return counterparty_said(contract)


@register.filter
def ending(contract):
    """Что строка говорит под «Кончается» — одно из трёх состояний и приписка к нему."""
    return ending_said(contract)
