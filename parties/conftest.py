"""What the полка Сторон's tests are staged on.

The root `conftest` holds the organisations, the employees and the Стороны that sit in
помещения — ТОО «Альфа» and ИП Петров are the pair every screen of this stage is read
through, and there must not be two definitions of either. What stands here belongs to the
раздел «Стороны» alone: the учётная карточка that puts a Сторона on the полка at all, and
the сфера деятельности a row names.
"""

import pytest

from dictionary.models import DictBank, DictLineOfBusiness, DictProfessionalHoliday
from parties.models import ContactPerson, Party, PartyRecord


@pytest.fixture
def make_record(db):
    """The учётная карточка that puts a Сторона on an organisation's полка.

    A factory rather than a ready-made карточка: the полка is a полка карточек, and what
    almost every test here stages is which pair «Сторона + организация» exists and which
    does not.
    """

    def _make_record(org, party, **fields):
        return PartyRecord.objects.create(party=party, org=org, **fields)

    return _make_record


@pytest.fixture
def make_party(db):
    """A Сторона of the registry — with or without anybody's карточка on her.

    The 62 Стороны loaded from other bases are exactly this: rows of the registry that no
    организация knows, and the полка has to keep them off itself.
    """

    def _make_party(name, bin_iin, kind=Party.Kind.COMPANY, **fields):
        return Party.objects.create(kind=kind, name=name, bin_iin=bin_iin, **fields)

    return _make_party


@pytest.fixture
def construction(db):
    """A сфера деятельности — the one «все наши строители» is asked by."""
    return DictLineOfBusiness.objects.create(name="Строительство", short_name="Строительство")


@pytest.fixture
def catering(db):
    """A second сфера, so that narrowing by one is telling it from another.

    Общепит and not a second building trade: the отбор is checked by what it leaves off the
    полка, and two сферы a reader could confuse would make a passing test out of a condition
    that answers with everybody who has any сфера at all.
    """
    return DictLineOfBusiness.objects.create(name="Общепит", short_name="Общепит")


@pytest.fixture
def make_contact(db):
    """A контактное лицо on a учётная карточка — the person whose день рождения is a повод.

    A factory rather than a ready-made человек: what almost every occasion test stages is
    whose карточка the birthday hangs on and what day of the year it falls on, and both
    change from test to test.
    """

    def _make_contact(record, full_name, **fields):
        return ContactPerson.objects.create(record=record, full_name=full_name, **fields)

    return _make_contact


@pytest.fixture
def make_holiday(db):
    """A профессиональный праздник in the справочник — a rule and not a date (ADR 0027).

    Either form is staged through the same factory, because the справочник holds them in one
    row: `day` and `month`, or `week_of_month`, `weekday` and `month`. Which of the two a
    test means is said by the keywords it passes, exactly as the `CheckConstraint` reads it.
    """

    def _make_holiday(line_of_business, name, **rule):
        return DictProfessionalHoliday.objects.create(
            line_of_business=line_of_business, name=name, short_name=name, **rule
        )

    return _make_holiday


@pytest.fixture
def kaspi(db):
    """Банк, в котором лежит счёт, — из справочника, чтобы «Каспи» и «Kaspi Bank» были одним.

    Стоит здесь, а не у одного из тестов: комплект платёжных реквизитов заводят и модельные
    тесты карточки, и экран Стороны, который его печатает, и второе определение того же
    банка развело бы БИК на экране с БИК в базе.
    """
    return DictBank.objects.create(
        code="CASPKZKA", name='АО "Kaspi Bank"', short_name="Kaspi Bank"
    )


@pytest.fixture
def our_record(downtown, alpha, make_record):
    """Карточка ТОО «Альфа» у DownTown Management — та, о которой читают и которую ведут.

    Стоит здесь, а не у одного из тестов: экран Стороны читают одни тесты, а створки на нём
    отправляют другие, и второе определение той же карточки развело бы прочитанное с
    заведённым.
    """
    return make_record(downtown, alpha)


@pytest.fixture
def halyk(db):
    """Второй банк — тот, при котором счёт открывают, закрывая счёт в первом.

    Два банка, а не один: комплект, заведённый рядом с прежним, проверяется тем, что от
    прежнего отличается, и два счёта в одном банке оставили бы «банк не затёрся» утверждением
    ни о чём.
    """
    return DictBank.objects.create(
        code="HSBKKZKX", name='АО "Народный Банк Казахстана"', short_name="Halyk"
    )
