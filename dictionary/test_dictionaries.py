"""Три справочника Сторон: банки, сферы деятельности, профессиональные праздники.

What is checked here is the shape of the schema rather than a screen, because at this stage
there is no screen: the справочники are read by the полка Сторон and by the вывод повода,
and both arrive later. The three things worth pinning down before they do are the ones that
would be silently wrong afterwards — a column that promises knowledge the system has no way
of refreshing (ADR 0022), a праздник stored as a date instead of a rule (ADR 0027), and a
rule filled in twice.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from dictionary.models import (
    DictBank,
    DictionaryCommonModel,
    DictLineOfBusiness,
    DictProfessionalHoliday,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def construction(db):
    """Строительство — the отрасль whose праздник ADR 0027 is written about."""
    return DictLineOfBusiness.objects.create(
        slug="construction", name="Строительство", short_name="Строительство"
    )


def test_the_bank_dictionary_carries_nothing_beyond_bik_and_name():
    """`bank.csv` has an `is_license_revocation` column and the справочник does not.

    Said as «the bank is the словарное основание and nothing more», because that is the whole
    decision: BCMP has nowhere to learn that a licence was revoked, and a column it cannot
    refresh would state a year from now that a revoked licence is in force (ADR 0022).
    """
    bank = {field.name for field in DictBank._meta.concrete_fields}
    base = {field.name for field in DictionaryCommonModel._meta.fields}

    assert bank == base | {"id"}


def test_a_bank_is_found_by_its_bik():
    """«Каспи» and «Kaspi Bank» are one bank because the БИК says so, not the spelling."""
    DictBank.objects.create(
        code="CASPKZKA", name='АО "Kaspi Bank"', short_name='АО "Kaspi Bank"'
    )

    assert DictBank.objects.get(code="CASPKZKA").name == 'АО "Kaspi Bank"'


def test_a_holiday_is_expressed_as_a_weekday_of_a_week_of_a_month(construction):
    """«Второе воскресенье августа» — День строителя, and the first of the two forms."""
    holiday = DictProfessionalHoliday.objects.create(
        line_of_business=construction,
        name="День строителя",
        short_name="День строителя",
        month=8,
        week_of_month=DictProfessionalHoliday.WeekOfMonth.SECOND,
        weekday=DictProfessionalHoliday.Weekday.SUNDAY,
    )

    assert (holiday.week_of_month, holiday.weekday, holiday.month) == (2, 7, 8)
    assert holiday.day is None


def test_a_holiday_is_expressed_as_a_day_and_a_month(construction):
    """«Семнадцатое мая» — День работников связи, and the second of the two forms."""
    holiday = DictProfessionalHoliday.objects.create(
        line_of_business=construction,
        name="День работников связи",
        short_name="День связи",
        day=17,
        month=5,
    )

    assert (holiday.day, holiday.month) == (17, 5)
    assert (holiday.week_of_month, holiday.weekday) == (None, None)


def test_the_last_sunday_of_a_month_is_not_the_fourth_one(construction):
    """День шахтёра is «последнее воскресенье августа» and День работников торговли is
    «четвёртое воскресенье июля» — the same calendar tells them apart, so the rule must too:
    a month with five Sundays would otherwise move the shaft workers' day by a week.
    """
    last = DictProfessionalHoliday.WeekOfMonth.LAST
    fourth = DictProfessionalHoliday.WeekOfMonth.FOURTH

    assert last != fourth


def test_both_forms_filled_at_once_are_refused_by_the_database(construction):
    """Two rules on one row is two answers to «когда» — refused where nothing can go round it."""
    with pytest.raises(IntegrityError), transaction.atomic():
        DictProfessionalHoliday.objects.create(
            line_of_business=construction,
            name="День строителя",
            short_name="День строителя",
            day=12,
            month=8,
            week_of_month=DictProfessionalHoliday.WeekOfMonth.SECOND,
            weekday=DictProfessionalHoliday.Weekday.SUNDAY,
        )

    assert not DictProfessionalHoliday.objects.exists()


def test_neither_form_filled_is_refused_by_the_database(construction):
    """A month on its own is not a день in it."""
    with pytest.raises(IntegrityError), transaction.atomic():
        DictProfessionalHoliday.objects.create(
            line_of_business=construction,
            name="День строителя",
            short_name="День строителя",
            month=8,
        )

    assert not DictProfessionalHoliday.objects.exists()


def test_half_of_the_week_form_is_refused_by_the_database(construction):
    """«Второе августа» is not a rule: without a день недели the week says nothing."""
    with pytest.raises(IntegrityError), transaction.atomic():
        DictProfessionalHoliday.objects.create(
            line_of_business=construction,
            name="День строителя",
            short_name="День строителя",
            month=8,
            week_of_month=DictProfessionalHoliday.WeekOfMonth.SECOND,
        )

    assert not DictProfessionalHoliday.objects.exists()


def test_the_refusal_of_two_rules_is_named_on_the_form(construction):
    """The admin gets the reason in words; the constraint is the database's last word, not
    the first thing a человек meets."""
    holiday = DictProfessionalHoliday(
        line_of_business=construction,
        name="День строителя",
        short_name="День строителя",
        day=12,
        month=8,
        week_of_month=DictProfessionalHoliday.WeekOfMonth.SECOND,
        weekday=DictProfessionalHoliday.Weekday.SUNDAY,
    )

    with pytest.raises(ValidationError):
        holiday.full_clean()


def test_none_of_the_three_dictionaries_holds_a_year():
    """A календарь разложенный по годам goes quietly out of date: the first year nobody
    filled in says there are no праздники at all (ADR 0027). The same argument that keeps
    licence revocations out of the bank справочник (ADR 0022).
    """
    for model in (DictBank, DictLineOfBusiness, DictProfessionalHoliday):
        named = {field.name for field in model._meta.concrete_fields}

        assert not [name for name in named if "year" in name or "год" in name]
