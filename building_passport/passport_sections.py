"""The building passport laid out in the sections of the screen.

The sections are assembled here rather than in the template: "show an empty field, hide
an empty section" is a rule about the data, not about the layout, and checking it in
markup costs more than checking it in one place. The template receives a ready list and
only prints it.

The order of the fields inside a section is the order in which they are asked: a
section answers one question about the building as a whole, so the fields are not
re-sorted alphabetically.
"""

from dataclasses import dataclass
from typing import Any

from .passport_display import area, is_missing, volume


@dataclass(frozen=True)
class Field:
    """A row of a section. An empty value stays None — the dash is put in by `or_missing`."""

    label: str
    value: Any


@dataclass(frozen=True)
class Section:
    title: str
    fields: tuple[Field, ...]

    @property
    def is_empty(self) -> bool:
        """Emptiness is judged by the same test that gives a field its dash."""
        return all(is_missing(field.value) for field in self.fields)


def _name(party) -> str | None:
    """A party on the screen is a name: you cannot call a party's identifier."""
    return party.name if party is not None else None


def sections(passport) -> list[Section]:
    """The sections of a passport, ready to print: non-empty, in the reading order of the screen.

    Residential fields (number of apartments, living area, number of rooms) do not make
    it into the sections: the columns stay in the database, but a commercial passport is
    not padded out with them.
    """
    if passport is None:
        return []

    all_sections = [
        # Together, so the building can be matched against an external registry.
        Section(
            "Идентификация",
            (
                Field("Адрес", passport.address),
                Field("Кадастровый номер", passport.cadastral_no),
                Field("Инвентарный номер", passport.inventory_number),
                Field("Назначение", passport.intended_purpose),
            ),
        ),
        # Together, so a tenant or a valuer can be answered without opening anything else.
        Section(
            "Характеристики",
            (
                Field("Общая площадь", area(passport.total_area)),
                Field("Площадь застройки", area(passport.building_footprint)),
                Field("Нежилая площадь", area(passport.non_residential_area)),
                # The floor count is printed as recorded: "4+тех.этаж" is never a number.
                Field("Этажность", passport.number_of_floors),
                Field("Строительный объём", volume(passport.building_volume)),
                Field("Год постройки", passport.year_built),
                Field("Класс здания", passport.get_building_class_display()),
            ),
        ),
        # Together, so an engineer can check the building against the norms without
        # digging out the paper passport.
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
        # Together, so it is clear whom to call about this building.
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
