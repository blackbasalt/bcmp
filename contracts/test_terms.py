"""Правка условий на экране договора — то, что узнают позже скана.

Шов тот же, которым проверяется сам экран: граница HTTP адреса `/contracts/<ключ>/`. Тесты
отправляют створку тестовым клиентом от лица сотрудника с известным членством и проверяют
наблюдаемое — что легло в базу, что говорит шапка после правки, каким кодом ответил запрос
и что стоит на форме, вернувшейся с отказом.

Опора в разметке — `data-edit` на створке, та же, что на странице документа: договор экрана
о том, предложена ли правка. Сотруднику без флага администратора эта разметка не достаётся
вовсе (ADR 0005).

Вид узнают позже скана, срок уточняют по допнику, автопролонгацию замечают, перечитывая
бумагу, — поэтому правится всё это по одному и в любом порядке, и ни одно поле не
обязательно.
"""

from datetime import date

import pytest
from django.urls import reverse

from documents.models import ContractTerms
from parties.models import OrgMembership

from .test_contract_page import fields_on, page_of
from .test_shelf import ending_cell, shelf, stated

pytestmark = pytest.mark.django_db


def correct(client, contract, **fields):
    """Поправить условия — по тому же адресу, по которому договор и читают."""
    return client.post(reverse("contracts:contract_detail", args=[contract.pk]), fields)


def looking_up(client, contract, **fields):
    """Поиск Стороны: тот же адрес, вопрос в нём, и створка перерисована с найденным."""
    response = client.get(reverse("contracts:contract_detail", args=[contract.pk]), fields)
    return response, response.content.decode()


def edit_form(page):
    """Створка правки — или ничего, если её не предложили."""
    return page if 'data-edit="contract"' in page else None


def field_of(page, name):
    """Разметка одного поля створки — чтобы спросить, что в нём стоит."""
    return next((part for part in page.split("<fieldset") if f'name="{name}"' in part), "")


@pytest.fixture
def lifts(downtown, make_contract):
    """Скан из пачки: вид, контрагент и срок у него ещё никто не проставил (ADR 0035)."""
    return make_contract(downtown, "Договор на обслуживание лифтов", doc_no="ЭКС-2026/04")


@pytest.fixture
def admin_page(client, administrator, lifts):
    """Экран незаполненного договора глазами администратора: там, где створка и стоит.

    Незаполненного потому, что правкой как раз и заполняют: вопросы о самой створке — что она
    спрашивает и чего не спрашивает — задаются экрану, на котором заполнять ещё есть что.
    """
    client.force_login(administrator)
    _, page = page_of(client, lifts)
    return page


# Кому створка достаётся


def test_an_administrator_is_offered_the_form(admin_page):
    """Правят условия там же, где их читают: отказ возвращается на экран с договором вокруг
    него (ADR 0005)."""
    assert edit_form(admin_page) is not None


def test_a_reader_without_the_flag_is_offered_no_form(client, member, lifts):
    """Экран остаётся экраном, а не бланком: действия, которого сотруднику не выполнить, ему
    и не предлагают (ADR 0005)."""
    client.force_login(member)

    _, page = page_of(client, lifts)

    assert edit_form(page) is None


def test_a_submission_from_a_reader_without_the_flag_is_refused(client, member, lifts):
    """403, а не 404: раздел ему уже показали, и отвечать «этого нет» значило бы солгать о
    показанном (ADR 0005)."""
    client.force_login(member)

    response = correct(client, lifts, kind=ContractTerms.Kind.OPERATION)

    assert response.status_code == 403
    assert lifts.attached_terms().kind is None


def test_a_write_to_another_organisations_contract_is_missing_rather_than_forbidden(
    client, administrator, central, make_contract
):
    """404 и на запись, по той же причине, что и на чтение: отличив «нельзя» от «нет
    такого», читатель узнал бы, с кем работает другой клиент платформы (ADR 0006)."""
    theirs = make_contract(central, "Договор с чужим подрядчиком")
    client.force_login(administrator)

    response = correct(client, theirs, kind=ContractTerms.Kind.OPERATION)

    assert response.status_code == 404
    assert theirs.attached_terms().kind is None


def test_an_administrator_of_another_client_is_refused(
    client, django_user_model, downtown, central, lifts
):
    """Право принадлежит паре «сотрудник + организация»: ведущий данные одного клиента
    остаётся обычным читателем у другого (ADR 0005)."""
    stranger = django_user_model.objects.create_user("director-elsewhere")
    OrgMembership.objects.create(user=stranger, org=downtown)
    OrgMembership.objects.create(user=stranger, org=central, is_admin=True)
    client.force_login(stranger)

    _, page = page_of(client, lifts)
    response = correct(client, lifts, kind=ContractTerms.Kind.OPERATION)

    assert edit_form(page) is None
    assert response.status_code == 403


# Правка


def test_every_condition_is_corrected_from_the_contracts_screen(
    client, administrator, lifts, counterparty
):
    """Контрагент, вид, бессрочность, автопролонгация и срок — всё, чем договор является
    сверх своей бумаги. Название, номер и скан правят на странице документа: та отвечает
    «что это за бумага», эта — «какое обязательство и до каких пор»."""
    client.force_login(administrator)

    response = correct(
        client,
        lifts,
        counterparty=str(counterparty.pk),
        kind=ContractTerms.Kind.OPERATION,
        valid_until="2027-03-14",
        auto_prolongs="on",
    )
    lifts.refresh_from_db()
    terms = lifts.attached_terms()

    assert response.status_code == 302
    assert terms.counterparty == counterparty
    assert terms.kind == ContractTerms.Kind.OPERATION
    assert terms.auto_prolongs is True
    assert terms.is_perpetual is False
    assert lifts.valid_until == date(2027, 3, 14)


def test_the_corrected_contract_says_so_in_its_own_header(
    client, administrator, lifts, counterparty
):
    """Подтверждением служит перезагруженный экран: шапка несёт все пять условий, и сказать
    о правке словами было бы нечего."""
    client.force_login(administrator)

    correct(
        client,
        lifts,
        counterparty=str(counterparty.pk),
        kind=ContractTerms.Kind.OPERATION,
        valid_until="2027-03-14",
    )
    _, page = page_of(client, lifts)
    fields = fields_on(page)

    assert fields["kind"] == "Эксплуатация"
    assert fields["genus"] == "Расходный"
    assert fields["counterparty"] == "ТОО «Альфа»"
    assert fields["ending"] == "14.03.2027"


def test_the_form_opens_on_what_is_recorded(client, administrator, downtown, make_contract):
    """Форма, поднявшаяся забывшей заведённое, сохранила бы его прочь: пришедший поправить
    вид не должен терять срок и контрагента."""
    contract = make_contract(
        downtown,
        "Договор на обслуживание лифтов",
        valid_until=date(2027, 3, 14),
        kind=ContractTerms.Kind.OPERATION,
        auto_prolongs=True,
    )
    client.force_login(administrator)

    _, page = page_of(client, contract)

    assert 'value="2027-03-14"' in page
    assert f'value="{ContractTerms.Kind.OPERATION}" selected' in field_of(page, "kind")
    assert "checked" in field_of(page, "auto_prolongs")


def test_a_condition_is_cleared_back_to_unrecorded(
    client, administrator, downtown, make_contract
):
    """Проставленное по ошибке снимается той же формой: вид возвращается в «не заведён», и
    договор снова считается на строке счёта."""
    contract = make_contract(
        downtown, "Договор на обслуживание лифтов", kind=ContractTerms.Kind.OPERATION
    )
    client.force_login(administrator)

    correct(client, contract, kind="")

    assert ContractTerms.objects.get(document=contract).kind is None


def test_a_kind_that_is_not_one_of_the_five_is_refused(client, administrator, lifts):
    """Пять видов и ровно пять: ключ, пришедший из отправки, а не из списка, отвергается
    словами о самом списке."""
    client.force_login(administrator)

    response = correct(client, lifts, kind="трудовой")

    assert response.status_code == 200
    assert lifts.attached_terms().kind is None
    assert "вид" in stated(field_of(response.content.decode(), "kind")).lower()


# Три состояния срока


def test_what_was_entered_reads_on_the_shelf_as_one_of_three_states(
    client, administrator, lifts
):
    """Заведённое читается на полке одним из трёх состояний, и бессрочность с датой конца не
    спорят между собой (ADR 0031): форма отказывает вместо того, чтобы молча выбрать одно."""
    client.force_login(administrator)

    correct(client, lifts, is_perpetual="on")
    _, page = shelf(client)

    assert ending_cell(page, lifts) == "бессрочный"


def test_a_perpetual_contract_with_an_end_date_is_refused(
    client, administrator, downtown, make_contract
):
    """Бессрочный договор конца срока не имеет, и заведённая дата его не отменяет: одна
    пустота на два смысла — то, от чего ADR 0031 и написан, а две заполненности разом — тот
    же спор с другой стороны."""
    contract = make_contract(downtown, "Договор на охрану")
    client.force_login(administrator)

    response = correct(client, contract, valid_until="2027-02-01", is_perpetual="on")
    contract.refresh_from_db()

    assert response.status_code == 200
    assert contract.valid_until is None
    assert contract.attached_terms().is_perpetual is False
    assert "бессрочн" in stated(response.content.decode()).lower()


def test_a_refusal_keeps_everything_that_was_typed(
    client, administrator, lifts, counterparty
):
    """Отказ возвращает экран с причиной на форме и ничего из введённого не теряет: форма,
    перерисованная пустой, стоила бы читателю всего, на что отказ не жаловался."""
    client.force_login(administrator)

    response = correct(
        client,
        lifts,
        valid_until="2027-02-01",
        is_perpetual="on",
        counterparty=str(counterparty.pk),
        counterparty_q="альфа",
        kind=ContractTerms.Kind.OPERATION,
        auto_prolongs="on",
    )
    page = response.content.decode()

    assert 'value="2027-02-01"' in page
    assert 'value="альфа"' in page
    assert f'value="{counterparty.pk}" selected' in page
    assert f'value="{ContractTerms.Kind.OPERATION}" selected' in page
    assert "checked" in field_of(page, "is_perpetual")
    assert "checked" in field_of(page, "auto_prolongs")


def test_the_end_date_replaces_a_perpetuity_that_is_lifted_in_the_same_submission(
    client, administrator, downtown, make_contract
):
    """Одна отправка меняет состояние целиком: бессрочный договор, которому назначили конец,
    перестаёт быть бессрочным тем же нажатием, а не двумя."""
    contract = make_contract(downtown, "Договор на охрану", is_perpetual=True)
    client.force_login(administrator)

    correct(client, contract, valid_until="2027-02-01")
    contract.refresh_from_db()

    assert contract.valid_until == date(2027, 2, 1)
    assert contract.attached_terms().is_perpetual is False


# Контрагент


def test_the_counterparty_is_chosen_out_of_what_a_search_found(
    client, administrator, lifts, counterparty
):
    """Сторону ищут, а не пролистывают: поиск едет параметром на адрес самого договора и
    перерисовывает створку, не трогая экрана вокруг неё."""
    client.force_login(administrator)

    _, page = looking_up(client, lifts, counterparty_q="альфа")

    assert f'value="{counterparty.pk}"' in field_of(page, "counterparty")
    assert counterparty.name in stated(field_of(page, "counterparty"))


def test_a_search_does_not_cost_the_counterparty_already_recorded(
    client, administrator, downtown, make_contract, counterparty
):
    """Уже проставленный контрагент стоит в списке и тогда, когда поиск не нашёл никого:
    иначе искавший зря сохранил бы пустоту на его месте. Выбранное едет с вопросом — так его
    и шлёт створка, — и возвращается выбранным."""
    contract = make_contract(
        downtown, "Договор на обслуживание лифтов", counterparty=counterparty
    )
    client.force_login(administrator)

    _, page = looking_up(
        client,
        contract,
        counterparty_q="такой Стороны нет",
        counterparty=str(counterparty.pk),
    )

    assert f'value="{counterparty.pk}" selected' in field_of(page, "counterparty")


def test_an_address_without_a_search_fills_nothing_in(client, administrator, lifts):
    """Гейт на месте: `?kind=…` без поиска открыл бы форму с видом, которого никто не
    выбирал, — а проставленное поле сохраняют, не взглянув (ADR 0004)."""
    client.force_login(administrator)

    _, page = looking_up(client, lifts, kind=ContractTerms.Kind.SUPPLY)

    assert f'value="{ContractTerms.Kind.SUPPLY}" selected' not in field_of(page, "kind")


# Устройство створки


def test_the_form_carries_no_leftover_template_comments(admin_page):
    """Django не считает многострочный `{# … #}` комментарием и печатает его на экране."""
    assert "{#" not in admin_page


def test_neither_the_title_nor_the_scan_is_asked_for_here(admin_page):
    """Реквизиты документа правят на странице документа, и второе их место было бы второй
    правдой о номере и названии (ADR 0030)."""
    assert 'name="title"' not in admin_page
    assert 'name="doc_no"' not in admin_page
    assert "enctype" not in admin_page


def test_no_sum_is_asked_for(admin_page):
    """Суммы договора нет и на створке: денежная черта стоит там, где её держат восемь ADR."""
    assert "сумма" not in stated(admin_page).lower()
