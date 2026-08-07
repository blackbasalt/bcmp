"""Заглушки в нежилой площади и числе комнат становятся NULL.

Перечень полей в тикете #4 закрытый, и `0015` его не превышала. Но `-1` остался ещё в
четырёх столбцах, и два из них — `non_residential_area` и `total_rooms` — не жилые:
оговорка «прячем при отрисовке», которая покрывает жилую площадь и балконы, на них не
распространяется, и сотрудник УК увидел бы `-1 м²` и `-1` на экране. Ровно то, ради чего
`0015` и писалась.

Отдельная миграция, а не правка `0015`: та уже применена.

`living_area` и `balcony_loggia_area` намеренно не трогаются — жилая недвижимость вне
контекста (CONTEXT.md, §Язык), эти поля прячет Карточка БЦ.
"""

from decimal import Decimal

from django.db import migrations

# Поле → значение, которым в нём записано отсутствие данных.
PLACEHOLDERS = {
    "non_residential_area": Decimal(-1),
    "total_rooms": -1,
}


def clear_remaining_placeholders(apps, schema_editor):
    BuildingPassport = apps.get_model("building_passport", "BuildingPassport")

    for field, placeholder in PLACEHOLDERS.items():
        BuildingPassport.objects.filter(**{field: placeholder}).update(**{field: None})


def keep_placeholders_cleared(apps, schema_editor):
    """Откат оставляет NULL на месте — как и в `0015`.

    Отличить снятую заглушку от поля, которое никто не заполнял, нечем; заглушка не была
    данными, и восстанавливать её означало бы придумать измерение заново.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("building_passport", "0015_clear_passport_placeholders"),
    ]

    operations = [
        migrations.RunPython(clear_remaining_placeholders, keep_placeholders_cleared),
    ]
