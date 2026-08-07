"""Заглушки в паспортах становятся NULL.

Пять паспортов несут `-1` в общей площади, площади застройки, объёме и числе квартир,
пустую строку в этажности и `1900` в годе постройки — значения, записанные как измерения,
но означающие «данных нет». Чистка идёт в базе, а не в шаблонах: спрятать заглушку при
отрисовке — значит оставить её всем, кто читает данные дальше, включая ИИ-управляющего.

Список полей — ровно тот, что перечислен в тикете. `living_area`, `balcony_loggia_area`,
`non_residential_area` и `total_rooms` тоже несут `-1`, но в перечень не входят и здесь
не трогаются.
"""

from decimal import Decimal

from django.db import migrations

PLACEHOLDER_MEASUREMENT = Decimal(-1)
PLACEHOLDER_COUNT = -1
PLACEHOLDER_YEAR = 1900

# Поле → значение, которым в нём записано отсутствие данных.
PLACEHOLDERS = {
    "total_area": PLACEHOLDER_MEASUREMENT,
    "building_footprint": PLACEHOLDER_MEASUREMENT,
    "building_volume": PLACEHOLDER_MEASUREMENT,
    "number_of_floors": "",
    "apartments_number": PLACEHOLDER_COUNT,
}


def clear_placeholders(apps, schema_editor):
    BuildingPassport = apps.get_model("building_passport", "BuildingPassport")

    # Год снимается только там, где общая площадь тоже заглушка, и обязательно до того,
    # как та станет NULL. Безусловное правило стёрло бы 1900 у действительно старого
    # здания на любом следующем прогоне.
    BuildingPassport.objects.filter(
        total_area=PLACEHOLDER_MEASUREMENT, year_built=PLACEHOLDER_YEAR
    ).update(year_built=None)

    for field, placeholder in PLACEHOLDERS.items():
        BuildingPassport.objects.filter(**{field: placeholder}).update(**{field: None})


def keep_placeholders_cleared(apps, schema_editor):
    """Откат оставляет NULL на месте.

    Вернуть `-1` можно было бы только всем пустым полям сразу — отличить снятую заглушку
    от поля, которое никто не заполнял, нечем. Заглушка не была данными, и восстанавливать
    её означало бы придумать измерение заново.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("building_passport", "0014_alter_buildingpassport_balcony_loggia_area_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_placeholders, keep_placeholders_cleared),
    ]
