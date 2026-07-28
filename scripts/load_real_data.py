import csv

from django.contrib.auth.models import User

from dictionary.models import *
from building_passport.models import *


def run():
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

