"""Общая половина Стороны: пока её правят, когда она замирает и что тогда говорит экран.

Шов тот же, что и у остального раздела, — HTTP. Тесты отправляют форму по адресу экрана
Стороны от имени сотрудника с известным членством и проверяют наблюдаемое: что стоит в шапке
после правки, что осталось в базе после отказа, какой код вернул запрос и что прочёл на экране
тот, кому правка уже не принадлежит.

Опор в разметке две. `data-shared-half` — состояние общей половины: правится она или замерла;
сотруднику без флага администратора не достаётся ни то, ни другое. `data-entry="shared-half"` —
сама форма, тем же атрибутом, каким читаются створки ведения карточки: один атрибут — один
договор.
"""

import re

import pytest
from django.urls import reverse

from parties.models import OrgMembership, Party

from .test_page import fields_on, screen, sections_on
from .test_record_keeping import entries_on
from .test_shelf import rows_on, stated

pytestmark = pytest.mark.django_db

#: Состояние общей половины на экране: правится или замерла. Отсутствует вовсе там, где
#: правка не предлагается никому.
SHARED_HALF = re.compile(r'data-shared-half="(?P<state>[^"]+)"')


def shared_half_state(page):
    """Что экран говорит об общей половине, или None, если он не говорит о ней ничего."""
    found = SHARED_HALF.search(page)
    return found["state"] if found else None


def edit(client, record, follow=False, **fields):
    """Отправить правку общей половины по адресу самого экрана, на котором она стоит."""
    return client.post(
        reverse("parties:party_detail", args=[record.pk]),
        {"submitted": "shared-half", **fields},
        follow=follow,
    )


def named(client, record, name="ТОО «Бета»", **fields):
    """Правка с заполненной общей половиной: меняется название, остальное как было."""
    party = record.party
    return edit(
        client,
        record,
        name=name,
        bin_iin=fields.pop("bin_iin", party.bin_iin),
        kind=fields.pop("kind", party.kind),
        **fields,
    )


# Правка, пока карточка одна


def test_the_shared_half_is_edited_while_mine_is_the_only_record(
    client, administrator, our_record
):
    """Занять свободный БИН не вредит никому: пока Сторону знает один, радиуса у правки нет."""
    client.force_login(administrator)

    response = named(client, our_record, follow=True)

    our_record.party.refresh_from_db()
    assert our_record.party.name == "ТОО «Бета»"
    # Перезагруженный экран и есть подтверждение: правку читают там, где её набрали.
    assert fields_on(response.content.decode())["name"] == "ТОО «Бета»"


def test_the_form_asks_the_four_columns_of_the_shared_half(client, administrator, our_record):
    """Название, БИН/ИИН, юрлицо/физлицо и сфера — одна строка на всю систему, и ничего сверх."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    form = entries_on(page)["shared-half"]
    asked = set(re.findall(r'<(?:input|select)[^>]*\bname="([^"]+)"', form))
    assert asked == {
        "csrfmiddlewaretoken",
        "submitted",
        "name",
        "bin_iin",
        "kind",
        "line_of_business",
    }


def test_the_line_of_business_is_edited_by_the_same_form(
    client, administrator, our_record, construction
):
    """Сфера живёт на самой Стороне, а не в карточке (ADR 0020), — и правится вместе с ней."""
    client.force_login(administrator)

    named(client, our_record, line_of_business=construction.pk)

    our_record.party.refresh_from_db()
    assert our_record.party.line_of_business == construction


def test_a_taken_bin_is_refused_and_nothing_is_changed(
    client, administrator, our_record, make_party
):
    """Правка на занятый БИН — отказ, а не вторая строка: БИН и есть ответ на «кто это»."""
    client.force_login(administrator)
    make_party("ТОО «Гамма»", "111111111111")

    response = named(client, our_record, bin_iin="111111111111")

    our_record.party.refresh_from_db()
    assert our_record.party.name == "ТОО «Альфа»"
    assert our_record.party.bin_iin == "050340008889"
    assert response.status_code == 200
    assert "уже заведена" in response.content.decode()


def test_the_bin_is_cleared_of_spaces_by_the_edit_too(client, administrator, our_record):
    """«091 240 012 345» и «091240012345» — один номер, и правка чистит его тем же правилом,
    каким чистит заведение: иначе один и тот же БИН разошёлся бы двумя написаниями."""
    client.force_login(administrator)

    named(client, our_record, bin_iin="091 240 012 345")

    our_record.party.refresh_from_db()
    assert our_record.party.bin_iin == "091240012345"


def test_an_empty_name_is_refused(client, administrator, our_record):
    """Полку Сторон читают по названиям: Сторона без названия на ней неразличима."""
    client.force_login(administrator)

    response = named(client, our_record, name="")

    our_record.party.refresh_from_db()
    assert our_record.party.name == "ТОО «Альфа»"
    assert response.status_code == 200


def test_the_kind_is_spelled_as_it_is_on_both_screens(client, administrator, our_record):
    """«Юрлицо», а не «Организация»: на этих экранах организация — арендатор платформы."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    form = entries_on(page)["shared-half"]
    assert "Юрлицо" in form
    assert "Организация" not in form


def test_the_kind_is_edited_by_the_same_form(client, administrator, our_record):
    """Заведённое юрлицом физлицо исправляется той же формой: род решает, где висит день
    рождения и бывает ли у Стороны блок контактных лиц."""
    client.force_login(administrator)

    named(client, our_record, kind=Party.Kind.PERSON)

    our_record.party.refresh_from_db()
    assert our_record.party.kind == Party.Kind.PERSON


# Замирание, когда карточка не одна


@pytest.fixture
def known_by_two(our_record, central, make_record):
    """Вторая организация завела свою карточку на ту же Сторону — общее замерло.

    Central City Properties, а не второй сотрудник DownTown: замирает общее оттого, что правка
    дотянулась бы до чужого экрана, и вторая карточка той же организации такого экрана не
    заводит — она и невозможна, пара «Сторона + организация» уникальна.
    """
    return make_record(central, our_record.party)


def test_the_form_is_not_shown_once_a_second_record_exists(
    client, administrator, our_record, known_by_two
):
    """Замёрзшая половина не показывается формой, которая потом откажет (ADR 0028)."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert shared_half_state(page) == "frozen"
    assert "shared-half" not in entries_on(page)


def test_the_screen_says_why_the_shared_half_froze(
    client, administrator, our_record, known_by_two
):
    """Экран говорит, что Сторона знакома не только нам, и называет, кто её теперь правит."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    said = stated(re.search(r'data-shared-half="frozen"[^>]*>(.*?)</div>', page, re.DOTALL)[1])
    assert "не только ваша организация" in said
    assert "администратор платформы" in said
    # Ни кому, ни с каких пор: узнаётся ровно один бит — что Сторона знакома кому-то ещё.
    assert "Central" not in said


def test_a_submission_with_two_records_is_refused_and_changes_nothing(
    client, administrator, our_record, known_by_two
):
    """Отклоняется на отправке, а не только не показывается: адрес набирают и руками."""
    client.force_login(administrator)

    response = named(client, our_record)

    our_record.party.refresh_from_db()
    assert our_record.party.name == "ТОО «Альфа»"
    # 403, а не 404: Сторона этому сотруднику показана, и право на правку существует — оно
    # принадлежит администратору платформы.
    assert response.status_code == 403


def test_the_frozen_half_does_not_freeze_the_record(
    client, administrator, our_record, known_by_two
):
    """Учётную карточку ведут всегда: створки реквизитов и контактных лиц остаются на месте."""
    client.force_login(administrator)

    _, page = screen(client, our_record)

    assert {"payment", "contact"} <= set(entries_on(page))


def test_the_other_organisations_record_freezes_too(
    client, administrator, our_record, known_by_two, central, django_user_model
):
    """Замирает общее для обоих: правило о радиусе, а не о том, кто завёл первым (ADR 0020)."""
    theirs = django_user_model.objects.create_user("their-director")
    OrgMembership.objects.create(user=theirs, org=central, is_admin=True)
    client.force_login(theirs)

    _, page = screen(client, known_by_two)

    assert shared_half_state(page) == "frozen"


# Кому правка не предлагается вовсе


def test_an_employee_without_the_flag_is_told_nothing_about_the_shared_half(
    client, member, our_record
):
    """Ни формы, ни объяснения, почему её нет: чужое право не объясняют."""
    client.force_login(member)

    _, page = screen(client, our_record)

    assert shared_half_state(page) is None


def test_an_employee_without_the_flag_is_refused_the_edit(client, member, our_record):
    """И отклоняется на отправке — обе стадии, как и всё остальное в разделе (ADR 0005)."""
    client.force_login(member)

    response = named(client, our_record)

    our_record.party.refresh_from_db()
    assert our_record.party.name == "ТОО «Альфа»"
    assert response.status_code == 403


# Смена рода уносит с экрана то, чего у нового рода не бывает


def test_a_company_turned_into_a_person_stops_naming_its_people(
    client, administrator, our_record, make_contact
):
    """Заведённое юрлицом физлицо исправляют этой же формой — и контактных лиц у него не
    остаётся ни в блоке, ни в поводах: «не бывает» и «не заведено» отвечаются одинаково
    (ADR 0025), а повод человека, которого на экране нет, читался бы как чужой."""
    client.force_login(administrator)
    make_contact(our_record, "Иванов Иван", born_on="1980-03-14")

    named(client, our_record, kind=Party.Kind.PERSON)

    _, page = screen(client, our_record)
    assert "contacts" not in sections_on(page)
    assert "Иванов" not in fields_on(page)["occasions"]


def test_a_person_turned_into_a_company_stops_naming_her_own_birthday(
    client, administrator, our_record
):
    """И обратно: день рождения ТОО — это дни рождения его людей, и записанный на карточке
    физлица он уходит из шапки вместе с родом, а не остаётся поводом без строки."""
    client.force_login(administrator)
    our_record.party.kind = Party.Kind.PERSON
    our_record.party.save()
    our_record.born_on = "1980-03-14"
    our_record.save()

    named(client, our_record, kind=Party.Kind.COMPANY)

    _, page = screen(client, our_record)
    assert "born_on" not in fields_on(page)
    # Поводов у неё не остаётся вовсе: контактных лиц нет, а свой день рождения юрлицо не
    # держит — он принадлежал бы его людям.
    assert "День рождения" not in fields_on(page)["occasions"]


def test_the_shelf_reads_the_occasions_by_the_same_rule(
    client, administrator, our_record, make_contact
):
    """Полка считает ближайший повод тем же правилом, каким экран перечисляет все: два
    изложения однажды назвали бы ближайшим то, чего на экране нет (ADR 0023)."""
    client.force_login(administrator)
    make_contact(our_record, "Иванов Иван", born_on="1980-03-14")
    named(client, our_record, kind=Party.Kind.PERSON)

    row = rows_on(client.get(reverse("parties:party_list")).content.decode())
    assert "Иванов" not in row[str(our_record.party_id)]
