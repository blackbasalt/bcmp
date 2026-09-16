"""Наполнение: вымышленные поставщики и расходные договоры с ними.

Проверяется не то, что файлы прочитались, а то, ради чего они написаны. Полке договоров
нечего показать, пока УК не завела ни одного договора, — а реестра договоров у неё в
выгрузке нет вовсе (спека 0007), — и неудобные формы строк тут и есть всё дело: договор,
кончающийся через месяц, договор на автопролонгации, переживший свой конец срока,
бессрочный, договор без срока и скан из пачки, которому не проставили и вида. Каждая из них
закреплена здесь по имени, потому что каждая выглядит плохими данными тому, кто станет
наводить в файле порядок.

Половина проверок базы не касается вовсе — они стоят над самими файлами. Что вымышленный
БИН не оказался номером настоящей Стороны и что каждый названный поставщик в файле есть,
видно в файле, и там это видеть лучше, чем после отказа, оставившего базу заполненной
наполовину.

Доходную половину полки наполняет `fill_leases`, и о ней здесь нет ни слова: её собственные
проверки стоят рядом, в `test_lease_filling`.
"""

from datetime import date, timedelta

import pytest

from contracts import genus
from documents.models import ContractTerms, Document
from parties.models import Party

from . import load_real_data

pytestmark = pytest.mark.django_db

#: День, на который наполнение заводится в тестах. Годился бы любой — ради того сроки и
#: держатся смещениями, — но названный делает «кончится через месяц» и «кончилось две недели
#: назад» проверяемыми вообще.
ANCHOR = date(2026, 3, 2)


def contracts():
    return load_real_data.rows("contract.csv")


def suppliers():
    return load_real_data.rows("supplier.csv")


def real_bins():
    """Настоящие БИНы — те, что вымышленный занять не должен."""
    return {row["inn_bin"] for row in load_real_data.rows("party.csv")}


def terms_of(title):
    return Document.objects.get(title=title).attached_terms()


# Сами файлы


def test_the_filling_holds_a_handful_of_contracts():
    """Горсть: довольно для неудобных форм, мало, чтобы прочесть за один присест."""
    assert 5 <= len(contracts()) <= 12


def test_no_fictional_supplier_borrows_a_bin_from_a_real_party():
    """БИН у них невозможный — месяц 99, — чтобы он не мог оказаться номером настоящей.

    699 Сторон из `party.csv` приехали из настоящего списка контрагентов, и 698 помечены в
    нём ролью «Поставщики». Вымышленный поставщик, надевший чужой номер, положил бы в данные
    ложь, которую кто-нибудь потом прочитает как правду (ADR 0026).
    """
    fictional = [row["bin_iin"] for row in suppliers()]

    assert len(set(fictional)) == len(fictional)
    assert not set(fictional) & real_bins()


def test_no_fictional_supplier_borrows_a_bin_from_a_fictional_tenant():
    """Наполнений два, а реестр Сторон один: поставщик и арендатор с одним БИН были бы одной
    Стороной, севшей в помещение и подписавшей договор на охрану."""
    tenants = {row["bin_iin"] for row in load_real_data.rows("tenant.csv")}

    assert not {row["bin_iin"] for row in suppliers()} & tenants


def test_every_named_supplier_is_in_the_file_beside_it():
    """Договор, назвавший поставщика, которого в файле нет, уронил бы наполнение на середине."""
    named = {row["supplier"] for row in contracts() if row["supplier"]}

    assert named and named <= {row["slug"] for row in suppliers()}


def test_every_fictional_supplier_actually_signed_something():
    """Сторона, заведённая и не подписавшая ничего, — не поставщик, а мусор."""
    assert {row["slug"] for row in suppliers()} == {
        row["supplier"] for row in contracts() if row["supplier"]
    }


def test_every_kind_in_the_file_is_an_expense_one():
    """Доходную половину наполняет `fill_leases` своими восемнадцатью номерами. Договор
    аренды, заведённый здесь, был бы вторым её изложением — и без аренд, то есть арендой,
    которой никто не сидит."""
    named = [row["kind"] for row in contracts() if row["kind"]]

    assert named
    assert all(genus.STANDS_ON[kind] == genus.EXPENSE for kind in named)


def test_the_file_holds_a_contract_whose_kind_nobody_filled_in():
    """Пачка сканов попадает на полку раньше, чем кому-нибудь проставят вид (ADR 0035), и
    наполнение, проставившее вид всем, скрыло бы находку «вид не заведён у N»."""
    assert [row for row in contracts() if not row["kind"]]


# Что наполнение кладёт в базу


@pytest.fixture
def filled(downtown):
    load_real_data.fill_contracts(ANCHOR)
    return downtown


def test_every_contract_of_the_file_reaches_the_shelf(filled):
    """Каждая строка заведена, и каждая — документ вида «Договор» своей организации."""
    entered = Document.objects.filter(kind=Document.Kind.CONTRACT)

    assert entered.count() == len(contracts())
    assert {contract.org_id for contract in entered} == {filled.pk}


def test_every_contract_carries_its_terms(filled):
    """Строка условий заводится на каждый договор, заполненная или нет (ADR 0035)."""
    assert ContractTerms.objects.count() == len(contracts())


def test_no_real_party_is_credited_with_a_contract(filled):
    """Ни одному настоящему поставщику не приписано договора, которого он не подписывал."""
    counterparties = ContractTerms.objects.exclude(counterparty=None)

    assert counterparties.exists()
    assert all(
        terms.counterparty.external_id.startswith(load_real_data.FILLING_MARK)
        for terms in counterparties
    )


def test_a_contract_ends_within_the_next_ninety_days(filled):
    """Ради этого договора полка и заведена: тот, что кончается на глазах. Девяносто дней —
    то самое окно, которым отбор будет спрашивать «что кончается», и наполнение, ни разу в
    него не попавшее, показало бы это условие пустым."""
    ending_soon = [
        contract
        for contract in Document.objects.filter(kind=Document.Kind.CONTRACT)
        if contract.valid_until and ANCHOR < contract.valid_until <= ANCHOR + timedelta(days=90)
    ]

    assert ending_soon


def test_a_contract_prolongs_itself_past_its_own_end(filled):
    """Договор, продлевающийся сам, на полке остаётся и говорит об этом (ADR 0031). Конец
    срока у него позади: продлившийся молча — ложная тревога, которую строка и снимает."""
    prolonging = [terms for terms in ContractTerms.objects.all() if terms.auto_prolongs]

    assert prolonging
    assert any(terms.document.valid_until < ANCHOR for terms in prolonging)


def test_a_contract_is_perpetual(filled):
    """Второе из трёх состояний срока: конца нет по самому соглашению."""
    perpetual = ContractTerms.objects.filter(is_perpetual=True)

    assert perpetual.exists()
    assert all(terms.document.valid_until is None for terms in perpetual)


def test_a_contract_has_no_term_at_all(filled):
    """Третье состояние, и находка «срок не заведён у N», которую полка о нём называет."""
    assert Document.objects.filter(
        kind=Document.Kind.CONTRACT, valid_until=None, terms__is_perpetual=False
    ).exists()


def test_a_contract_has_no_kind_at_all(filled):
    """И вторая находка: скан из пачки, которому вида ещё не проставили."""
    assert Document.objects.filter(kind=Document.Kind.CONTRACT, terms__kind=None).exists()


def test_running_the_filling_twice_replaces_it_rather_than_doubling_it(filled):
    """Наполнение узнаёт своё по метке и заводит поверх себя, а не вторым слоем."""
    load_real_data.fill_contracts(ANCHOR)

    assert Document.objects.filter(kind=Document.Kind.CONTRACT).count() == len(contracts())
    assert Party.objects.filter(
        external_id__startswith=load_real_data.FILLING_MARK
    ).count() == len(suppliers())


def test_the_filling_leaves_a_contract_entered_by_hand_alone(filled):
    """Договор, заведённый УК в админке, повторный прогон не трогает (ADR 0026)."""
    by_hand = Document.objects.create(
        org=filled, kind=Document.Kind.CONTRACT, title="Договор, заведённый руками"
    )

    load_real_data.fill_contracts(ANCHOR)

    assert Document.objects.filter(pk=by_hand.pk).exists()
