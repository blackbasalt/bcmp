"""Как паспорт здания читается на экране.

Отсутствующее значение пишется «— нет данных» — одним и тем же способом везде, где
поле паспорта пусто: пустое место на карточке можно прочитать как ноль, а прочерк
нельзя. Карточка БЦ пользуется этим же фильтром, а не заводит свой.
"""

from django import template

register = template.Library()

NO_DATA = "— нет данных"

#: Неразрывный пробел: «2 484 м²» не должно переноситься между строк.
NBSP = " "


@register.filter
def or_missing(value):
    """Пустое значение паспорта — «— нет данных»."""
    if value is None or value == "":
        return NO_DATA
    return value


@register.filter
def area(value):
    """Площадь в м² как она записана в паспорте — до сотых, без округления.

    Отсутствующая площадь остаётся None: её оформит `or_missing`.
    """
    if value is None or value == "":
        return None
    return f"{value:,.2f}{NBSP}м²".replace(",", NBSP).replace(".", ",")
