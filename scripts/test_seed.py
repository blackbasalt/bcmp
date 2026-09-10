"""Посев: настоящие Стороны, их учётные карточки и аренды из таблицы управляющей компании.

Наполнение — вымышленные арендаторы Manhattan — проверяется рядом, в `test_lease_filling`.
Здесь проверяется то, что приехало из учётной системы УК и чего выдумывать нельзя: 699
Сторон, чья каждая строка названа колонкой `date_base`, и 271 строка аренд, из которых
заводится ровно та часть, чей арендатор в реестре есть.

Половина проверок стоит над самими файлами и до базы не доходит. Что помещение, названное
в `lease_data.csv`, есть в `space.csv`, и что БИН несёт каждая строка выгрузки, видно в
файле, и увидеть это там лучше, чем после отказа, оставившего базу налитой наполовину.
"""

from datetime import date

import pytest

from leases.models import Lease
from leases.party_choice import found
from parties.models import Org, OrgMembership, Party, PartyRecord

from . import load_real_data

pytestmark = pytest.mark.django_db

#: Кем ведётся база, из которой приехала строка. Три названия в колонке `date_base`, и
#: организация в системе есть только для одного из них.
DOWNTOWN = "ТОО «DOWNTOWN MANAGEMENT»"
OTHER_BASES = ("Asset-Asia ТОО", "ТОО «CO-PROSTRANSTVO»")


def parties():
    return load_real_data.rows("party.csv")


def table():
    return load_real_data.rows("lease_data.csv")


# Сами файлы


def test_every_row_of_the_export_names_the_base_it_came_from():
    """`date_base` — это и есть ответ на «чья эта строка», и пустой он ничего не значит."""
    assert {row["date_base"] for row in parties()} == {DOWNTOWN, *OTHER_BASES}


def test_the_export_is_mostly_the_management_company_s_own():
    """637 своих и 62 чужих — числа, на которых стоит правило полки (ADR 0020)."""
    own = [row for row in parties() if row["date_base"] == DOWNTOWN]

    assert len(own) == 637
    assert len(parties()) - len(own) == 62


def test_every_party_of_the_export_carries_a_bin():
    """Двенадцать цифр без пропусков и без повторов — вся защита от дублей стоит на них."""
    numbers = [row["inn_bin"] for row in parties()]

    assert all(len(number) == 12 and number.isdigit() for number in numbers)
    assert len(set(numbers)) == len(numbers)


def test_the_export_holds_sole_traders_and_natural_persons_apart_from_companies():
    """Пометок рода в колонке `type` две, а не одна: ИП — тоже человек (ADR 0025)."""
    forms = [row["type"].strip() for row in parties()]

    assert forms.count("ИП") == 5
    assert forms.count("ФЛ") == 2


def test_every_let_room_of_the_table_is_a_room_of_the_export():
    """Помещение, которого нет в `space.csv`, посев искал бы и не нашёл посреди прогона."""
    known = {row["code"] for row in load_real_data.rows("space.csv")}

    assert {row["space"] for row in table()} <= known


def test_every_named_landlord_of_the_table_is_a_party_of_the_registry():
    """Арендодателя посев не пропускает и не выдумывает — он обязан быть в выгрузке."""
    named = {row["landlord"] for row in table() if row["landlord"]}

    assert named and named <= {row["inn_bin"] for row in parties()}


def test_the_table_holds_one_lease_per_room_and_tenant():
    """По этой паре посев узнаёт свою же строку на повторном прогоне.

    Две строки на одну пару значили бы, что у одного арендатора в одном помещении два
    срока, — тогда пара перестаёт быть именем строки, и повторный прогон положил бы второй
    слой поверх первого.
    """
    pairs = [(row["space"], row["tenant"]) for row in table()]

    assert len(set(pairs)) == len(pairs)


def test_every_date_of_the_table_is_one_the_seed_can_read():
    """Клетка, написанная днём вперёд, читается посевом как тридцать первый месяц и падает.

    Проверяется над файлом, а не над тем, что завелось: строка с чужим порядком клеток
    сегодня может быть из тех, что пропускаются, и уронит посев в тот день, когда приедет
    выгрузка арендаторов и её арендатор найдётся.

    Что за днём стоит именно тот день, который имела в виду УК, отсюда не видно и не может
    быть видно: `01/09/24` — законное первое сентября и столь же законное девятое января.
    Проверяется читаемость, и обещать больше этот тест не берётся.
    """
    for row in table():
        assert load_real_data.day_of(row["valid_from"]) or not row["valid_from"], row["space"]
        assert load_real_data.day_of(row["valid_to"]) or not row["valid_to"], row["space"]


def test_no_lease_the_seed_enters_ends_before_it_begins():
    """Проверка периода отказывает такую аренду (ADR 0017), и отказ падает посреди посева.

    В файле это одна плохая строка; на модели — база, налитая наполовину.

    Проверяются те строки, что посев заводит, а не все: четыре строки `man-f3-c*` несут
    «с 31.07.26 по 30.07.26» — срок, кончающийся накануне начала. Арендаторов их в реестре
    нет, и посев до них не доходит; какой там срок на самом деле, знает УК, и досочинять
    его посеву нечем — спрашивают в тот день, когда приедет выгрузка арендаторов.
    """
    registry = {row["inn_bin"] for row in parties()}

    for row in table():
        if row["tenant"] not in registry:
            continue
        valid_from = load_real_data.day_of(row["valid_from"])
        valid_to = load_real_data.day_of(row["valid_to"])
        assert valid_to is None or valid_from is None or valid_to >= valid_from, row["space"]


# Стороны и учётные карточки


@pytest.fixture
def sown(db):
    """База после посева Сторон: 699 строк и учётные карточки той организации, что есть."""
    load_real_data.load_parties()
    return Party.objects.all()


@pytest.fixture
def sown_org(sown):
    """Организация, которую завёл сам посев, — DownTown Management из её же выгрузки.

    Фикстуры `downtown` и `member` из корневого `conftest` сюда не годятся: они заводят
    Сторону с тем же БИН, а он уникален — на том и стоит вся защита от дублей. Посев здесь
    не ставится на подготовленную сцену, он и есть сцена.
    """
    return Org.objects.get(party__bin_iin=load_real_data.BASES[DOWNTOWN])


@pytest.fixture
def reader(sown_org, django_user_model):
    """Сотрудник управляющей компании — обычный читатель полки Сторон."""
    user = django_user_model.objects.create_user("engineer")
    OrgMembership.objects.create(user=user, org=sown_org)
    return user


def test_the_seed_enters_every_party_of_the_export(sown):
    assert sown.count() == len(parties())


def test_the_management_company_gets_a_record_for_every_row_of_its_own_base(sown):
    """637 Сторон на полке УК — те, чью строку её же выгрузка назвала своей."""
    assert PartyRecord.objects.count() == 637


def test_a_party_of_another_base_gets_no_record(sown):
    """62 Стороны из чужих баз: организаций для них в системе нет (ADR 0020)."""
    strangers = Party.objects.filter(records__isnull=True)

    assert strangers.count() == 62
    assert {row["clean_name"] for row in parties() if row["date_base"] in OTHER_BASES} == {
        party.name for party in strangers
    }


def test_a_party_without_a_record_reaches_nobody_s_shelf(sown, reader):
    """Полка Сторон — полка учётных карточек, и чужой базе на ней места нет."""
    on_the_shelf = {record.party_id for record in PartyRecord.objects.visible_to(reader)}
    strangers = {party.pk for party in Party.objects.filter(records__isnull=True)}

    assert on_the_shelf
    assert not on_the_shelf & strangers


def test_a_party_without_a_record_is_still_found_by_a_search(sown):
    """Находима поиском при заведении аренды: реестр общесистемный (`party_choice`)."""
    stranger = Party.objects.filter(records__isnull=True).first()

    assert stranger in found(stranger.bin_iin)
    assert stranger in found(stranger.name)


def test_the_five_sole_traders_are_entered_as_natural_persons(sown):
    """ИП — человек: у него нет контактных лиц, а день рождения висит на карточке."""
    numbers = [row["inn_bin"] for row in parties() if row["type"].strip() == "ИП"]

    assert len(numbers) == 5
    assert all(
        Party.objects.get(bin_iin=number).kind == Party.Kind.PERSON for number in numbers
    )


def test_the_seed_keeps_the_legal_form_in_the_name(sown):
    """ОПФ отдельным полем не заводится — она уже суффикс названия (ADR 0025)."""
    assert Party.objects.filter(name="Центр крепежных систем ТОО").exists()


def test_sowing_twice_doubles_neither_the_parties_nor_the_records(sown):
    """Повторный прогон заменяет своё, а не кладёт второй слой."""
    load_real_data.load_parties()

    assert Party.objects.count() == len(parties())
    assert PartyRecord.objects.count() == 637


def test_the_seed_leaves_a_party_entered_in_the_admin_alone(sown, alpha):
    """Сторону, заведённую УК помимо выгрузки, посев не сносит: он сносит только своё.

    ТОО «Альфа» берётся фикстурой корневого `conftest`, а не заводится здесь ещё раз: два
    определения одного юрлица — ровно то, от чего защищает уникальный БИН.
    """
    load_real_data.load_parties()

    assert Party.objects.filter(pk=alpha.pk).exists()


# Аренды из таблицы УК


@pytest.fixture
def spaces_from_the_export(sown_org, build_spaces, export_rows):
    """Все пять БЦ из `space.csv` — те же помещения, которыми живёт рабочая база.

    Целиком, а не одним зданием: пустота Tokyo и Boston — это то, что проверяется, и на
    незаведённых помещениях она была бы пустотой ни о чём.
    """
    return build_spaces(sown_org, export_rows)


#: День, на который посев ставит аренду без срока. Любой подошёл бы — потому он и передаётся.
ANCHOR = date(2026, 3, 2)


@pytest.fixture
def let(spaces_from_the_export):
    return load_real_data.load_leases(ANCHOR)


def test_the_table_enters_the_leases_whose_tenant_is_in_the_registry(let):
    """36 из 271: `party.csv` — выгрузка поставщиков, и арендаторы в неё почти не попали."""
    assert let.entered == 36
    assert Lease.objects.count() == 36


def test_a_lease_whose_tenant_is_not_in_the_registry_is_skipped(let):
    """235 строк не заводятся, и ни одной Стороны ради них не выдумано (ADR 0026)."""
    assert let.skipped == 235
    assert Party.objects.count() == len(parties())


def test_the_seed_reports_how_many_parties_were_missing(let):
    """Число Сторон, а не число строк: 42 арендатора, которых в реестре нет."""
    assert let.missing == 42


def test_the_seed_reports_by_number_and_prints_nothing(spaces_from_the_export, capsys):
    """Отчёт — величина, которую забирает вызвавший, а не строки, пролетевшие в консоли."""
    load_real_data.load_leases(ANCHOR)

    assert capsys.readouterr().out == ""


def test_tokyo_and_boston_are_left_without_a_single_lease(let):
    """Пустой БЦ честнее заполненного неправдой: по пустому идут за выгрузкой арендаторов."""
    empty = Lease.objects.filter(space__building__code__in=("tok", "bos"))

    assert not empty.exists()
    assert {lease.space.building.code for lease in Lease.objects.all()} == {"man", "dub", "gen"}


def test_a_lease_carries_the_term_the_table_names(let):
    """Срок читается датами файла, а не смещениями: это настоящие сроки, а не наполнение."""
    lease = Lease.objects.get(space__code="man-f3-f")

    assert lease.valid_from == date(2026, 1, 1)
    assert lease.valid_to == date(2027, 7, 31)


def test_a_lease_the_table_gives_no_term_for_starts_on_the_day_of_the_seed(let):
    """Четырнадцать помещений Geneva сданы, а срока таблица УК не назвала.

    Днём посева, а не выдуманной датой: арендатор сидит там сегодня, и день, с которого
    это известно, — тот, в который строка приехала. Пустой конец читается «по сей день».
    """
    undated = Lease.objects.filter(valid_from=ANCHOR)

    assert undated.count() == 14
    assert all(lease.valid_to is None for lease in undated)


def test_a_lease_names_the_landlord_the_table_names(let):
    """Арендодатель — роль на аренде, и берётся он из того же реестра Сторон."""
    lease = Lease.objects.get(space__code="man-f2-d")

    assert lease.landlord.bin_iin == "130140009766"


def test_sowing_the_leases_twice_does_not_lay_a_second_layer(let):
    assert load_real_data.load_leases(ANCHOR).entered == 36
    assert Lease.objects.count() == 36


def test_a_lease_entered_in_the_admin_is_left_alone(let, spaces_from_the_export, alpha):
    """То самое правило, ради которого наполнение держит `FILLING_MARK` (ADR 0026)."""
    entered = Lease.objects.create(
        space=spaces_from_the_export["tok-f1-lb"], tenant=alpha, valid_from=date(2026, 1, 1)
    )

    load_real_data.load_leases(ANCHOR)

    assert Lease.objects.filter(pk=entered.pk).exists()
