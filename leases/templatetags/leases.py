"""Фильтры шаблонов над правилами показа договора.

Здесь только регистрация: сами правила лежат в `lease_display`, потому что ими
пользуется не одна разметка — сроком договора называется и отказ модели.
"""

from django import template

from ..lease_display import period, spaces_counted

register = template.Library()

register.filter(period)
register.filter(spaces_counted)
