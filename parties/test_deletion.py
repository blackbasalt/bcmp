"""Удаление учётной карточки: вопрос, что оно уносит, что остаётся и кому оно предлагается.

Шов тот же, что и у остального раздела, — HTTP. Тесты отправляют с экрана Стороны от имени
сотрудника с известным членством и проверяют наблюдаемое: что экран спрашивает прежде, чем
что-либо разрушено, что осталось в таблицах после ответа, куда попал читатель и каким кодом
ответил запрос.

Опор в разметке две, обе — те же, что и на странице документа, потому что правило одно и то же
(ADR 0013). `data-deletion` — состояние удаления: предложено оно или экран держит вопрос;
сотруднику без флага администратора не достаётся ни то, ни другое. `data-taken` называет одну
вещь, уходящую с карточкой: вопрос стоит того, чтобы его задавали, лишь пока он говорит, что
именно будет уничтожено, — и проверяется этот список, а не фраза вокруг него.

Удаляется карточка, а не Сторона: удалённая строка реестра освободила бы БИН, и вторая
организация завела бы юрлицо без прошлого при том, что на прежнее ссылаются аренды, документы
«Кем выдан» и `responsible_party` инженерных систем (ADR 0028).
"""

import re

import pytest
from django.urls import reverse

from leases.party_choice import found
from parties.models import ContactPerson, Party, PartyRecord, PaymentDetails

from .test_page import screen
from .test_shelf import parties_on, shelf, stated

pytestmark = pytest.mark.django_db

#: Состояние удаления на экране: предложено или спрошено. Отсутствует вовсе на экране того,
#: кто удалять не вправе, — действие, в котором откажут, на экране не называют.
DELETION = re.compile(r'data-deletion="(?P<state>[^"]+)"')

#: Одна вещь, уходящая с карточкой: что это и что о ней сказано. Названа атрибутом, так что
#: «что-то уносится» и «вот что уносится» — два разных утверждения.
TAKEN = re.compile(r'data-taken="(?P<name>[^"]+)">(?P<said>[^<]*)<')


def deletion_state(page):
    """Что экран говорит об удалении этой карточки, или None, если не говорит ничего."""
    state = DELETION.search(page)
    return state["state"] if state else None


def taken_on(page):
    """Что вопрос называет уходящим вместе с карточкой, по имени каждой вещи."""
    return {one["name"]: stated(one["said"]) for one in TAKEN.finditer(page)}


def ask_to_delete(client, record):
    """Нажать «Удалить учётную карточку» — отправка, которая задаёт вопрос и не разрушает
    ничего."""
    return client.post(
        reverse("parties:party_detail", args=[record.pk]), {"submitted": "deletion"}
    )


def confirm_deletion(client, record, follow=False):
    """Ответить на вопрос — отправка, которую посылает сам вопрос."""
    return client.post(
        reverse("parties:party_detail", args=[record.pk]),
        {"submitted": "deletion-confirmed"},
        follow=follow,
    )


@pytest.fixture
def filled_record(our_record, kaspi, make_contact):
    """Карточка, на которой есть что уносить: комплект реквизитов и контактное лицо."""
    PaymentDetails.objects.create(
        record=our_record, bank=kaspi, account="KZ111111111111111111"
    )
    make_contact(our_record, "Иванов Иван", born_on="1980-03-14")
    return our_record


# Вопрос задаёт приложение, а не браузер


def test_the_offer_stands_on_the_screen_of_the_record(client, administrator, our_record):
    """Удаление предлагается там же, где карточку читают, — с её собственного экрана."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert deletion_state(page) == "offered"


def test_the_first_press_asks_and_destroys_nothing(client, administrator, filled_record):
    """Первое нажатие задаёт вопрос: два нажатия в разных местах, а не формулировка между
    ними, защищают от промаха (ADR 0013)."""
    client.force_login(administrator)

    response = ask_to_delete(client, filled_record)

    assert deletion_state(response.content.decode()) == "confirming"
    assert PartyRecord.objects.filter(pk=filled_record.pk).exists()
    assert PaymentDetails.objects.filter(record=filled_record).exists()


def test_the_question_is_asked_by_the_application(client, administrator, our_record):
    """Подтверждение живёт на запросе, а не в скрипте: то, которое жило бы в скрипте,
    исчезло бы вместе с несработавшим скриптом."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert "confirm(" not in page
    assert "onclick" not in page


def test_the_question_names_what_the_deletion_takes(client, administrator, filled_record):
    """Названо прежде, чем что-либо уничтожено: «удалить карточку» значит больше, чем строку,
    на которую смотрит читатель."""
    client.force_login(administrator)

    response = ask_to_delete(client, filled_record)

    taken = taken_on(response.content.decode())
    assert taken["payment"] == "1 комплект платёжных реквизитов"
    assert taken["contacts"] == "1 контактное лицо"


def test_a_bare_record_takes_nothing_with_it(client, administrator, our_record):
    """Карточка, на которой ничего не заведено, не уносит ничего — и вопрос не обещает
    несуществующего: ноль в предупреждении читается как что-то потерянное."""
    client.force_login(administrator)

    response = ask_to_delete(client, our_record)

    assert taken_on(response.content.decode()) == {}


def test_the_occasions_are_named_among_what_goes(client, administrator, filled_record):
    """Поводы уходят с карточкой: день рождения контактного лица хранится на ней, а
    профессиональный праздник читать станет неоткуда."""
    client.force_login(administrator)

    response = ask_to_delete(client, filled_record)

    assert taken_on(response.content.decode())["occasions"] == "1 повод"


def test_the_professional_holiday_is_not_named_among_what_goes(
    client, administrator, our_record, construction, make_holiday
):
    """Профессиональный праздник выводится из сферы деятельности Стороны, а Сторона остаётся
    (ADR 0023, ADR 0028): названный уничтоженным, он пообещал бы разрушение, которого не
    произойдёт."""
    client.force_login(administrator)
    our_record.party.line_of_business = construction
    our_record.party.save()
    make_holiday(construction, "День строителя", week_of_month=2, weekday=6, month=8)

    response = ask_to_delete(client, our_record)

    assert taken_on(response.content.decode()) == {}


def test_a_birthday_on_the_record_itself_is_named(client, administrator, our_record, petrov):
    """День рождения физлица уносится: он лежит на карточке, и назвать его больше нечем —
    контактных лиц у физлица не бывает (ADR 0025)."""
    client.force_login(administrator)
    our_record.party = petrov
    our_record.born_on = "1977-01-01"
    our_record.save()

    response = ask_to_delete(client, our_record)

    assert taken_on(response.content.decode())["occasions"] == "1 повод"


# Второе нажатие


def test_the_record_and_everything_on_it_are_gone(client, administrator, filled_record):
    """Необратимо и целиком: мягкого удаления нет ни у одной сущности проекта (ADR 0013)."""
    client.force_login(administrator)

    confirm_deletion(client, filled_record)

    assert not PartyRecord.objects.filter(pk=filled_record.pk).exists()
    assert not PaymentDetails.objects.filter(record_id=filled_record.pk).exists()
    assert not ContactPerson.objects.filter(record_id=filled_record.pk).exists()


def test_the_party_stays_in_the_registry(client, administrator, filled_record):
    """Сторона остаётся: удалённая строка освободила бы БИН, и вторая организация завела бы
    юрлицо без прошлого (ADR 0028)."""
    client.force_login(administrator)

    confirm_deletion(client, filled_record)

    stayed = Party.objects.get(pk=filled_record.party_id)
    assert stayed.bin_iin == "050340008889"


def test_the_party_is_still_found_when_a_lease_is_entered(
    client, administrator, filled_record, manhattan, make_space, first_floor
):
    """Поиск при заведении аренды остаётся общесистемным: арендатор, которого ещё никто не
    встречал, иначе был бы ненаходим (ADR 0020, спека, история 49)."""
    client.force_login(administrator)

    confirm_deletion(client, filled_record)

    assert filled_record.party in found("Альфа")


def test_the_party_leaves_my_shelf(client, administrator, filled_record):
    """Полка Сторон — полка учётных карточек: без карточки Сторона с неё уходит (ADR 0020)."""
    client.force_login(administrator)

    confirm_deletion(client, filled_record)

    _, page = shelf(client)
    assert str(filled_record.party_id) not in parties_on(page)


def test_the_reader_lands_on_the_shelf_and_is_told_what_went(
    client, administrator, filled_record
):
    """Экран, с которого удаляли, ушёл вместе с карточкой: читатель попадает на полку, и там
    сказано, чьей карточки не стало и что с ней ушло."""
    client.force_login(administrator)

    response = confirm_deletion(client, filled_record, follow=True)

    said = stated(response.content.decode())
    assert "ТОО «Альфа»" in said
    assert "1 комплект платёжных реквизитов" in said
    assert "1 контактное лицо" in said


def test_deleting_twice_finds_nothing(client, administrator, our_record):
    """Второй щелчок двойного не находит карточки и отвечает, что её нет, — как отвечает всё
    отсутствующее (ADR 0006)."""
    client.force_login(administrator)
    confirm_deletion(client, our_record)

    response = confirm_deletion(client, our_record)

    assert response.status_code == 404


# Чужая карточка


def test_another_organisations_record_is_untouched(
    client, administrator, our_record, central, make_record, kaspi
):
    """Удаляется моя карточка, а не знание о Стороне вообще: у второй управляющей компании
    остаётся её собственная (ADR 0020)."""
    theirs = make_record(central, our_record.party)
    PaymentDetails.objects.create(record=theirs, bank=kaspi, account="KZ222222222222222222")
    client.force_login(administrator)

    confirm_deletion(client, our_record)

    assert PartyRecord.objects.filter(pk=theirs.pk).exists()
    assert PaymentDetails.objects.filter(record=theirs).exists()


# Сторону из приложения не удаляют вовсе


def test_the_screen_offers_no_way_to_delete_the_party(client, administrator, our_record):
    """Сторона из приложения не удаляется вовсе — только администратором платформы в админке
    (ADR 0028). Экран не называет и не предлагает такого действия."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert "Удалить Сторону" not in page
    assert "удалить Сторону" not in page


# Кому удаление не предлагается вовсе


def test_an_employee_without_the_flag_is_offered_no_deletion(client, member, our_record):
    """Показанный вопрос с отказом на ответе читался бы как неисправность формы (ADR 0013)."""
    client.force_login(member)

    _, page = screen(client, our_record)

    assert deletion_state(page) is None


@pytest.mark.parametrize("submitted", ["deletion", "deletion-confirmed"])
def test_an_employee_without_the_flag_is_refused_both_stages(
    client, member, our_record, submitted
):
    """Обе стадии, включая вопрос: отклоняется на submission, а не только не показывается."""
    client.force_login(member)

    response = client.post(
        reverse("parties:party_detail", args=[our_record.pk]), {"submitted": submitted}
    )

    assert response.status_code == 403
    assert PartyRecord.objects.filter(pk=our_record.pk).exists()
