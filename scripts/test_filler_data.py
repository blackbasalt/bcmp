"""Наполнение: десять вымышленных арендаторов и их договоры на Manhattan.

Проверяется не то, что файлы прочитаны, а то, ради чего они заведены. Слой «сроки
договоров» должен показать все три краски, счёт свободного — не ноль ни в помещениях,
ни в метрах, и оба ответа должны получиться на посевных данных, а не только на тех,
что тест завёл себе сам. Поэтому здание здесь собирается из того же `space.csv`, из
которого живёт рабочая база: наполнение, разъехавшееся с посевными помещениями,
заведётся молча и покрасит пустоту.

Половина проверок к базе не обращается вовсе — они стоят над самими файлами. Что
помещение не сдано дважды на один день и что вымышленный БИН не занят настоящей
Стороной, видно в файле, и увидеть это лучше до того, как правило проверит модель:
отказ на середине посева оставляет базу наполовину наполненной.

Срок договора здесь не считается заново: смещения превращает в даты тот же
`load_filler_data.term`, которым их считает посев. Второй счёт того же разошёлся бы с
первым, и разошёлся бы молча — проверка над файлом стала бы проверять себя.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from building_passport.models import Space
from building_passport.plan_layer import EXPIRING, LEASED, VACANT, LeaseTermLayer
from building_passport.vacancy import vacancy_on
from leases.models import Lease
from parties.models import Party

from . import load_filler_data

SPACES = load_filler_data.DATA / "space.csv"
PARTIES = load_filler_data.DATA / "party.csv"

#: День, на который наполнение заводится в тестах. Любой: смысл смещений в файле в
#: том, что три краски получаются от какого угодно дня, — а названный день делает
#: проверяемым и то, что уже кончилось, и то, что кончится через полтора месяца.
ANCHOR = date(2026, 3, 2)


def leasable_of_manhattan():
    """Арендопригодные помещения Manhattan по посевному файлу — все 44."""
    return {
        row["code"]: row
        for row in load_filler_data.rows(SPACES)
        if row["building"] == "man" and row["is_leasable"] == "TRUE"
    }


def periods(anchor):
    """Срок каждого договора наполнения на этот день — тем же счётом, что и посев."""
    return {
        row["number"]: load_filler_data.term(row, anchor)
        for row in load_filler_data.leases()
    }


# Сами файлы


def test_the_file_holds_ten_fictional_tenants_and_every_one_of_them_rents_something():
    """Десять — и ни одного заведённого впустую: сторона без договора арендатором не станет."""
    tenants = load_filler_data.tenants()
    renting = {row["tenant"] for row in load_filler_data.leases()}

    assert len(tenants) == 10
    assert {row["slug"] for row in tenants} == renting


def test_no_fictional_tenant_borrows_a_bin_from_a_real_party():
    """Вымышленный БИН не должен совпасть с настоящим — иначе в данных появится ложь."""
    real = {row["inn_bin"] for row in load_filler_data.rows(PARTIES)}
    fictional = [row["bin_iin"] for row in load_filler_data.tenants()]

    assert len(set(fictional)) == len(fictional)
    assert not set(fictional) & real


def test_the_real_parties_keep_their_supplier_labelling():
    """699 Сторон остаются поставщиками: наполнение приходит рядом, а не поверх них."""
    real = load_filler_data.rows(PARTIES)

    assert len(real) == 699
    assert {row["role"].strip() for row in real} == {"Поставщики"}


def test_every_leased_space_is_a_leasable_space_of_manhattan():
    """Предметом бывает только арендопригодное — и только там, где есть нутро."""
    leasable = leasable_of_manhattan()

    assert {row["space_code"] for row in load_filler_data.subjects()} <= set(leasable)


def test_no_space_is_let_twice_on_one_day():
    """Правило пересечения (ADR 0007) держится в самом файле, а не только на модели."""
    term = periods(ANCHOR)
    let = {}
    for row in load_filler_data.subjects():
        began, ended = term[row["lease"]]
        for other_began, other_ended in let.setdefault(row["space_code"], []):
            assert ended is not None and ended < other_began or (
                other_ended is not None and other_ended < began
            ), f"{row['space_code']} сдано дважды на один день"
        let[row["space_code"]].append((began, ended))


def test_a_prolonging_lease_comes_after_the_one_it_continues():
    """Продлеваемый договор должен быть заведён раньше: посев читает файл сверху вниз.

    Иначе пролонгация не заведётся вовсе — и это лучше, чем завестись договором без
    ссылки, — но заводиться она должна.
    """
    entered = []
    for row in load_filler_data.leases():
        assert not row["prolongs"] or row["prolongs"] in entered
        entered.append(row["number"])


def test_a_good_number_of_leasable_spaces_is_left_without_any_lease():
    """Вакансия должна быть числом, которое стоит читать, а не нулём."""
    named = {row["space_code"] for row in load_filler_data.subjects()}
    leasable = leasable_of_manhattan()

    assert len(leasable) - len(named) >= 10


# Наполнение в базе


@dataclass(frozen=True)
class Drawn:
    """Контур ровно в том, чем его берёт слой: помещение и путь. Плана здесь нет.

    Чертежей у посевных данных нет — их заводят файлом в админке, — а спросить слой о
    трёх красках надо. Слою же от контура нужны только помещение и путь.
    """

    space: Space
    path_d: str = "M0 0 H1 V1 H0 Z"

    @property
    def space_id(self):
        return self.space.pk


@pytest.fixture
def manhattan_seeded(downtown):
    """Manhattan из посевного `space.csv` — то самое здание, что и в рабочей базе.

    Помещения заводятся в порядке файла: вложенное стоит в нём после того, внутри
    которого оно лежит, и родитель к этому моменту уже заведён.
    """
    building = Space.objects.create(
        org=downtown, type="building", code="man", name="Manhattan"
    )
    entered = {"man": building}
    for row in load_filler_data.rows(SPACES):
        if row["building"] != "man":
            continue
        entered[row["code"]] = Space.objects.create(
            org=downtown,
            type=row["type"],
            parent=entered.get(row["parent"]),
            building=building,
            code=row["code"],
            name=row["name"],
            floor_number=int(row["floor_number"]) if row["floor_number"] else None,
            area_m2=Decimal(row["area_m2"]) if row["area_m2"] else None,
            is_common=row["is_common"] == "TRUE",
            is_leasable=row["is_leasable"] == "TRUE",
        )
    return entered


@pytest.fixture
def filled(manhattan_seeded):
    """Наполнение, заведённое на названный день, — то, что проверяют экраны."""
    return load_filler_data.seed(ANCHOR)


def test_the_seeded_tenants_are_marked_as_filling_and_the_real_parties_are_not(
    filled, manhattan_seeded
):
    """Вымышленную сторону видно по её `external_id`: наполнение названо наполнением."""
    tenants = Party.objects.filter(external_id__startswith=load_filler_data.FILLING_MARK)

    assert filled.tenants == 10
    assert tenants.count() == 10
    assert {lease.tenant_id for lease in Lease.objects.all()} <= {
        party.pk for party in tenants
    }


def test_the_lease_term_layer_shows_all_three_paints_on_the_seeded_data(
    filled, manhattan_seeded
):
    """То, ради чего наполнение и заведено: свободно, действует и истекает разом."""
    contours = [
        Drawn(space) for space in manhattan_seeded.values() if space.is_leasable
    ]
    painting = LeaseTermLayer(day=ANCHOR, leases=Lease.objects.all()).apply(contours)

    assert set(painting.legend) == {VACANT, LEASED, EXPIRING}


def test_every_floor_roomy_enough_for_three_paints_shows_all_three(
    filled, manhattan_seeded
):
    """Слой показывают этажом, а не зданием: три краски нужны на самом экране.

    Спрашивается это у каждого этажа, которому есть чем ответить: на пятом
    арендопригодных всего два, и трёх красок на нём не бывает ни при каком наполнении.
    """
    for floor in (space for space in manhattan_seeded.values() if space.type == "floor"):
        leasable = [
            space
            for space in manhattan_seeded.values()
            if space.is_leasable and space.floor_number == floor.floor_number
        ]
        if len(leasable) < 3:
            continue
        painting = LeaseTermLayer(day=ANCHOR, leases=Lease.objects.all()).apply(
            Drawn(space) for space in leasable
        )
        assert set(painting.legend) == {VACANT, LEASED, EXPIRING}, floor.name


def test_at_least_one_seeded_lease_has_already_ended(filled, manhattan_seeded):
    """Кончившийся договор остаётся: «кто сидел здесь в прошлом году» имеет ответ."""
    ended = Lease.objects.filter(valid_to__lt=ANCHOR)

    assert ended.exists()
    assert all(lease.subjects.exists() for lease in ended)


def test_a_prolongation_points_at_the_lease_it_continues_and_changes_the_rate(
    filled, manhattan_seeded
):
    """Продление — новый договор со ссылкой на прежний, и ставка при нём другая."""
    new = Lease.objects.filter(prolongs__isnull=False).first()

    assert new is not None
    assert new.tenant_id == new.prolongs.tenant_id
    assert new.prolongs.valid_to < new.valid_from
    assert [subject.space_id for subject in new.subjects.all()] == [
        subject.space_id for subject in new.prolongs.subjects.all()
    ]
    assert new.subjects.first().rate != new.prolongs.subjects.first().rate


def test_vacancy_is_not_zero_and_not_everything_in_either_spaces_or_metres(
    filled, manhattan_seeded
):
    """Счёт свободного стоит на договорах и говорит о здании, а не о пустой базе."""
    counted = vacancy_on(ANCHOR, manhattan_seeded.values(), Lease.objects.all())

    assert 0 < counted.free_count < counted.leasable_count
    assert Decimal("0.00") < counted.free_m2 < counted.leasable_m2
    assert counted.lease_count > 0


def test_seeding_twice_leaves_one_set_of_leases_and_no_overlap(filled, manhattan_seeded):
    """Посев повторяем: прежнее наполнение уходит, и правило пересечения не задето."""
    again = load_filler_data.seed(ANCHOR)

    assert again == filled
    assert again.refused == ()
    assert Lease.objects.count() == again.leases
