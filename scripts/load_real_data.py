import csv

from django.contrib.auth.models import User

from dictionary.models import *
from building_passport.models import *
from parties.models import *

def run():
    with open("scripts/populate_data/building_passport.csv") as file:
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
    """
    with open("scripts/populate_data/party.csv") as file:
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

    with open('scripts/populate_data/user.csv') as file:
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

    with open("scripts/populate_data/space.csv") as file:
        reader = csv.reader(file)
        next(reader)

        Space.objects.all().delete()

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
"""
