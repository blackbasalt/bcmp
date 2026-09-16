"""Заведение договора на полке — одна отправка, документ и условия вместе.

Шов тот же, которым проверяется вся полка: граница HTTP адреса `/contracts/`. Тесты
отправляют створку тестовым клиентом от лица сотрудника с известным членством и проверяют
наблюдаемое — что легло в базу, каким кодом ответил запрос, что написано на вернувшейся
форме и что стоит на обеих полках после неё. Ниже HTTP шва нет: сама форма — не отдельный
предмет проверки, её читают через экран, на котором она стоит.

Опора в разметке — `data-entry` на самой створке, наравне с `data-upload` на полке
документов и `data-entry` на полке Сторон. Это договор экрана: он показывает, предложено ли
заведение, — а сотруднику без флага администратора эта разметка не достаётся вовсе.

Поля едут под приставкой створки (`entry-…`), и приставка эта не украшение: полка уже
спрашивает у адреса и вид, и контрагента — своим отбором, — и два вопроса, делящие одно имя,
отвечали бы друг за друга.
"""

import hashlib
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documents.models import ContractTerms, Document
from parties.models import OrgMembership

from .test_shelf import contracts_on, count_line, shelf, stated

pytestmark = pytest.mark.django_db

#: Приставка, которой створка метит свои поля в адресе и в отправке, — та же, что в форме.
ENTRY = "entry"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Сканы ложатся во временный каталог, а не в рабочую копию."""
    settings.MEDIA_ROOT = tmp_path


def pdf(text="скан договора"):
    """Файл размером со скан и формой PDF: важны первые байты."""
    return f"%PDF-1.4\n{text}".encode()


def scan(name="dogovor.pdf", content=None):
    """Скан, как он приходит в отправке."""
    return SimpleUploadedFile(name, pdf(name) if content is None else content)


def submission(**fields):
    """Отправка створки: поля под её приставкой."""
    return {f"{ENTRY}-{name}": value for name, value in fields.items()}


def enter(client, **fields):
    """Завести договор — по тому же адресу, по которому полку и читают."""
    return client.post(reverse("contracts:contract_list"), submission(**fields))


def looking_up(client, **fields):
    """Поиск Стороны: тот же адрес, вопрос в нём, и створка перерисована с найденным."""
    response = client.get(reverse("contracts:contract_list"), submission(**fields))
    return response, response.content.decode()


def entry_form(page):
    """Створка заведения — или ничего, если её не предложили."""
    return page if 'data-entry="contracts"' in page else None


def field_of(page, name):
    """Разметка одного поля створки — чтобы спросить, что в нём стоит."""
    return next(
        (part for part in page.split("<fieldset") if f'name="{ENTRY}-{name}"' in part), ""
    )


@pytest.fixture
def admin_page(client, administrator):
    """Пустая полка глазами администратора: экран, на котором створка и стоит.

    Пустая не для краткости: заводят договор как раз тогда, когда на полке его нет, и вопросы
    о самой створке — что она спрашивает и чего не спрашивает — задаются именно этому экрану.
    """
    client.force_login(administrator)
    _, page = shelf(client)
    return page


# Кому створка достаётся


def test_an_administrator_is_offered_the_form(admin_page):
    """Договор заводит администратор организации, и заводит он его на полке: там, где о
    договорах читают, и туда же возвращается отказ."""
    assert entry_form(admin_page) is not None


def test_a_reader_without_the_flag_is_offered_no_form(client, member, downtown, make_contract):
    """Действия, которого сотруднику не выполнить, ему и не предлагают: показанная форма,
    отклоняющая отправку, читается как поломка экрана (ADR 0005)."""
    make_contract(downtown, "Договор на обслуживание лифтов")
    client.force_login(member)

    _, page = shelf(client)

    assert entry_form(page) is None
    assert "Завести договор" not in stated(page)


def test_a_submission_from_a_reader_without_the_flag_is_refused(client, member, counterparty):
    """403, а не 404: раздел этому сотруднику показан, и «его нет» было бы неправдой о том,
    что уже на экране. Скрывают чужие данные, а не собственную нехватку прав (ADR 0005)."""
    client.force_login(member)

    response = enter(client, title="Договор поставки картриджей")

    assert response.status_code == 403
    assert not Document.objects.exists()


def test_an_anonymous_visitor_is_sent_to_login(client):
    """Створка — не обход входа, которого требует каждый экран раздела."""
    response = enter(client, title="Договор поставки картриджей")

    assert response.status_code == 302
    assert reverse("login") in response["Location"]
    assert not Document.objects.exists()


# Одна отправка


def test_an_administrator_enters_a_contract_and_its_terms_in_one_submission(
    client, administrator, downtown, counterparty
):
    """Документ и условия вместе: название, номер, дата, срок, контрагент, вид и два
    признака — одной формой. Новый договор с поставщиком перестаёт требовать Django admin."""
    client.force_login(administrator)

    response = enter(
        client,
        title="Договор поставки картриджей",
        doc_no="ТМЦ-2026/11",
        issued_at="2026-02-01",
        valid_until="2027-02-01",
        counterparty=str(counterparty.pk),
        kind=ContractTerms.Kind.SUPPLY,
        auto_prolongs="on",
    )
    contract = Document.objects.get(title="Договор поставки картриджей")
    terms = contract.attached_terms()

    assert response.status_code == 302
    assert contract.kind == Document.Kind.CONTRACT
    assert contract.org == downtown
    assert contract.doc_no == "ТМЦ-2026/11"
    assert contract.issued_at == date(2026, 2, 1)
    assert contract.valid_until == date(2027, 2, 1)
    assert terms.counterparty == counterparty
    assert terms.kind == ContractTerms.Kind.SUPPLY
    assert terms.auto_prolongs is True
    assert terms.is_perpetual is False


def test_the_contract_entered_opens_on_its_own_screen(client, administrator, counterparty):
    """Заведённый договор не возвращается на полку: следом открывается его собственный
    экран — там и дозаполняют то, чего форма не спросила, и он же служит подтверждением."""
    client.force_login(administrator)

    response = enter(client, title="Договор поставки картриджей")
    contract = Document.objects.get(title="Договор поставки картриджей")

    assert response["Location"] == reverse("contracts:contract_detail", args=[contract.pk])


def test_the_contract_entered_reaches_both_shelves(client, administrator):
    """Договор — это документ вида «Договор» (ADR 0030), и заведённый одной формой он стоит
    на обеих полках: иначе «Показано 12 из 637 документов» солгало бы о таблице, которую
    считает."""
    client.force_login(administrator)

    enter(client, title="Договор поставки картриджей")
    contract = Document.objects.get(title="Договор поставки картриджей")
    _, contracts_page = shelf(client)
    documents_page = client.get(reverse("documents:document_list")).content.decode()

    assert contracts_on(contracts_page) == [str(contract.pk)]
    assert "Договор поставки картриджей" in stated(documents_page)


def test_a_contract_reaches_the_shelf_before_its_kind_is_known(client, administrator):
    """Вид можно оставить пустым: пачка сканов попадает на полку раньше, чем кому-нибудь
    проставят вид (ADR 0035), и форма, требующая его, держала бы их снаружи. Незаведённый
    вид — не молчание, а число на строке счёта."""
    client.force_login(administrator)

    enter(client, title="Скан договора без вида")
    contract = Document.objects.get(title="Скан договора без вида")
    _, page = shelf(client)

    assert contract.attached_terms().kind is None
    assert contracts_on(page) == [str(contract.pk)]
    assert "вид не заведён у 1" in count_line(page)


def test_a_contract_may_be_entered_with_nothing_but_a_title(client, administrator):
    """Договор обогащается со временем: форма, требующая всего сразу, держала бы известное
    название снаружи, пока ищут номер и скан. Обязательно одно — название, потому что полку
    читают по названиям."""
    client.force_login(administrator)

    response = enter(client, title="Договор, о котором известно одно название")

    assert response.status_code == 302
    assert Document.objects.filter(title="Договор, о котором известно одно название").exists()


def test_a_contract_without_a_title_is_refused_with_the_reason_on_the_form(
    client, administrator
):
    """Отказ возвращает тот же экран с причиной на форме, а не пустую строку на полке."""
    client.force_login(administrator)

    response = enter(client, title="", doc_no="ТМЦ-2026/11")
    page = response.content.decode()

    assert response.status_code == 200
    assert not Document.objects.exists()
    assert "название" in stated(field_of(page, "title")).lower()
    assert 'value="ТМЦ-2026/11"' in page


# Три состояния срока


def test_a_perpetual_contract_with_an_end_date_is_refused(client, administrator):
    """Состояний срока три, и два разом не бывает (ADR 0031): бессрочность и дата конца
    спорят между собой, а полка отвечает на «когда кончается» одним ответом. Ни одна форма
    такого спора не заводит — и эта отказывает словами, а не молча выбирает победителя."""
    client.force_login(administrator)

    response = enter(
        client, title="Договор на охрану", valid_until="2027-02-01", is_perpetual="on"
    )
    page = stated(response.content.decode())

    assert response.status_code == 200
    assert not Document.objects.exists()
    assert "бессрочн" in page.lower()


def test_a_refusal_keeps_everything_that_was_typed(client, administrator, counterparty):
    """Отказ не стоит читателю набранного: перерисованная пустой форма стоила бы и номера, и
    даты, и выбранного контрагента — то есть всего, на что отказ не жаловался."""
    client.force_login(administrator)

    response = enter(
        client,
        title="Договор на охрану",
        doc_no="ЭКС-2026/07",
        issued_at="2026-02-01",
        valid_until="2027-02-01",
        is_perpetual="on",
        counterparty=str(counterparty.pk),
        counterparty_q="альфа",
        kind=ContractTerms.Kind.OPERATION,
        auto_prolongs="on",
    )
    page = response.content.decode()

    assert 'value="Договор на охрану"' in page
    assert 'value="ЭКС-2026/07"' in page
    assert 'value="2026-02-01"' in page
    assert 'value="2027-02-01"' in page
    assert 'value="альфа"' in page
    assert f'value="{counterparty.pk}" selected' in page
    assert f'value="{ContractTerms.Kind.OPERATION}" selected' in page
    assert "checked" in field_of(page, "is_perpetual")
    assert "checked" in field_of(page, "auto_prolongs")


def test_a_perpetual_contract_is_entered_when_no_end_date_is_given(client, administrator):
    """Бессрочность сама по себе — не спор, а один из трёх ответов: конца срока нет по самому
    соглашению."""
    client.force_login(administrator)

    enter(client, title="Договор на охрану", is_perpetual="on")
    contract = Document.objects.get(title="Договор на охрану")

    assert contract.valid_until is None
    assert contract.attached_terms().is_perpetual is True


# Скан


def test_the_scan_is_stored_with_the_contract(client, administrator):
    """Скан кладут вместе с условиями, а не второй отправкой на странице документа: бумага и
    обязательство приходят в руки разом."""
    client.force_login(administrator)

    enter(client, title="Договор поставки картриджей", scan=scan())
    contract = Document.objects.get(title="Договор поставки картриджей")

    assert contract.file_uri
    assert contract.file_uri.read() == pdf("dogovor.pdf")
    assert contract.file_hash


def test_a_file_that_is_not_a_scan_is_refused_by_its_content(client, administrator):
    """Формат решается содержимым, а не именем, — тем же правилом, каким его решает пачка:
    переименованный `.exe` сканом не становится."""
    client.force_login(administrator)

    response = enter(
        client,
        title="Договор поставки картриджей",
        scan=scan("dogovor.pdf", b"MZ\x90\x00 not a pdf"),
    )
    page = response.content.decode()

    assert response.status_code == 200
    assert not Document.objects.exists()
    assert "PDF" in stated(field_of(page, "scan"))


def test_the_scan_is_recognised_by_the_next_batch(client, administrator, downtown):
    """Отпечаток содержимого кладётся рядом с файлом тем же чтением, каким его считает пачка:
    им пакетная загрузка и узнаёт скан, который уже лежит на полке. Отказа по нему здесь нет
    — повторный файл пачка называет сообщением, а не отказом, и второе решение о том же
    рядом с первым было бы вторым ответом на один вопрос."""
    client.force_login(administrator)

    enter(client, title="Договор поставки картриджей", scan=scan())
    contract = Document.objects.get(title="Договор поставки картриджей")

    assert contract.file_hash == hashlib.sha256(pdf("dogovor.pdf")).hexdigest()


def test_a_refusal_says_the_scan_has_to_be_chosen_again(client, administrator):
    """Всё набранное отказ возвращает, а файл вернуть некому: значения в `<input type="file">`
    не вписать, и браузер выбранный путь разметке не отдаёт. Молчание тут прочиталось бы как
    «файл на месте», и договор завёлся бы без скана, который прикладывали дважды."""
    client.force_login(administrator)

    response = enter(client, title="", scan=scan())

    assert not Document.objects.exists()
    assert "Файл выбирают заново" in stated(response.content.decode())


def test_a_refusal_without_a_file_says_nothing_about_one(client, administrator):
    """Строка о файле, которого не выбирали, отправила бы читателя искать потерю, которой не
    было."""
    client.force_login(administrator)

    response = enter(client, title="")

    assert "Файл выбирают заново" not in stated(response.content.decode())


# Контрагент


def test_the_counterparty_is_chosen_out_of_what_a_search_found(
    client, administrator, counterparty
):
    """Сторону ищут, а не пролистывают: в реестре 699 строк, и список по ним — прокрутка, а
    не выбор. Поиск едет параметром в адресе полки и перерисовывает створку."""
    client.force_login(administrator)

    _, page = looking_up(client, counterparty_q="альфа")

    assert f'value="{counterparty.pk}"' in field_of(page, "counterparty")
    assert counterparty.name in stated(field_of(page, "counterparty"))


def test_a_search_carries_back_what_was_already_typed(client, administrator, counterparty):
    """Поиск шлёт с собой всю форму, и форма возвращается той же: искать контрагента не
    стоит уже вписанного названия и номера, чего бы из ответа ни взяли."""
    client.force_login(administrator)

    _, page = looking_up(
        client, counterparty_q="альфа", title="Договор на охрану", doc_no="ЭКС-2026/07"
    )

    assert 'value="Договор на охрану"' in page
    assert 'value="ЭКС-2026/07"' in page


def test_an_address_without_a_search_fills_nothing_in(client, administrator):
    """Гейт на месте: `?entry-title=…` без поиска открыл бы форму с названием, которого
    никто не набирал, — а проставленное поле сохраняют, не взглянув (ADR 0004)."""
    client.force_login(administrator)

    _, page = looking_up(client, title="Название, которого никто не набирал")

    assert "Название, которого никто не набирал" not in page


def test_the_shelf_search_does_not_fill_the_entry_form_in(
    client, administrator, counterparty
):
    """Отбор полки и створка заведения спрашивают об одном и том же — о виде и о
    контрагенте, — и делят один адрес. Приставка их и разводит: суженная до эксплуатации
    полка не проставляет вид новому договору."""
    client.force_login(administrator)

    _, page = shelf(client, kind=ContractTerms.Kind.OPERATION, counterparty=counterparty.pk)

    assert f'value="{ContractTerms.Kind.OPERATION}" selected' not in field_of(page, "kind")
    assert "selected" not in field_of(page, "counterparty")


def test_a_party_of_no_record_of_ours_is_not_on_the_list(client, administrator, petrov):
    """Контрагента выбирают из Сторон своей учётной карточки: «с кем мы имеем дело» — вопрос
    о знании, и отвечает на него полка Сторон, а не реестр (ADR 0020)."""
    client.force_login(administrator)

    _, page = looking_up(client, counterparty_q="Петров")

    assert str(petrov.pk) not in field_of(page, "counterparty")
    assert "Не нашлось" in stated(page)


def test_a_counterparty_off_the_list_is_refused_in_the_readers_own_words(
    client, administrator, petrov
):
    """Ключ, пришедший из отправки, а не из списка: Стороны нет вовсе или её нет на полке
    этой организации — сказано одинаково, потому что различить их значило бы сказать
    читателю, что есть у другого клиента (ADR 0006)."""
    client.force_login(administrator)

    response = enter(
        client, title="Договор поставки картриджей", counterparty=str(petrov.pk)
    )
    page = stated(response.content.decode())

    assert not Document.objects.exists()
    assert "Такой Стороны среди ваших нет" in page


# Чья это будет бумага


def test_an_administrator_of_one_client_is_not_asked_whose_contract_it_is(
    admin_page, downtown
):
    """Список из единственного значения повторял бы ведущему одного клиента то, что он и так
    знает, — тем же доводом, каким полка заводит или не заводит колонку «Организация»."""
    assert 'name="entry-org"' not in admin_page


def test_an_administrator_of_two_clients_names_the_organisation(
    client, django_user_model, downtown, central, counterparty
):
    """Вывести ответ не из чего: здания в этой форме нет, в отличие от пачки документов, где
    БЦ и говорит, чья это полка (ADR 0010). Отказать вместо вопроса значило бы оставить
    администратора двух клиентов вовсе без заведения договора."""
    both = django_user_model.objects.create_user("director-of-two")
    OrgMembership.objects.create(user=both, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=both, org=central, is_admin=True)
    client.force_login(both)

    _, page = shelf(client)
    enter(client, title="Договор поставки картриджей", org=str(central.pk))

    assert 'name="entry-org"' in page
    assert Document.objects.get(title="Договор поставки картриджей").org == central


def test_an_organisation_this_employee_does_not_administer_is_refused(
    client, administrator, central
):
    """Чужая организация не становится своей оттого, что её ключ вписали в отправку: список
    проверяет то же, что показывает."""
    client.force_login(administrator)

    enter(client, title="Договор поставки картриджей", org=str(central.pk))

    assert Document.objects.get(title="Договор поставки картриджей").org != central


# Устройство створки


def test_the_form_stands_open_over_an_empty_shelf(admin_page):
    """Раскрыта там, где ей есть что делать: над пустой полкой — это то место, где
    отсутствие договоров замечают."""
    assert "<details" in admin_page
    assert "open" in admin_page.split('data-entry="contracts"')[1].split(">")[0]


def test_the_form_stands_shut_over_a_shelf_an_otbor_emptied(
    client, administrator, downtown, make_contract
):
    """Полка, опустошённая отбором, пустой полкой не является: сузивший её до ничего ищет
    договор, а не заводит его."""
    make_contract(downtown, "Договор на обслуживание лифтов")
    client.force_login(administrator)

    _, page = shelf(client, q="такого договора нет")

    assert "open" not in page.split('data-entry="contracts"')[1].split(">")[0]


def test_the_form_stands_open_with_a_refusal_at_hand(client, administrator):
    """Причина, спрятанная под заголовком, — причина, которой никто не видит."""
    client.force_login(administrator)

    response = enter(client, title="")
    page = response.content.decode()

    assert "open" in page.split('data-entry="contracts"')[1].split(">")[0]


def test_the_entry_form_carries_no_leftover_template_comments(admin_page):
    """Django не считает многострочный `{# … #}` комментарием и печатает его на экране."""
    assert "{#" not in admin_page


def test_no_sum_is_asked_for(admin_page):
    """Суммы договора нет и здесь: денежная черта стоит там, где её держат восемь ADR, и
    форма, спрашивающая сумму, завела бы её первой."""
    assert "сумма" not in stated(admin_page).lower()
