"""Посев рабочей базы: настоящие Стороны, помещения, паспорта и аренды — и наполнение.

The first blocks load what the УК actually handed over. The last one is наполнение: a dozen
fictional арендаторы sitting in Manhattan, without which «сдано X из Y», the находки and the
отбор «свободно» have nothing to be looked at on before the УК enters anything.

Стороны и аренды посев сносить перестал: он опознаёт своё по тому, чем его зовёт сама
выгрузка — БИН у Стороны, пара «помещение + арендатор» у аренды, — и заводит поверх себя.
Сплошное `Party.objects.all().delete()`, стоявшее здесь прежде, сносило вместе со своим и
заведённое УК в админке (ADR 0026).

Помещения — ещё нет: `run()` по-прежнему начинает их блок со сплошного
`Space.objects.all().delete()`, а `Lease.space` — `CASCADE`, так что полный прогон посева
уносит и аренды УК. Заменить снос заведением поверх себя тут нечем: `Space.code` не
уникален, и ключа, по которому посев узнал бы свою же строку, у помещения пока нет. Это
отдельное решение и отдельный тикет; правило ADR 0026 до тех пор держится на `load_parties`
и `load_leases`, вызванных сами по себе.

    uv run python manage.py runscript load_real_data
"""

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from dictionary.models import *
from building_passport.models import *
from leases.models import Lease
from parties.models import *

# Читается тем же чтением, что и словари: посев берёт свои файлы из той же папки и той же
# строкой, и второе чтение однажды разошлось бы с первым в кодировке или в диалекте.
from .load_dict_data import DATA, rows

#: What marks a fictional Сторона. It stands in `external_id` — the field that already says
#: where a row came from — rather than in a flag of its own: a second place saying «это
#: наполнение» would one day disagree with the first. By the same mark the наполнение finds
#: its own leavings when it clears them, so a repeat run replaces them instead of laying a
#: second наполнение on top.
FILLING_MARK = "наполнение:"

#: Кем ведётся база, из которой приехала строка выгрузки, — и БИН той организации, если она
#: в системе есть. Колонка `date_base` зовёт базу её названием, а система знает организации
#: по БИН, и мостик между двумя именованиями стоит здесь строкой, а не выводится сличением
#: названий: «ТОО «DOWNTOWN MANAGEMENT»» и «DownTown Management ТОО» — одно и то же, и
#: сличение, которое сегодня их сводит, завтра сведёт не то.
#:
#: Баз в выгрузке три, а строка тут одна: организаций для «Asset-Asia ТОО» и
#: «ТОО «CO-PROSTRANSTVO»» в системе нет, и 62 их Стороны заливаются без учётной карточки —
#: находимы поиском, ни на чьей полке (ADR 0020). Asset-Asia при этом стоит арендодателем на
#: четырнадцати строках аренд, и это роль на аренде, а не основание завести организацию.
DOWNTOWN_BASE = "ТОО «DOWNTOWN MANAGEMENT»"
BASES = {DOWNTOWN_BASE: "180540035878"}

#: Пометки рода в колонке `type` выгрузки, за которыми стоит человек, а не организация.
#: Их две, а не одна: ИП — это человек, и загрузчик, знавший только «ФЛ», записывал всех
#: пятерых организациями. Род спрашивает экран Стороны, и от него зависит, есть ли блок
#: контактных лиц и где висит день рождения (ADR 0025).
PERSONAL_FORMS = {"ФЛ", "ИП"}


@dataclass(frozen=True)
class LeaseReport:
    """Чем посев отчитывается об арендах: сколько завёл, сколько пропустил и кого не нашёл.

    Величиной, которую забирает вызвавший, а не строками в консоли (ADR 0026): пропуск
    двухсот тридцати пяти строк — это то, что читают числом и сверяют с ожидаемым, а
    консоль посева и без того полна.

    `missing` считает Стороны, а не строки: сорок два арендатора, которых в реестре нет, —
    это одна недостающая выгрузка арендаторов, и знать надо её размер.
    """

    entered: int
    skipped: int
    missing: int


def day_of(value):
    """Дата таблицы УК — `01/01/26`, месяц первым. Пустая клетка остаётся пустой.

    Даты здесь настоящие и оттого абсолютные, в отличие от сроков наполнения: те держатся
    смещениями, чтобы прошлые аренды не переставали быть прошлыми, а эти приехали из
    договоров, и сдвигать их значило бы их сочинять.
    """
    return datetime.strptime(value, "%m/%d/%y").date() if value else None


def load_parties():
    """699 Сторон выгрузки и учётные карточки той организации, чья это выгрузка.

    Колонка `date_base` называет, чья каждая строка, и посев её больше не выбрасывает: 637
    строк «ТОО «DOWNTOWN MANAGEMENT»» получают учётную карточку этой организации и тем
    попадают на её полку. Полку нельзя вывести из связей с БЦ — `PartyRole` пуст, аренд
    тридцать пять, и правило «показывать связанных» дало бы управляющей компании пустой
    экран при 637 её собственных поставщиках (ADR 0020).

    Названием становится `clean_name`, а не `name`: ОПФ уже стоит в нём суффиксом, и
    отдельным полем не заводится (ADR 0025).

    Опознаются Стороны по БИН — он уникален, все 699 строк его несут, и одно юрлицо есть
    одна строка. Оттого посеву и не нужно ничего сносить: он заводит своё поверх себя, а
    Сторону, заведённую УК помимо выгрузки, не трогает вовсе.
    """
    export = rows("party.csv")

    parties = {}
    for row in export:
        parties[row["inn_bin"]], _ = Party.objects.update_or_create(
            bin_iin=row["inn_bin"],
            defaults={
                "kind": (
                    Party.Kind.PERSON
                    if row["type"].strip() in PERSONAL_FORMS
                    else Party.Kind.COMPANY
                ),
                "name": row["clean_name"].strip(),
            },
        )

    # Организация заводится после Сторон и из них же: `Org` — тонкий слой над Стороной, и
    # управляющая компания стоит в собственной выгрузке такой же строкой, как её поставщики.
    orgs = {}
    for base, bin_iin in BASES.items():
        orgs[base], _ = Org.objects.get_or_create(party=parties[bin_iin])

    for row in export:
        org = orgs.get(row["date_base"])
        if org is None:
            continue
        PartyRecord.objects.get_or_create(party=parties[row["inn_bin"]], org=org)


def load_leases(day=None):
    """Аренды из таблицы УК: заводится та строка, чей арендатор в реестре Сторон есть.

    Аренда, чьего арендатора там нет, не заводится, и Стороны ради неё не выдумывается:
    имён арендаторов в выгрузке нет вовсе, только БИН, и 42 Стороны с именем-БИНом дали бы
    полку из строк вида «030841005109», отвечающую на «кто сидит в каб305» бессмысленно, но
    уверенно. Пустой Tokyo честнее заполненного неправдой (ADR 0026). Цена названа заранее:
    из 271 строки заводится 36, и Tokyo с Boston остаются без единой аренды.

    Заводится всё обычным путём, через `Lease.objects`, то есть через ту же проверку
    периода, что и админка с формой, — довод целиком в `fill_leases`.

    Своё посев узнаёт по паре «помещение + арендатор» — по ней в таблице УК ровно одна
    строка — и заводит поверх себя. Аренду, заведённую УК в админке, он не трогает: то же
    правило, ради которого наполнение держит `FILLING_MARK`.
    """
    day = day or timezone.localdate()
    registry = {party.bin_iin: party for party in Party.objects.exclude(bin_iin=None)}

    entered = 0
    skipped = 0
    missing = set()
    for row in rows("lease_data.csv"):
        tenant = registry.get(row["tenant"])
        if tenant is None:
            skipped += 1
            missing.add(row["tenant"])
            continue

        Lease.objects.update_or_create(
            space=Space.objects.get(code=row["space"]),
            tenant=tenant,
            defaults={
                "landlord": registry[row["landlord"]] if row["landlord"] else None,
                "area_m2": Decimal(row["area_m2"]) if row["area_m2"] else None,
                # Днём посева, а не выдуманной датой: четырнадцать помещений Geneva сданы, а
                # срока таблица УК не назвала. Арендатор сидит там сегодня, и день, с
                # которого это известно, — тот, в который строка приехала; пустой конец и
                # без того читается «по сей день».
                "valid_from": day_of(row["valid_from"]) or day,
                "valid_to": day_of(row["valid_to"]),
            },
        )
        entered += 1

    return LeaseReport(entered=entered, skipped=skipped, missing=len(missing))


def term(row, day):
    """Срок аренды на этот день: смещения из файла — датами.

    The периоды are held as offsets rather than as dates because absolute ones would mean
    that half a year after the file was written the наполнение stops showing what it exists
    for: the прошлые аренды stop being прошлые, and «по сей день» stops being today's
    answer. Offsets give the same shapes from whatever day the посев is run.

    Пустой конец остаётся пустым — он и означает «по сей день».
    """
    return (
        day + timedelta(days=int(row["from_days"])),
        day + timedelta(days=int(row["to_days"])) if row["to_days"] else None,
    )


def fill_leases(day=None):
    """Наполнение: вымышленные арендаторы и их аренды на Manhattan.

    Настоящих Сторон это не касается. 699 Сторон из `party.csv` пришли из настоящего списка
    контрагентов; сделать «Центр крепежных систем ТОО» арендатором значило бы положить в
    данные ложь, которую кто-нибудь потом прочитает как правду. Поэтому вымышленные приходят
    своим файлом рядом, помечены `FILLING_MARK`, и БИН у них невозможный, с месяцем 99: он
    не помечает, он не даёт занять номер настоящей Стороны.

    Арендодателем же названа настоящая Сторона — та, которой БЦ принадлежит на самом деле,
    или та, которая ведёт его в своё имя: все пять БЦ принадлежат «Компании системных бизнес
    технологий», а данные ведёт DownTown Management. У части аренд он пуст: таблица УК не
    всегда говорит, в чьё имя помещение сдано.

    Заводится всё обычным путём, `Lease.objects.create()`, то есть через ту же проверку
    периода, что и админка с формой: скрипт, пишущий мимо правила, завёл бы данные, на
    которых экран считает как попало.
    """
    day = day or timezone.localdate()

    # Прежнее наполнение — и только оно: аренду, заведённую УК в админке, посев не трогает.
    Lease.objects.filter(tenant__external_id__startswith=FILLING_MARK).delete()

    tenants = {}
    for row in rows("tenant.csv"):
        tenants[row["slug"]], _ = Party.objects.update_or_create(
            external_id=FILLING_MARK + row["slug"],
            defaults={
                "kind": row["kind"],
                "name": row["name"],
                "bin_iin": row["bin_iin"],
            },
        )

    for row in rows("lease.csv"):
        valid_from, valid_to = term(row, day)
        Lease.objects.create(
            space=Space.objects.get(code=row["space"]),
            tenant=tenants[row["tenant"]],
            landlord=Party.objects.get(bin_iin=row["landlord"]) if row["landlord"] else None,
            area_m2=Decimal(row["area_m2"]) if row["area_m2"] else None,
            rate=Decimal(row["rate"]) if row["rate"] else None,
            contract_no=row["contract_no"] or None,
            valid_from=valid_from,
            valid_to=valid_to,
        )


def run():
    load_parties()
    dt = Party.objects.get(bin_iin=BASES[DOWNTOWN_BASE])

    with (DATA / "user.csv").open() as file:
        reader = csv.reader(file)
        next(reader)

        User.objects.all().delete()

        for row in reader:
            user = User.objects.create_user(
                username=row[0],
                first_name=row[1],
                last_name=row[2],
                password=row[6],
            )
            if row[5]=="TRUE":
                user.is_staff = True
            else:
                user.is_staff = False

            if row[4]=="TRUE":
                user.is_superuser = True
            else:
                user.is_superuser = False

            user.save()

    with (DATA / "space.csv").open() as file:
        reader = csv.reader(file)
        next(reader)

        Space.objects.all().delete()

        dtp = Party.objects.get(bin_iin="180540035878")
        dto = Org.objects.get(party = dt)

        for row in reader:
            par = None
            subt=None
            building=None
            area=None
            is_common=None
            is_leasable=None
            floor_number=None
            if row[1]:
                par = Space.objects.get(code=row[1])
            if row[3]:
                subt = DictSpaceSubtype.objects.get(slug=row[3])
            if row[7]:
                building = Space.objects.get(code=row[7])
            if row[8]:
                floor_number = row[8]
            if row[9]:
                area = row[9]

            if row[10] and row[11]:
                if row[10]=="TRUE":
                    is_common=True
                else:
                    is_common=False
                if row[11]=="TRUE":
                    is_leasable=True
                else:
                    is_leasable=False

            c, _ = Space.objects.get_or_create(
                    org=dto,
                    parent=par,
                    name=row[4],
                    type=row[2],
                    subtype=subt,
                    building=building,
                    is_common=is_common,
                    is_leasable=is_leasable,
                    area_m2=area,
                    floor_number=floor_number,
                    code=row[5],
                    )
    with (DATA / "building_passport.csv").open() as file:
        reader = csv.reader(file)
        next(reader)

        BuildingPassport.objects.all().delete()

        for row in reader:
            space = Space.objects.get(code=row[0])
            owner = None
            operator = None
            designer = None
            builder = None

            if row[41]:
                owner = Party.objects.get(bin_iin=row[41])

            if row[42]:
                operator = Party.objects.get(bin_iin=row[42])
            if row[43]:
                designer = Party.objects.get(bin_iin=row[43])

            if row[44]:
                builder = Party.objects.get(bin_iin=row[44])
            c  = BuildingPassport.objects.create(
                    space=space,
                    building_passport_naming=row[1],
                    region=row[2],
                    region_district=row[3],
                    settlement=row[4],
                    settlement_district=row[5],
                    address=row[6],
                    cadastral_no=row[7],
                    inventory_number=row[8],
                    intended_purpose=row[9],
                    property_category=row[10],
                    series_project_type=row[11],
                    number_of_floors=row[12],
                    building_footprint=row[13],
                    building_volume=row[14],
                    total_area=row[15],
                    balcony_loggia_area=row[16],
                    living_area=row[17],
                    non_residential_area=row[18],
                    apartments_number=row[19],
                    total_rooms=row[20],
                    wall_material=row[21],
                    year_built=row[22],
                    physical_wear_tear=row[23],
                    registry_number=row[24],
                    passport_prepared=row[25],
                    signer_name=row[26],
                    lat=row[27],
                    lon=row[28],
                    building_class=row[31],
                    floors_above=row[32],
                    floors_below=row[33],
                    structural_scheme=row[34],
                    owner_party=owner,
                    operator_party=operator,
                    designer_party=designer,
                    builder_party=builder,
                    )

    # Отчёт уходит в журнал, а не в консоль: пропуск двухсот тридцати пяти строк — это
    # число, которое сверяют с ожидаемым, а `print` посреди посева читает только тот, кто
    # смотрит в терминал ровно в эту секунду (ADR 0026).
    report = load_leases()
    logging.getLogger(__name__).info(
        "аренды из таблицы УК: заведено %s, пропущено %s, Сторон не хватило %s",
        report.entered,
        report.skipped,
        report.missing,
    )

    fill_leases()
