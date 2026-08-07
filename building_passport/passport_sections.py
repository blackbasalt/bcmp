"""Паспорт здания, разложенный по разделам экрана.

Разделы собираются здесь, а не в шаблоне: «пустое поле показать, пустой раздел
скрыть» — правило про данные, а не про вёрстку, и проверять его в разметке дороже,
чем в одном месте. Шаблон получает готовый список и только печатает его.

Порядок полей внутри раздела — порядок, в котором их спрашивают: раздел отвечает
на один вопрос о здании целиком, поэтому поля не пересортировываются по алфавиту.
"""

from dataclasses import dataclass
from typing import Any

from .passport_display import area, is_missing, volume


@dataclass(frozen=True)
class Field:
    """Строка раздела. Пустое значение остаётся None — прочерк ставит `or_missing`."""

    label: str
    value: Any


@dataclass(frozen=True)
class Section:
    title: str
    fields: tuple[Field, ...]

    @property
    def is_empty(self) -> bool:
        """Признак пустоты тот же, по которому поле получает прочерк."""
        return all(is_missing(field.value) for field in self.fields)


def _name(party) -> str | None:
    """Сторона на экране — имя: идентификатору стороны позвонить нельзя."""
    return party.name if party is not None else None


def sections(passport) -> list[Section]:
    """Разделы паспорта, готовые к печати: непустые, в порядке чтения экрана.

    Жилые поля (количество квартир, жилая площадь, число комнат) в разделы не
    попадают: столбцы в базе остаются, но коммерческий паспорт ими не разбавляется.
    """
    if passport is None:
        return []

    all_sections = [
        # Вместе — чтобы здание можно было сличить с внешним реестром.
        Section(
            "Идентификация",
            (
                Field("Адрес", passport.address),
                Field("Кадастровый номер", passport.cadastral_no),
                Field("Инвентарный номер", passport.inventory_number),
                Field("Назначение", passport.intended_purpose),
            ),
        ),
        # Вместе — чтобы ответить арендатору и оценщику, не открывая ничего ещё.
        Section(
            "Характеристики",
            (
                Field("Общая площадь", area(passport.total_area)),
                Field("Площадь застройки", area(passport.building_footprint)),
                Field("Нежилая площадь", area(passport.non_residential_area)),
                # Этажность печатается как записана: «4+тех.этаж» числом не бывает.
                Field("Этажность", passport.number_of_floors),
                Field("Строительный объём", volume(passport.building_volume)),
                Field("Год постройки", passport.year_built),
                Field("Класс здания", passport.get_building_class_display()),
            ),
        ),
        # Вместе — чтобы инженер УК сверил здание с нормой, не поднимая бумажный паспорт.
        Section(
            "Конструктив и безопасность",
            (
                Field("Материал стен", passport.wall_material),
                Field("Конструктивная схема", passport.structural_scheme),
                Field("Степень огнестойкости", passport.fire_resistance_degree),
                Field("Класс функциональной пожарной опасности", passport.functional_fire_class),
                Field("Класс конструктивной пожарной опасности", passport.structural_fire_class),
                Field("Расчётная сейсмичность, баллы", passport.seismic_points),
                Field("Энергокласс", passport.energy_class),
            ),
        ),
        # Вместе — чтобы было понятно, кому звонить об этом здании.
        Section(
            "Стороны",
            (
                Field("Собственник", _name(passport.owner_party)),
                Field("Управляющая компания", _name(passport.operator_party)),
                Field("Проектировщик", _name(passport.designer_party)),
                Field("Подрядчик", _name(passport.builder_party)),
            ),
        ),
    ]
    return [section for section in all_sections if not section.is_empty]
