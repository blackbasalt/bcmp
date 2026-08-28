"""Посев рабочей базы: настоящие Стороны, помещения и паспорта — и наполнение аренд.

The first four blocks load what the УК actually handed over. The fifth is наполнение: a
dozen fictional арендаторы sitting in Manhattan, without which «сдано X из Y», the находки
and the отбор «свободно» have nothing to be looked at on before the УК enters anything.

    uv run python manage.py runscript load_real_data
"""

import csv
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.utils import timezone

from dictionary.models import *
from building_passport.models import *
from leases.models import Lease
from parties.models import *

DATA = Path(__file__).parent / "populate_data"

#: What marks a fictional Сторона. It stands in `external_id` — the field that already says
#: where a row came from — rather than in a flag of its own: a second place saying «это
#: наполнение» would one day disagree with the first. By the same mark the наполнение finds
#: its own leavings when it clears them, so a repeat run replaces them instead of laying a
#: second наполнение on top.
FILLING_MARK = "наполнение:"


def rows(name):
    """Строки посевного файла. Читают их и посев, и тесты — одним чтением на всех."""
    with (DATA / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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
    with (DATA / "party.csv").open() as file:
        reader = csv.reader(file)
        next(reader)

        Party.objects.all().delete()

        for row in reader:
            kind="company"
            if row[3]=="ФЛ":
                kind = "person"
            c, _ = Party.objects.get_or_create(
                    kind=kind,
                    name=row[2],
                    bin_iin=row[4],
                    )
        dt = Party.objects.get(bin_iin="180540035878")
        o,_ = Org.objects.get_or_create(
            party = dt,
                )

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

    fill_leases()
