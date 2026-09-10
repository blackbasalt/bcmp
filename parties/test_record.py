"""Учётная карточка: пара «Сторона + организация» и привратник изоляции.

The seam is the model layer, as it was for `Space.objects.visible_to` when the паспорт had
no screens yet (`building_passport/test_scoping.py`): полка Сторон and экран Стороны arrived
in the tickets after this one, and what those two read is checked at their own HTTP boundary,
in `test_shelf.py` and `test_page.py`. The second seam is the Django admin, where платёжные
реквизиты and контактные лица are maintained meanwhile — the same place an аренда was
entered from before the карточка помещения carried a form.

What is pinned down here is what would be silently wrong on the screens above: a second карточка on one pair, a день рождения that reaches the second
управляющая компания (ADR 0023), the телефоны Стороны kept in two places at once, and a
привратник that lets a reader of one client see another's.

Удаление Стороны is not among them: the application does not offer it at all (ADR 0028), and
what a model can say about that is checked here — the карточка goes with everything hanging
off it, and the Сторона stays.
"""

from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.urls import reverse

from parties.models import ContactPerson, Party, PartyRecord, PaymentDetails

pytestmark = pytest.mark.django_db


@pytest.fixture
def our_record(downtown, alpha):
    """Карточка ТОО «Альфа», заведённая DownTown Management, — на ней висит всё остальное."""
    return PartyRecord.objects.create(party=alpha, org=downtown)


def test_a_record_is_the_pair_of_a_party_and_an_organisation(downtown, alpha):
    """Карточка и есть пара: всё, что организация знает о Стороне, висит на ней."""
    record = PartyRecord.objects.create(party=alpha, org=downtown)

    assert (record.party, record.org) == (alpha, downtown)
    assert list(alpha.records.all()) == [record]


def test_a_second_record_on_the_same_pair_is_refused(downtown, alpha):
    """Иначе у одной пары два ответа на вопрос «что мы о ней знаем», и второй прочитают."""
    PartyRecord.objects.create(party=alpha, org=downtown)

    with pytest.raises(IntegrityError), transaction.atomic():
        PartyRecord.objects.create(party=alpha, org=downtown)


def test_two_organisations_keep_their_own_record_of_one_party(downtown, central, alpha):
    """Kaspi Bank поставляет двум управляющим компаниям сразу, и это одна Сторона (ADR 0020)."""
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    theirs = PartyRecord.objects.create(party=alpha, org=central)

    assert set(alpha.records.all()) == {ours, theirs}


def test_a_contact_person_lives_in_the_record_and_not_on_the_party(our_record, central, alpha):
    """Телефон директора, записанный одной УК, второй, знакомой с тем же ТОО, не показывают."""
    theirs = PartyRecord.objects.create(party=alpha, org=central)
    contact = ContactPerson.objects.create(
        record=our_record,
        full_name="Сергеев Пётр Иванович",
        position="главный инженер",
        phone="+7 701 000 00 00",
    )

    assert list(our_record.contacts.all()) == [contact]
    assert list(theirs.contacts.all()) == []


def test_a_contact_person_is_not_a_party(our_record):
    """Директор не встаёт в один список со своим же ТОО и БИН у него не спрашивают."""
    before = set(Party.objects.values_list("pk", flat=True))

    ContactPerson.objects.create(record=our_record, full_name="Сергеев Пётр Иванович")

    assert set(Party.objects.values_list("pk", flat=True)) == before


def test_the_birthday_of_a_person_is_held_on_the_record_and_not_on_the_party(
    downtown, central, petrov
):
    """У физлица контактных лиц нет, и личный повод висит на самой карточке (ADR 0025).

    На Стороне он лежать не может: дата рождения есть персональные данные, и второй
    управляющей компании, знакомой с тем же человеком, их не показывают (ADR 0023).
    """
    ours = PartyRecord.objects.create(party=petrov, org=downtown, born_on=date(1977, 1, 1))
    theirs = PartyRecord.objects.create(party=petrov, org=central)

    assert (ours.born_on, theirs.born_on) == (date(1977, 1, 1), None)
    assert not hasattr(petrov, "born_on")


def test_several_sets_of_payment_details_live_on_one_record_with_the_primary_first(
    our_record, kaspi
):
    """Счёт в тенге и счёт в валюте живут вместе, и экран знает, что показать одной строкой."""
    PaymentDetails.objects.create(
        record=our_record, bank=kaspi, account="KZ11 0000 0000 0000 0002", kbe="17"
    )
    primary = PaymentDetails.objects.create(
        record=our_record, bank=kaspi, account="KZ11 0000 0000 0000 0001", kbe="17", is_primary=True
    )

    assert our_record.payment_details.first() == primary
    assert our_record.payment_details.count() == 2


def test_a_bank_is_not_erased_from_under_a_set_of_payment_details(our_record, kaspi):
    """Вычеркнутый из справочника банк сделал бы позавчерашнюю платёжку нечитаемой."""
    PaymentDetails.objects.create(record=our_record, bank=kaspi, account="KZ11", kbe="17")

    with pytest.raises(ProtectedError), transaction.atomic():
        kaspi.delete()


def test_deleting_the_record_takes_its_contacts_and_payment_details_with_it(our_record, kaspi):
    """Карточка уходит целиком: то, что о Стороне знали, знанием ничьим не остаётся (ADR 0028)."""
    ContactPerson.objects.create(record=our_record, full_name="Сергеев Пётр Иванович")
    PaymentDetails.objects.create(record=our_record, bank=kaspi, account="KZ11", kbe="17")

    our_record.delete()

    assert ContactPerson.objects.count() == 0
    assert PaymentDetails.objects.count() == 0


def test_deleting_the_record_leaves_the_party(our_record, alpha, central):
    """Освобождённый БИН завели бы заново и получили юрлицо без прошлого (ADR 0028)."""
    theirs = PartyRecord.objects.create(party=alpha, org=central)

    our_record.delete()

    assert Party.objects.filter(pk=alpha.pk).exists()
    assert list(alpha.records.all()) == [theirs]


# Привратник изоляции


def test_a_member_sees_the_records_of_their_organisation_only(downtown, central, alpha, member):
    """Тот же привратник, что у помещений и документов, — первый и единственный отбор."""
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    PartyRecord.objects.create(party=alpha, org=central)

    assert list(PartyRecord.objects.visible_to(member)) == [ours]


def test_the_party_is_shared_and_the_knowledge_about_it_is_not(
    downtown, central, alpha, member, kaspi
):
    """Одна Сторона на двух полках, и на каждой — только свой телефон и свой счёт (ADR 0020)."""
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    theirs = PartyRecord.objects.create(party=alpha, org=central)
    ContactPerson.objects.create(record=theirs, full_name="Сергеев Пётр Иванович")
    PaymentDetails.objects.create(record=theirs, bank=kaspi, account="KZ11", kbe="17")

    visible = PartyRecord.objects.visible_to(member)

    assert [record.party for record in visible] == [alpha]
    assert list(visible) == [ours]
    assert ContactPerson.objects.filter(record__in=visible).count() == 0
    assert PaymentDetails.objects.filter(record__in=visible).count() == 0


def test_a_superuser_sees_every_organisation(downtown, central, alpha, django_user_model):
    """Разработчик воспроизводит проблему клиента, не выписывая себе членство."""
    developer = django_user_model.objects.create_superuser("developer")
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    theirs = PartyRecord.objects.create(party=alpha, org=central)

    assert set(PartyRecord.objects.visible_to(developer)) == {ours, theirs}


def test_a_user_without_membership_sees_nothing_rather_than_everything(
    downtown, alpha, django_user_model
):
    """«Нет членства — видно всё» и есть та утечка, ради которой привратник стоит."""
    newcomer = django_user_model.objects.create_user("newcomer")
    PartyRecord.objects.create(party=alpha, org=downtown)

    assert list(PartyRecord.objects.visible_to(newcomer)) == []


def test_an_anonymous_visitor_sees_nothing(downtown, alpha):
    PartyRecord.objects.create(party=alpha, org=downtown)

    assert list(PartyRecord.objects.visible_to(AnonymousUser())) == []


def test_a_member_of_two_organisations_sees_both_shelves(downtown, central, alpha, both_clients):
    """Сотрудник, ведущий двух клиентов, видит обе карточки — и знает, чья каждая."""
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    theirs = PartyRecord.objects.create(party=alpha, org=central)

    assert set(PartyRecord.objects.visible_to(both_clients)) == {ours, theirs}


def test_a_reader_administers_nothing_without_the_flag(downtown, alpha, member):
    """Читать данные организации и вести их — разные права (ADR 0005)."""
    PartyRecord.objects.create(party=alpha, org=downtown)

    assert list(PartyRecord.objects.visible_to(member)) != []
    assert list(PartyRecord.objects.administered_by(member)) == []


def test_an_administrator_maintains_the_records_of_their_organisation_only(
    downtown, central, alpha, administrator
):
    """Флаг стоит на паре «сотрудник + организация»: у второго клиента он ведёт ту же карточку
    ровно постольку, поскольку и там администратор."""
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    PartyRecord.objects.create(party=alpha, org=central)

    assert list(PartyRecord.objects.administered_by(administrator)) == [ours]


def test_a_superuser_maintains_everything(downtown, central, alpha, django_user_model):
    """Тем же доводом, что в `OrgQuerySet`: он и так пишет через админку."""
    developer = django_user_model.objects.create_superuser("developer")
    ours = PartyRecord.objects.create(party=alpha, org=downtown)
    theirs = PartyRecord.objects.create(party=alpha, org=central)

    assert set(PartyRecord.objects.administered_by(developer)) == {ours, theirs}


def test_an_anonymous_visitor_maintains_nothing(downtown, alpha):
    """Спрошено отдельно от `visible_to`: аноним доходит сюда без членств, по которым
    отбирать, и ответ «ничего» стоит на `OrgQuerySet`, а не на этой строке."""
    PartyRecord.objects.create(party=alpha, org=downtown)

    assert list(PartyRecord.objects.administered_by(AnonymousUser())) == []


def test_revoking_membership_hides_the_organisation_again(downtown, alpha, member):
    PartyRecord.objects.create(party=alpha, org=downtown)

    member.memberships.get().delete()

    assert list(PartyRecord.objects.visible_to(member)) == []


# Что расщепление меняет на самой Стороне


def test_the_party_no_longer_carries_a_contacts_field():
    """`Party.contacts` — пустой JSONField во всех 699 строках, и снесён он не за пустоту.

    Оставленный рядом с `ContactPerson`, он собрал бы вторую копию телефонов: часть завели бы
    сюда, часть туда, и «кому звонить» получило бы два ответа — та самая вторая правда, от
    которой проект отказывается в близнеце, в ставке и в самом расщеплении (ADR 0020).
    """
    assert "contacts" not in {field.name for field in Party._meta.concrete_fields}


def test_the_party_keeps_its_kind(alpha, petrov):
    """`kind`, в отличие от `contacts`, не пуст — его просто никогда не спрашивали.

    Этот экран спрашивает: от рода зависит, есть ли блок контактных лиц и где висит день
    рождения (ADR 0025).
    """
    assert (alpha.kind, petrov.kind) == (Party.Kind.COMPANY, Party.Kind.PERSON)


# Ведение в админке — покуда экрана Стороны нет


def record_form(party, org, **fields):
    """Форма карточки с двумя вложенными наборами — контактных лиц и платёжных реквизитов.

    Наборы объявлены пустыми, а строку в них дописывает тест: сама по себе карточка — это
    пара, и большинство вопросов к ней о том, что на ней висит, а не о ней самой.
    """
    return {
        "party": str(party.pk),
        "org": str(org.pk),
        "born_on": "",
        "contacts-TOTAL_FORMS": "0",
        "contacts-INITIAL_FORMS": "0",
        "payment_details-TOTAL_FORMS": "0",
        "payment_details-INITIAL_FORMS": "0",
        **fields,
    }


def test_a_record_is_maintained_in_django_admin(admin_client, downtown, alpha, kaspi):
    """Пока экрана Стороны нет, контактное лицо и счёт заводят здесь — и на одной странице.

    Вложенными наборами, а не тремя отдельными разделами: и то и другое существует только
    внутри карточки, и заводить их порознь значило бы сперва отыскать карточку в списке из
    637 строк.
    """
    response = admin_client.post(
        reverse("admin:parties_partyrecord_add"),
        record_form(
            alpha,
            downtown,
            **{
                "contacts-TOTAL_FORMS": "1",
                "contacts-0-full_name": "Сергеев Пётр Иванович",
                "contacts-0-position": "главный инженер",
                "contacts-0-phone": "+7 701 000 00 00",
                "contacts-0-email": "",
                "contacts-0-born_on": "1980-03-12",
                "payment_details-TOTAL_FORMS": "1",
                "payment_details-0-bank": str(kaspi.pk),
                "payment_details-0-account": "KZ11 0000 0000 0000 0001",
                "payment_details-0-kbe": "17",
                "payment_details-0-is_primary": "on",
            },
        ),
    )

    assert response.status_code == 302
    record = PartyRecord.objects.get()
    assert (record.party, record.org) == (alpha, downtown)
    assert record.contacts.get().born_on == date(1980, 3, 12)
    assert record.payment_details.get().is_primary


def test_the_admin_refuses_a_second_record_on_the_same_pair(admin_client, downtown, alpha):
    """Отказ называется на форме словами, а не прилетает пятисоткой из базы."""
    PartyRecord.objects.create(party=alpha, org=downtown)

    response = admin_client.post(
        reverse("admin:parties_partyrecord_add"), record_form(alpha, downtown)
    )

    assert response.status_code == 200
    assert PartyRecord.objects.count() == 1

