"""Что кладут в базу три справочника Сторон и что переживает повторный прогон.

Проверяется поставка, а не модель: формы правила и отказ на двух сразу стоят в
`dictionary/test_dictionaries.py`, здесь — что справочники доезжают, доезжают вместе с
остальными словарями и что второй прогон не стирает заведённого поверх них.
"""

import pytest

from dictionary.models import DictBank, DictLineOfBusiness, DictProfessionalHoliday
from parties.models import Party

from . import load_dict_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def dictionaries():
    """Три справочника, налитые из поставочных файлов."""
    load_dict_data.fill_banks()
    load_dict_data.fill_lines_of_business()
    load_dict_data.fill_professional_holidays()


def test_the_banks_arrive_with_their_bik_and_their_name(dictionaries):
    kaspi = DictBank.objects.get(code="CASPKZKA")

    assert kaspi.name == 'АО "Kaspi Bank"'
    assert DictBank.objects.count() == len(load_dict_data.rows("bank.csv"))


def test_a_bank_that_no_longer_clears_payments_stays_in_the_dictionary(dictionaries):
    """АТФБанк платежи не проводит, но комплект реквизитов, заведённый при нём, его называет:
    вычеркнутый из справочника банк сделал бы позавчерашнюю платёжку нечитаемой."""
    atf = DictBank.objects.get(name='АО "АТФБанк"')

    assert atf.code is None


def test_the_lines_of_business_are_a_list_that_fits_in_one_select(dictionaries):
    """Около двадцати пяти отраслей, а не полторы тысячи позиций ОКЭД (ADR 0024)."""
    assert 20 <= DictLineOfBusiness.objects.count() <= 35
    assert DictLineOfBusiness.objects.filter(name="Строительство").exists()


def test_a_line_of_business_without_a_holiday_is_still_in_the_list(dictionaries):
    """Общепит сидит в БЦ этажами, и своего дня в перечне РК у него нет — сфера деятельности
    без праздника это обычная строка, а не пробел."""
    catering = DictLineOfBusiness.objects.get(slug="catering")

    assert not catering.holidays.exists()


def test_the_shipped_calendar_speaks_both_forms(dictionaries):
    """И «второе воскресенье августа», и «семнадцатое мая» — обе формы в поставке."""
    by_week = DictProfessionalHoliday.objects.filter(week_of_month__isnull=False)
    by_day = DictProfessionalHoliday.objects.filter(day__isnull=False)

    assert by_week.exists()
    assert by_day.exists()
    assert by_week.count() + by_day.count() == DictProfessionalHoliday.objects.count()


def test_the_builders_day_is_the_second_sunday_of_august(dictionaries):
    builders = DictProfessionalHoliday.objects.get(line_of_business__slug="construction")

    assert builders.name == "День строителя"
    assert builders.month == 8
    assert builders.week_of_month == DictProfessionalHoliday.WeekOfMonth.SECOND
    assert builders.weekday == DictProfessionalHoliday.Weekday.SUNDAY


def test_the_miners_day_is_the_last_sunday_and_not_the_fourth_one(dictionaries):
    """Август бывает и о четырёх воскресеньях, и о пяти."""
    miners = DictProfessionalHoliday.objects.get(line_of_business__slug="mining")

    assert miners.week_of_month == DictProfessionalHoliday.WeekOfMonth.LAST


def test_every_holiday_hangs_on_a_line_of_business(dictionaries):
    """Праздник без сферы деятельности некому вывести: он и заведён ради вывода (ADR 0023)."""
    assert not DictProfessionalHoliday.objects.filter(line_of_business__isnull=True).exists()


def test_the_three_dictionaries_load_with_the_rest_of_them(db):
    """«Поставляются с системой» — это один прогон загрузчика словарей, а не отдельный обряд."""
    load_dict_data.run()

    assert DictBank.objects.exists()
    assert DictLineOfBusiness.objects.exists()
    assert DictProfessionalHoliday.objects.exists()


def test_a_second_run_does_not_take_the_line_of_business_off_a_party(dictionaries):
    """Справочники наливаются поверх себя, а не сносятся: 637 Сторон ссылаются на сферы
    деятельности, и прогон, стирающий таблицу, отобрал бы у них сферу молча — вместе с
    выводом повода."""
    construction = DictLineOfBusiness.objects.get(slug="construction")
    party = Party.objects.create(
        kind=Party.Kind.COMPANY,
        name="Центр крепежных систем ТОО",
        bin_iin="060140004821",
        line_of_business=construction,
    )
    before = DictLineOfBusiness.objects.count()

    load_dict_data.fill_lines_of_business()
    load_dict_data.fill_professional_holidays()

    party.refresh_from_db()
    assert party.line_of_business == construction
    assert DictLineOfBusiness.objects.count() == before


def test_the_communications_day_is_the_seventeenth_of_may(dictionaries):
    """«День работников связи и информации» разошёлся в 2019 году на два праздника: связистам
    осталось 17 мая, а 28 июня ушло работникам СМИ. Календарь, списанный со старой
    публикации, поздравил бы связистов чужим днём."""
    communications = DictProfessionalHoliday.objects.get(line_of_business__slug="communications")

    assert communications.name == "День работников связи"
    assert (communications.day, communications.month) == (17, 5)


def test_a_holiday_pointing_at_a_line_of_business_that_is_not_there_is_named(monkeypatch):
    """Молчаливый пропуск читался бы как «у этой сферы праздника нет» — то есть как ответ."""
    monkeypatch.setattr(
        load_dict_data,
        "rows",
        lambda name: [
            {
                "line_of_business": "quarrying",
                "slug": "quarrying_day",
                "name": "День каменотёса",
                "short_name": "День каменотёса",
                "day": "1",
                "month": "5",
                "week_of_month": "",
                "weekday": "",
            }
        ],
    )

    with pytest.raises(KeyError, match="quarrying"):
        load_dict_data.fill_professional_holidays()
