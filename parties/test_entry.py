"""Заведение Стороны администратором организации — что видно на границе HTTP.

Шов тот же, что и у остальных экранов раздела: тесты отправляют форму полки Сторон
тестовым клиентом от имени сотрудника с известным членством и проверяют наблюдаемое — что
осталось в базе после отправки, каким кодом ответил запрос, на какой экран он привёл и что
сказано словами. Ниже HTTP шва нет: и право на запись, и обязательность БИН, и то, что
общая половина занятой Стороны не переписывается, читаются ровно так, как их читает
администратор.

Опора в разметке — атрибут `data-entry` на самой створке: он показывает, предложено ли
заведение, и сотруднику без флага администратора не показывается вовсе. Тот же приём, что
`data-upload` на створке загрузки документов.
"""

import re

import pytest
from django.urls import reverse

from parties.models import OrgMembership, Party, PartyRecord

from .test_shelf import parties_on, shelf, stated

pytestmark = pytest.mark.django_db

#: БИН, свободный во всех фикстурах: ни одна из Сторон корневого conftest его не занимает.
FREE_BIN = "091240012345"


def enter(
    client,
    name="ТОО «Бета»",
    bin_iin=FREE_BIN,
    kind=Party.Kind.COMPANY,
    follow=False,
    **fields,
):
    """Отправить форму заведения — по тому же адресу, по которому открыта полка."""
    return client.post(
        reverse("parties:party_list"),
        {"name": name, "bin_iin": bin_iin, "kind": kind, **fields},
        follow=follow,
    )


def entry_form(page):
    """Створка заведения на полке — или ничего, если она не предложена."""
    return page if 'data-entry="parties"' in page else None


def unfolded(page):
    """Стоит ли створка раскрытой, а не под своим заголовком.

    Читается по тому же `data-entry`, по которому читается и само предложение: раскрыта и
    предложена — два разных утверждения об одном элементе, и вторая опора для второго из них
    была бы вторым, что придётся держать в согласии с разметкой.
    """
    tag = re.search(r'<details[^>]*data-entry="parties"[^>]*>', page)
    return tag is not None and re.search(r"\bopen\b", tag.group()) is not None


def fields_asked(page):
    """Имена полей, о которых спрашивает створка, — то, что уедет в отправке."""
    return set(re.findall(r'<(?:input|select)[^>]*\bname="([^"]+)"', page))


def said(response):
    """Сказанное словами на экране, куда привела отправка."""
    return stated(response.content.decode())


# Кому предложено заведение


def test_an_administrator_of_the_organisation_is_offered_the_entry(client, administrator):
    """Завести поставщика больше не значит позвонить в поддержку (ADR 0021)."""
    client.force_login(administrator)

    _, page = shelf(client)

    assert entry_form(page) is not None


def test_a_member_without_the_flag_is_offered_no_entry_form_at_all(client, member):
    """Показанная форма, отклоняющая отправку, читается как сломанный экран (ADR 0005)."""
    client.force_login(member)

    _, page = shelf(client)

    assert entry_form(page) is None


def test_a_member_without_the_flag_is_refused_even_by_posting_directly(client, member):
    """Отклоняется не только показ формы: право спрашивается на самом запросе."""
    client.force_login(member)

    response = enter(client)

    assert response.status_code == 403
    assert Party.objects.filter(bin_iin=FREE_BIN).count() == 0
    assert PartyRecord.objects.count() == 0


def test_an_anonymous_entry_is_sent_to_the_login_screen(client):
    """До входа ничего не заводится — ровно как ничего и не читается."""
    response = enter(client)

    assert response.status_code == 302
    assert reverse("login") in response["Location"]
    assert Party.objects.filter(bin_iin=FREE_BIN).count() == 0


def test_administering_one_organisation_does_not_administer_another(
    client, django_user_model, downtown, central
):
    """Администраторство принадлежит паре «сотрудник + организация» (ADR 0005).

    Читателю, ведущему одного клиента и лишь читающему второго, карточка заводится тому
    клиенту, чьи данные он ведёт, — и вторая организация не становится его от того, что её
    полка у него на экране.
    """
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=False)
    client.force_login(user)

    enter(client)

    assert PartyRecord.objects.filter(org=central).count() == 0
    assert PartyRecord.objects.filter(org=downtown).count() == 1


# О чём спрашивает форма


def test_the_form_asks_the_name_the_bin_the_kind_and_the_line_of_business(
    client, administrator
):
    """Четыре вопроса и ни одного лишнего: остальное — дело учётной карточки."""
    client.force_login(administrator)

    _, page = shelf(client)

    assert {"name", "bin_iin", "kind", "line_of_business"} <= fields_asked(page)


def test_the_form_stands_open_on_a_shelf_with_no_parties_on_it(client, administrator):
    """Пустая полка и есть то место, где отсутствие замечают."""
    client.force_login(administrator)

    _, page = shelf(client)

    assert unfolded(page)


def test_the_form_stays_folded_over_a_shelf_a_search_emptied(
    client, administrator, downtown, alpha, make_record
):
    """Полка, опустошённая отбором, — не пустая полка, и створка над ней стоит закрытой.

    Тот, кто сузил полку до ничего, ищет Сторону, а не заводит её, и форма, раскрывающаяся у
    него под руками, отвечает на вопрос, которого он не задавал. Предложена она при этом
    по-прежнему: право заводить от отбора не меняется.
    """
    make_record(downtown, alpha)
    client.force_login(administrator)

    page = client.get(
        reverse("parties:party_list"), {"q": "Мегаполис"}
    ).content.decode()

    assert entry_form(page) is not None
    assert not unfolded(page)


# Заведение свободного БИН


def test_a_party_is_entered_with_a_record_of_my_organisation(client, administrator, downtown):
    """Вместе со Стороной заводится карточка: без неё Сторона не попала бы на свою полку."""
    client.force_login(administrator)

    enter(client, name="ТОО «Бета»", bin_iin=FREE_BIN, kind=Party.Kind.COMPANY)

    party = Party.objects.get(bin_iin=FREE_BIN)
    assert party.name == "ТОО «Бета»"
    assert party.kind == Party.Kind.COMPANY
    assert PartyRecord.objects.filter(party=party, org=downtown).count() == 1


def test_the_line_of_business_is_recorded_on_the_party_itself(
    client, administrator, construction
):
    """Сфера деятельности — единственное, что записывается не в карточку, а на Сторону."""
    client.force_login(administrator)

    enter(client, line_of_business=str(construction.pk))

    assert Party.objects.get(bin_iin=FREE_BIN).line_of_business == construction


def test_a_party_is_entered_without_a_line_of_business(client, administrator):
    """Сферу заводят не всегда: у всех 699 Сторон её нет, и полка это переживает."""
    client.force_login(administrator)

    enter(client)

    assert Party.objects.get(bin_iin=FREE_BIN).line_of_business is None


def test_the_entered_party_stands_on_the_shelf(client, administrator):
    """Заведённая Сторона оказывается на полке — это и есть, зачем заводится карточка."""
    client.force_login(administrator)
    enter(client)

    _, page = shelf(client)

    assert str(Party.objects.get(bin_iin=FREE_BIN).pk) in parties_on(page)


def test_after_entering_the_screen_of_the_entered_party_opens(client, administrator):
    """Перезагруженный экран заведённой Стороны и есть подтверждение."""
    client.force_login(administrator)

    response = enter(client)

    record = PartyRecord.objects.get(party__bin_iin=FREE_BIN)
    assert response.status_code == 302
    assert response["Location"] == reverse("parties:party_detail", args=[record.pk])


# БИН обязателен обоим родам


def test_an_entry_without_a_bin_stores_nothing(client, administrator):
    """Вся защита от дублей стоит на БИН: без него «ТОО «Альфа»» заведут дважды (ADR 0028)."""
    client.force_login(administrator)

    response = enter(client, bin_iin="")

    assert response.status_code == 200
    assert Party.objects.filter(name="ТОО «Бета»").count() == 0
    assert PartyRecord.objects.count() == 0


def test_a_person_without_an_iin_is_refused_too(client, administrator):
    """Обоим родам: незнание ИИН значит, что Сторону заводят рано, а не что поле лишнее."""
    client.force_login(administrator)

    response = enter(client, name="ИП Сидоров", bin_iin="", kind=Party.Kind.PERSON)

    assert response.status_code == 200
    assert Party.objects.filter(name="ИП Сидоров").count() == 0


def test_a_person_with_an_iin_is_entered(client, administrator):
    """ИП заводится физлицом — и с ИИН проходит ровно так же, как юрлицо с БИН."""
    client.force_login(administrator)

    enter(client, name="ИП Сидоров", bin_iin=FREE_BIN, kind=Party.Kind.PERSON)

    assert Party.objects.get(bin_iin=FREE_BIN).kind == Party.Kind.PERSON


def test_a_refusal_comes_back_onto_the_shelf_with_the_form_filled_in(
    client, administrator, downtown, alpha, make_record
):
    """Отказ возвращается на экран, с которого форму отправляли (ADR 0005).

    С заполненной формой: перепечатывать название после отказа о другом поле — цена, которую
    отказ брать не должен. И раскрытой: причина, спрятанная под заголовком створки, — причина,
    которой никто не видит.

    Полка под створкой не пуста, так что раскрыл её именно отказ, а не пустой раздел.
    """
    make_record(downtown, alpha)
    client.force_login(administrator)

    response = enter(client, name="ТОО «Бета»", bin_iin="")
    page = response.content.decode()

    assert "<li>Стороны</li>" in page
    assert str(alpha.pk) in parties_on(page)
    assert unfolded(page)
    assert 'value="ТОО «Бета»"' in page


def test_an_entry_without_a_name_stores_nothing(client, administrator):
    """Сторона без названия не Сторона: полку читают глазами по названиям."""
    client.force_login(administrator)

    response = enter(client, name="")

    assert response.status_code == 200
    assert Party.objects.filter(bin_iin=FREE_BIN).count() == 0


# Занятый БИН


def test_a_taken_bin_is_said_to_be_taken(client, administrator, make_party):
    """Администратор узнаёт, что это юрлицо кому-то в системе знакомо (ADR 0021)."""
    make_party("ТОО «Мегаполис»", FREE_BIN)
    client.force_login(administrator)

    response = enter(client, name="ТОО «Бета»", bin_iin=FREE_BIN, follow=True)

    assert "уже заведена" in said(response)


def test_what_is_said_names_neither_the_organisation_nor_what_is_recorded(
    client, administrator, central, make_party, make_record, make_contact
):
    """Утечка принята вслух ровно в один бит: ни кому, ни с каких пор, ни что записано."""
    stranger = make_party("ТОО «Мегаполис»", FREE_BIN)
    theirs = make_record(central, stranger)
    make_contact(theirs, "Игорь Соколов", phone="+7 701 000 00 00")
    client.force_login(administrator)

    response = enter(client, bin_iin=FREE_BIN, follow=True)
    page = response.content.decode()

    assert "Central City Properties" not in page
    assert "Игорь Соколов" not in page
    assert "+7 701 000 00 00" not in page


def test_a_taken_bin_gives_me_a_record_and_leaves_the_shared_half_alone(
    client, administrator, downtown, central, make_party, make_record, catering
):
    """Заводя уже существующую Сторону, администратор получает карточку на неё, а общая
    половина остаётся как была (ADR 0028)."""
    stranger = make_party("ТОО «Мегаполис»", FREE_BIN, line_of_business=catering)
    make_record(central, stranger)
    client.force_login(administrator)

    enter(client, name="ТОО «Бета»", bin_iin=FREE_BIN, kind=Party.Kind.PERSON)

    stranger.refresh_from_db()
    assert stranger.name == "ТОО «Мегаполис»"
    assert stranger.kind == Party.Kind.COMPANY
    assert stranger.line_of_business == catering
    assert PartyRecord.objects.filter(party=stranger, org=downtown).count() == 1


def test_a_bin_written_with_spaces_is_the_bin_it_already_names(
    client, administrator, downtown, make_party
):
    """«091 240 012 345» с бумаги и «091240012345» со счёта — один и тот же БИН.

    Пропущенные как есть, они завели бы два юрлица из одного — тот самый дубль, ради которого
    поле и объявлено обязательным.
    """
    stranger = make_party("ТОО «Мегаполис»", FREE_BIN)
    client.force_login(administrator)

    enter(client, name="ТОО «Бета»", bin_iin="091 240 012 345")

    assert Party.objects.filter(name="ТОО «Бета»").count() == 0
    assert PartyRecord.objects.get(org=downtown).party == stranger


def test_an_entered_bin_is_stored_without_the_spaces_it_was_typed_with(client, administrator):
    """Иначе следующий, набравший его без пробелов, завёл бы то же юрлицо второй раз."""
    client.force_login(administrator)

    enter(client, bin_iin=" 091 240 012 345 ")

    assert Party.objects.get(name="ТОО «Бета»").bin_iin == FREE_BIN


def test_a_taken_bin_enters_no_second_party(client, administrator, make_party):
    """Одна Сторона на один БИН, на всю систему (ADR 0020)."""
    make_party("ТОО «Мегаполис»", FREE_BIN)
    client.force_login(administrator)

    enter(client, bin_iin=FREE_BIN)

    assert Party.objects.filter(bin_iin=FREE_BIN).count() == 1


def test_a_taken_bin_opens_the_screen_of_the_party_it_belongs_to(
    client, administrator, downtown, make_party
):
    """Экран открывается тот же: заведение чужого БИН кончается карточкой на ту же Сторону."""
    stranger = make_party("ТОО «Мегаполис»", FREE_BIN)
    client.force_login(administrator)

    response = enter(client, bin_iin=FREE_BIN)

    record = PartyRecord.objects.get(party=stranger, org=downtown)
    assert response["Location"] == reverse("parties:party_detail", args=[record.pk])


def test_a_party_already_on_my_shelf_is_not_entered_twice(
    client, administrator, downtown, alpha, make_record
):
    """Второе заведение той же Стороны не заводит второй карточки и ничего не ломает."""
    record = make_record(downtown, alpha)
    client.force_login(administrator)

    response = enter(client, name="ТОО «Альфа»", bin_iin=alpha.bin_iin)

    assert PartyRecord.objects.filter(party=alpha, org=downtown).count() == 1
    assert response["Location"] == reverse("parties:party_detail", args=[record.pk])
    assert "уже заведена" in said(client.get(response["Location"]))


# Администратор двух организаций


def test_an_administrator_of_two_organisations_is_asked_whose_record_it_is(
    client, django_user_model, downtown, central
):
    """Чья это карточка, вывести не из чего: здания в форме нет, а угадывать некому.

    Ведущему одного клиента вопрос не задаётся вовсе — список из одного значения повторял бы
    ему то, что он и так знает.
    """
    user = django_user_model.objects.create_user("group")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=True)
    client.force_login(user)

    _, page = shelf(client)

    assert "org" in fields_asked(page)


def test_the_record_lands_on_the_organisation_chosen(
    client, django_user_model, downtown, central
):
    """Карточка заводится той организации, которую назвали."""
    user = django_user_model.objects.create_user("group")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=True)
    client.force_login(user)

    enter(client, org=str(central.pk))

    assert PartyRecord.objects.filter(party__bin_iin=FREE_BIN, org=central).count() == 1
    assert PartyRecord.objects.filter(party__bin_iin=FREE_BIN, org=downtown).count() == 0


def test_an_administrator_of_one_organisation_is_not_asked(client, administrator):
    """Список из одного значения — не выбор, а строка, повторяющая известное."""
    client.force_login(administrator)

    _, page = shelf(client)

    assert "org" not in fields_asked(page)
