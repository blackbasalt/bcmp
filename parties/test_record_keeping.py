"""Ведение учётной карточки — что видно на границе HTTP, когда её заполняют.

Шов тот же, что и у остального раздела: тесты отправляют створку экрана Стороны тестовым
клиентом от имени сотрудника с известным членством и проверяют наблюдаемое — что появилось
на перезагруженном экране, что осталось в базе после отказа и каким кодом ответил запрос.
Ниже HTTP шва нет: и право на запись, и то, что у физлица контактных лиц не бывает, читаются
ровно так, как их читает администратор.

Опора в разметке — атрибут `data-entry` на складке створки, тот же и на том же элементе, каким
читается створка заведения на полке: он называет, что предложено завести, и сотруднику без
флага администратора не достаётся вовсе.
"""

import re
from datetime import date

import pytest
from django.urls import reverse

from parties.models import ContactPerson, PaymentDetails

from .test_page import fields_on, rows_in, screen, sections_on
from .test_shelf import parties_on, shelf

pytestmark = pytest.mark.django_db

#: Одна створка экрана, по имени, которым она названа: разметка складки целиком.
#:
#: По элементу `<details>` и его `data-entry`, ровно как читается створка заведения Стороны
#: на полке: один атрибут — один договор, и прочитанный на этом экране с другого элемента, он
#: был бы вторым его изложением.
ENTRY = re.compile(
    r'<details[^>]*data-entry="(?P<name>[^"]+)"[^>]*>(?P<body>.*?)</details>', re.DOTALL
)


def entries_on(page):
    """Створки экрана по именам: что на нём предложено завести и чем."""
    return {entry["name"]: entry["body"] for entry in ENTRY.finditer(page)}


def entry_fields(page, entry):
    """Имена полей, о которых спрашивает одна створка, — то, что уедет в её отправке."""
    return set(
        re.findall(r'<(?:input|select)[^>]*\bname="([^"]+)"', entries_on(page)[entry])
    )


def keep(client, record, follow=False, **fields):
    """Отправить створку по адресу самой карточки — тому же, по которому её читают."""
    return client.post(
        reverse("parties:party_detail", args=[record.pk]), fields, follow=follow
    )


def pay_to(client, record, account="KZ111111111111111111", **fields):
    """Завести комплект платёжных реквизитов: банк, счёт и то, что при них."""
    return keep(client, record, account=account, **fields)


# Платёжные реквизиты


def test_a_set_of_payment_details_is_entered_on_the_record(
    client, administrator, our_record, kaspi
):
    """Куда платить, ведёт сама организация: счета меняются чаще, чем звонят в поддержку."""
    client.force_login(administrator)

    response = pay_to(client, our_record, bank=kaspi.pk, kbe="17", follow=True)

    entered = PaymentDetails.objects.get(record=our_record)
    assert entered.bank == kaspi
    assert entered.account == "KZ111111111111111111"
    assert entered.kbe == "17"
    # Заведённое видно на экране сразу: перезагруженный экран и есть подтверждение.
    entered_row = rows_in(response.content.decode(), "payment", "data-payment")[0]
    assert "KZ111111111111111111" in entered_row


def test_the_entry_of_payment_details_is_offered_to_an_administrator(
    client, administrator, our_record
):
    """Ведёт карточку тот, кто вправе вести данные организации, — и створка стоит у него."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert "payment" in entries_on(page)


def test_a_reader_is_offered_no_forms_at_all(client, member, our_record):
    """Показанная форма, отклоняющая отправку, читается как сломанный экран (ADR 0005)."""
    client.force_login(member)

    _, page = screen(client, our_record)

    assert entries_on(page) == {}


def test_the_set_of_payment_details_asks_for_the_bank_the_account_and_the_kbe(
    client, administrator, our_record, kaspi
):
    """Куда платить: банк из справочника, счёт и КБе — и ни слова о лицензии (ADR 0022)."""
    client.force_login(administrator)

    _, page = screen(client, our_record)
    entry = entries_on(page)["payment"]

    assert entry_fields(page, "payment") >= {"bank", "account", "kbe"}
    assert "Kaspi Bank" in entry
    # По БИК: «Каспи» и «Kaspi Bank» одним банком делает он, а не написание названия.
    assert "CASPKZKA" in entry
    assert "лицензи" not in entry.lower()


def test_the_empty_block_does_not_send_the_administrator_to_an_administrator(
    client, administrator, our_record
):
    """«Их заводит администратор организации» — читателю, а не тому, у кого стоит створка."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert "не заведены" in sections_on(page)["payment"]
    assert "администратор" not in sections_on(page)["payment"]
    assert "администратор" not in sections_on(page)["contacts"]


def test_several_sets_of_payment_details_live_on_one_record(
    client, administrator, our_record, kaspi
):
    """Счёт в тенге и счёт в валюте живут вместе — комплектов на карточке сколько угодно."""
    client.force_login(administrator)

    pay_to(client, our_record, account="KZ111111111111111111", bank=kaspi.pk)
    response = pay_to(
        client, our_record, account="KZ999999999999999999", bank=kaspi.pk, follow=True
    )

    accounts = " ".join(rows_in(response.content.decode(), "payment", "data-payment"))
    assert "KZ111111111111111111" in accounts
    assert "KZ999999999999999999" in accounts


def test_a_new_set_does_not_overwrite_the_one_entered_before_it(
    client, administrator, our_record, kaspi, halyk
):
    """Платёжка, выписанная позавчера, должна сходиться с тем, что на экране."""
    client.force_login(administrator)
    pay_to(client, our_record, account="KZ111111111111111111", bank=kaspi.pk, kbe="17")

    pay_to(client, our_record, account="KZ999999999999999999", bank=halyk.pk, kbe="19")

    closed = PaymentDetails.objects.get(account="KZ111111111111111111")
    assert closed.bank == kaspi
    assert closed.kbe == "17"


def test_one_set_is_marked_the_principal_one(client, administrator, our_record, kaspi):
    """Экран знает, что показать одной строкой, — и говорит это словом, а не местом в списке."""
    client.force_login(administrator)

    response = pay_to(client, our_record, bank=kaspi.pk, is_primary="on", follow=True)

    assert PaymentDetails.objects.get(record=our_record).is_primary
    assert "основной" in rows_in(response.content.decode(), "payment", "data-payment")[0]


def test_marking_a_new_set_principal_takes_the_mark_off_the_one_before_it(
    client, administrator, our_record, kaspi, halyk
):
    """Основной один: два помеченных комплекта — это два ответа на вопрос «куда платить»."""
    client.force_login(administrator)
    pay_to(client, our_record, account="KZ111111111111111111", bank=kaspi.pk, is_primary="on")

    pay_to(client, our_record, account="KZ999999999999999999", bank=halyk.pk, is_primary="on")

    # Пометка снята, а сам комплект остался: закрытый счёт не затирается новым.
    assert not PaymentDetails.objects.get(account="KZ111111111111111111").is_primary
    assert PaymentDetails.objects.get(account="KZ999999999999999999").is_primary


def test_a_set_without_a_bank_is_refused_and_nothing_is_written(
    client, administrator, our_record
):
    """«Каспи» и «Kaspi Bank» — один банк, и говорит об этом справочник, а не набранное от руки."""
    client.force_login(administrator)

    response = pay_to(client, our_record)

    assert response.status_code == 200
    assert not PaymentDetails.objects.filter(record=our_record).exists()
    assert "Выберите банк" in entries_on(response.content.decode())["payment"]


# Контактные лица


def add_contact(client, record, full_name="Иванов Иван", **fields):
    """Завести контактное лицо — своя створка и своё имя в отправке."""
    return keep(client, record, submitted="contact", full_name=full_name, **fields)


def test_a_contact_person_is_entered_with_everything_known_about_them(
    client, administrator, our_record
):
    """«Кому звонить» и «кого поздравить» — один список, и заводят его одной створкой."""
    client.force_login(administrator)

    response = add_contact(
        client,
        our_record,
        position="главный инженер",
        phone="+7 701 000 00 00",
        email="ivanov@alpha.kz",
        born_on="1980-03-14",
        follow=True,
    )

    entered = ContactPerson.objects.get(record=our_record)
    assert entered.full_name == "Иванов Иван"
    assert entered.position == "главный инженер"
    assert entered.phone == "+7 701 000 00 00"
    assert entered.email == "ivanov@alpha.kz"
    assert entered.born_on == date(1980, 3, 14)
    assert "Иванов Иван" in rows_in(response.content.decode(), "contacts", "data-contact")[0]


def test_the_contact_person_is_not_asked_for_a_bin(client, administrator, our_record):
    """Он ни с кем не в отношениях, аренду на него не заводят, и БИН ему не нужен."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert not any("bin" in name for name in entry_fields(page, "contact"))
    assert "БИН" not in entries_on(page)["contact"]


def test_a_contact_person_does_not_reach_the_shelf_of_parties(
    client, administrator, our_record
):
    """Директор не встаёт в один список со своим же ТОО: он не Сторона."""
    client.force_login(administrator)
    add_contact(client, our_record)

    _, page = shelf(client)

    assert parties_on(page) == [str(our_record.party_id)]
    assert "Иванов Иван" not in page


def test_a_natural_person_is_offered_no_entry_of_contact_persons(
    client, administrator, downtown, petrov, make_record
):
    """Заводить физлицу представителя значит раздваивать одного человека (ADR 0025)."""
    record = make_record(downtown, petrov)
    client.force_login(administrator)

    _, page = screen(client, record)

    assert "contact" not in entries_on(page)


def test_a_contact_person_submitted_on_a_natural_person_is_refused(
    client, administrator, downtown, petrov, make_record
):
    """Створки нет, и отправка мимо неё не заводит ничего: «не бывает» отвечается одинаково."""
    record = make_record(downtown, petrov)
    client.force_login(administrator)

    response = add_contact(client, record)

    assert response.status_code == 404
    assert not ContactPerson.objects.filter(record=record).exists()


# День рождения физлица


def mark_a_birthday(client, record, born_on="1977-01-01", **fields):
    """Записать день рождения на самой карточке — своя створка и своё имя в отправке."""
    return keep(client, record, submitted="birthday", born_on=born_on, **fields)


@pytest.fixture
def record_of_a_person(downtown, petrov, make_record):
    """Карточка ИП Петрова: физлицо, чей личный повод повесить не на кого."""
    return make_record(downtown, petrov)


def test_the_birthday_of_a_natural_person_is_kept_on_the_record(
    client, administrator, record_of_a_person
):
    """Личный повод существует и там, где его не на кого повесить (ADR 0023)."""
    client.force_login(administrator)

    response = mark_a_birthday(client, record_of_a_person, follow=True)

    record_of_a_person.refresh_from_db()
    assert record_of_a_person.born_on == date(1977, 1, 1)
    assert fields_on(response.content.decode())["born_on"] == "01.01.1977"


def test_the_birthday_already_recorded_comes_back_into_the_form(
    client, administrator, record_of_a_person
):
    """Заведённое однажды правят той же створкой: два места для одного дня разошлись бы."""
    client.force_login(administrator)
    mark_a_birthday(client, record_of_a_person)

    _, page = screen(client, record_of_a_person)

    assert "1977-01-01" in entries_on(page)["birthday"]


def test_a_legal_entity_is_offered_no_birthday_of_its_own(client, administrator, our_record):
    """День рождения юрлица — это дни рождения его людей, и они в блоке контактных лиц."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert "birthday" not in entries_on(page)


def test_a_birthday_submitted_on_a_legal_entity_is_refused(client, administrator, our_record):
    """Створки нет — и отправка мимо неё не заводит ничего."""
    client.force_login(administrator)

    response = mark_a_birthday(client, our_record)

    our_record.refresh_from_db()
    assert response.status_code == 404
    assert our_record.born_on is None


# Кому карточка не даётся


def test_a_reader_submitting_a_form_is_refused_and_nothing_is_written(
    client, member, our_record, kaspi
):
    """Отвечает 403, а не 404: экран этой карточки сотруднику показан, и «её нет» было бы
    неправдой о том, что уже перед ним (ADR 0005)."""
    client.force_login(member)

    response = pay_to(client, our_record, bank=kaspi.pk)

    assert response.status_code == 403
    assert not PaymentDetails.objects.filter(record=our_record).exists()


def test_another_clients_record_is_not_maintained_at_all(
    client, administrator, central, alpha, make_record, kaspi
):
    """Чужая карточка отвечает 404 и записи, и чтению: скрывают чужие данные, а не свою
    нехватку прав (ADR 0006)."""
    theirs = make_record(central, alpha)
    client.force_login(administrator)

    response = pay_to(client, theirs, bank=kaspi.pk)

    assert response.status_code == 404
    assert not PaymentDetails.objects.filter(record=theirs).exists()


def test_a_record_is_maintained_even_when_another_client_knows_the_party_too(
    client, administrator, our_record, central, alpha, make_record, kaspi
):
    """Свою карточку ведут всегда: то, что Сторона знакома кому-то ещё, замораживает общую
    половину, а не телефоны и счета (ADR 0028)."""
    make_record(central, alpha)
    client.force_login(administrator)

    pay_to(client, our_record, bank=kaspi.pk)

    assert PaymentDetails.objects.filter(record=our_record).count() == 1
