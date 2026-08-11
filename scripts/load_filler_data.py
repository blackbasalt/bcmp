"""Наполнение: десять вымышленных арендаторов и их договоры на Manhattan.

Слой «сроки договоров» и счёт свободного проверены тестами, но на рабочей базе они
показывают пустое здание: договоров в ней нет ни одного, и «свободно 44 из 44»
читается фактом, хотя означает, что фактов не заведено. Эти три файла заводят
наполнение, на котором и слой, и счёт видно работающими.

    uv run python manage.py runscript load_filler_data
    uv run python manage.py runscript load_filler_data --script-args 2026-03-02

Настоящих Сторон наполнение не касается. В `party.csv` лежат 699 Сторон из настоящего
списка, и все они помечены поставщиками; сделать «Центр крепежных систем ТОО»
арендатором значило бы положить в данные ложь, которую кто-нибудь потом прочитает как
правду. Поэтому вымышленные Стороны приходят своими файлами рядом
(`filler_tenant.csv`), а не переклейкой ярлыка на существующих.

Вымышленное помечено и в самой базе: `external_id` вымышленной Стороны начинается с
`FILLING_MARK`, и по этой пометке посев узнаёт прежнее наполнение, когда убирает его.
БИН у неё вдобавок невозможный — месяц 99: он ничего не помечает, он не даёт
вымышленной Стороне занять номер настоящей.

Сроки договоров заданы смещениями в днях от названного дня (`from_days`, `to_days`), а
не датами. Абсолютные даты в файле означали бы, что через полгода после его написания
наполнение перестаёт показывать то, ради чего заведено: «истекает» протухает первым, за
ним «действует». Смещения дают все три краски от какого угодно дня посева.

Посев повторяем: прежнее наполнение удаляется целиком, а потом заводится заново, — и
правило «у помещения не бывает двух арендаторов на один день» (ADR 0007) при повторе не
задевается. Заводится всё обычным путём, `Lease.objects.create()` и
`LeaseSubject.objects.create()`, то есть через ту же проверку, что и админка с формой:
скрипт, пишущий мимо правила, завёл бы данные, на которых слой красит произвольным
цветом. Отказ на одном договоре не роняет посев целиком — договор не заводится, а
причина называется вслух (`Filling.refused`).
"""

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from building_passport.models import Space
from leases.models import Lease, LeaseSubject
from parties.models import Party

DATA = Path(__file__).parent / "populate_data"
TENANTS = DATA / "filler_tenant.csv"
LEASES = DATA / "filler_lease.csv"
SUBJECTS = DATA / "filler_lease_subject.csv"

#: Чем помечена вымышленная сторона. Стоит в `external_id` — том поле, которое и у
#: настоящих сторон говорит, откуда запись взялась, — а не отдельным флагом: второе
#: место, где сказано «это наполнение», однажды разошлось бы с первым. Этой же
#: пометкой посев узнаёт прежнее наполнение, когда убирает его.
FILLING_MARK = "наполнение:"

#: Договор подписывают до того, как он начинает действовать. Двумя неделями: дату
#: подписания показывает карточка договора, и пустая читалась бы «не заведено», а
#: числа в файле нет — вопросов к нему не бывает.
SIGNED_BEFORE = timedelta(days=14)


@dataclass(frozen=True)
class Filling:
    """Что завелось и что не завелось: посев отчитывается числами, а не молчанием."""

    tenants: int
    leases: int
    subjects: int
    #: Договоры, которые не завелись, вместе с причиной — её же словами.
    refused: tuple[str, ...]


@dataclass(frozen=True)
class Sowing:
    """То, чем заводится всякий договор наполнения: день, стороны и помещения.

    Три вещи, которые иначе ходили бы по всему посеву вместе и порознь. День здесь же,
    а не только в `seed`: срок договора считается от него, и разъехаться дню, на который
    считаются сроки, с днём, на который посев отчитался, не с чем.
    """

    anchor: date
    #: Вымышленные стороны по `slug` из файла — тем же ключом их называет договор.
    parties: dict[str, Party]
    #: Помещения по коду — тому же, которым они названы в `space.csv`.
    spaces: dict[str, Space]


def tenants():
    return rows(TENANTS)


def leases():
    return rows(LEASES)


def subjects():
    return rows(SUBJECTS)


def rows(path):
    """Строки посевного файла. Читают их и посев, и тесты — одним чтением на всех."""
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def term(row, anchor: date) -> tuple[date, date | None]:
    """Срок договора на этот день: смещения из файла — датами.

    Правило одно и лежит здесь: посев и проверка над файлом считают срок одинаково, а
    два счёта одного и того же разъехались бы при первой же правке смысла смещений.
    Пустой конец остаётся пустым — он и означает «по сей день».
    """
    return (
        anchor + timedelta(days=int(row["from_days"])),
        anchor + timedelta(days=int(row["to_days"])) if row["to_days"] else None,
    )


def seed(anchor: date) -> Filling:
    """Завести наполнение заново на этот день.

    Организация берётся у помещения, а не называется в файле: договор принимает
    помещения только своей организации (ADR 0009), и названная отдельно она разошлась
    бы с той, которой Manhattan принадлежит на самом деле.

    Помещения ищутся по коду — тому же, которым они названы в `space.csv` и в `id`
    путей на чертеже. Ненайденное помещение договор не заводит вовсе: договор без
    предмета остался бы молча пустой записью, а посев — наполовину наполненной базой.
    """
    _clear_the_previous_filling()
    by_lease = _subjects_by_lease()
    sowing = Sowing(
        anchor=anchor,
        parties={row["slug"]: _fictional_party(row) for row in tenants()},
        spaces=_spaces_named(by_lease),
    )

    entered: dict[str, Lease] = {}
    refused: list[str] = []
    subject_count = 0
    for row in leases():
        subject_rows = by_lease[row["number"]]
        stopped = _what_stops(row, subject_rows, sowing, entered)
        if stopped:
            refused.append(f"{row['number']}: {stopped}")
            continue
        try:
            with transaction.atomic():
                lease = _enter(row, subject_rows, sowing, entered.get(row["prolongs"]))
        except ValidationError as refusal:
            refused.append(f"{row['number']}: {' '.join(refusal.messages)}")
            continue
        entered[row["number"]] = lease
        subject_count += len(subject_rows)

    return Filling(
        tenants=len(sowing.parties),
        leases=len(entered),
        subjects=subject_count,
        refused=tuple(refused),
    )


def run(*args):
    """Точка входа `runscript`; день посева — первым аргументом, по умолчанию сегодня.

    День называется снаружи не ради тестов: посев, повторённый назавтра, сдвинет все
    сроки на день, и снимок базы, сделанный вчера, восстановить будет нечем.

    Сегодня спрашивается тем же, чем его спрашивает экран (`timezone.localdate`):
    посев, взявший свой день другим способом, однажды разошёлся бы с тем днём, на
    который экран считает вакансию.
    """
    filled = seed(date.fromisoformat(args[0]) if args else timezone.localdate())
    print(
        f"наполнение: арендаторов {filled.tenants}, договоров {filled.leases}, "
        f"предметов {filled.subjects}"
    )
    for refusal in filled.refused:
        print(f"не заведён {refusal}")


def _clear_the_previous_filling():
    """Убрать прежнее наполнение — договоры вымышленных сторон и ничего сверх них.

    Сами стороны остаются: они заводятся заново тем же `external_id`, а удалённая и
    заведённая заново сторона меняла бы ключ при каждом посеве.

    Удаляется с конца цепочки пролонгаций: продлевающий договор ссылается на прежний и
    удалить его не даёт (`PROTECT`) — ссылку рвать молча нечем. Цикл кончается, когда
    удалять становится нечего: если на наполнение сослался настоящий договор, прежнее
    остаётся, и заводимое поверх него будет отказано по пересечению — с названной
    причиной, а не молча.
    """
    standing = Lease.objects.filter(tenant__external_id__startswith=FILLING_MARK)
    removed = -1
    while removed:
        removed, _ = standing.filter(prolonged_by__isnull=True).delete()


def _fictional_party(row) -> Party:
    """Вымышленная сторона: заводится один раз и потом узнаётся по своей пометке."""
    party, _ = Party.objects.update_or_create(
        external_id=f"{FILLING_MARK}{row['slug']}",
        defaults={
            "kind": row["kind"],
            "name": row["name"],
            "bin_iin": row["bin_iin"],
        },
    )
    return party


def _subjects_by_lease() -> dict[str, list[dict]]:
    """Предметы по договорам: файл называет их строками, а заводятся они вместе."""
    named: dict[str, list[dict]] = {row["number"]: [] for row in leases()}
    for row in subjects():
        named[row["lease"]].append(row)
    return named


def _spaces_named(by_lease) -> dict[str, Space]:
    """Помещения, названные наполнением, — одним запросом на весь посев."""
    codes = {row["space_code"] for rows in by_lease.values() for row in rows}
    return {space.code: space for space in Space.objects.filter(code__in=codes)}


def _what_stops(row, subject_rows, sowing, entered) -> str | None:
    """Почему договор не заводится вовсе: нечего сдавать, некому показывать, нечего продлевать.

    Пересечения здесь нет: его знает модель, и спрашивать её второй раз отсюда значило
    бы написать правило периода дважды.

    Отсутствие продлеваемого договора останавливает продление целиком, а не роняет
    одну ссылку: пролонгация — продолжение прежней аренды, и заведённая без неё она
    превратилась бы в обычный договор, по которому истории ставки уже не собрать.
    """
    if not subject_rows:
        return "предмета в файле нет, а договор без предмета — пустая запись."
    missing = [
        subject["space_code"]
        for subject in subject_rows
        if subject["space_code"] not in sowing.spaces
    ]
    if missing:
        return f"помещений в базе нет — {', '.join(missing)}."
    if any(sowing.spaces[subject["space_code"]].org_id is None for subject in subject_rows):
        return "помещение не принадлежит организации, а договор без неё не бывает."
    if row["prolongs"] and row["prolongs"] not in entered:
        return f"продлеваемый договор {row['prolongs']} не заведён."
    return None


def _enter(row, subject_rows, sowing, prolongs) -> Lease:
    """Договор со всеми его предметами — как его завела бы форма, одним действием."""
    valid_from, valid_to = term(row, sowing.anchor)
    lease = Lease.objects.create(
        org=sowing.spaces[subject_rows[0]["space_code"]].org,
        tenant=sowing.parties[row["tenant"]],
        valid_from=valid_from,
        valid_to=valid_to,
        number=row["number"],
        signed_at=valid_from - SIGNED_BEFORE,
        prolongs=prolongs,
    )
    for subject in subject_rows:
        LeaseSubject.objects.create(
            lease=lease,
            space=sowing.spaces[subject["space_code"]],
            rate=Decimal(subject["rate"]),
            area_m2=Decimal(subject["area_m2"]),
        )
    return lease
