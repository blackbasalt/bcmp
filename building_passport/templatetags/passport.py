"""Фильтры шаблонов над правилами показа паспорта.

Здесь только регистрация: сами правила лежат в `passport_display`, потому что ими
пользуется не одна разметка. Регистрируется то, что вызывается из шаблона, — величины,
которые собираются в Python, приходят на экран уже оформленными.
"""

from django import template

from ..passport_display import area, figure, or_missing, space_label

register = template.Library()

register.filter(or_missing)
register.filter(area)
register.filter(figure)
register.filter(space_label)
