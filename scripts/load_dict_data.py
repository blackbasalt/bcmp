import csv

from django.contrib.auth.models import User

from dictionary.models import *


def run():
    with open("scripts/populate_data/building.csv") as file:
        reader = csv.reader(file)
        next(reader)

        DictBuilding.objects.all().delete()

        for row in reader:
            c, _ = DictBuilding.objects.get_or_create(name=row[0], short_name=row[1], code=row[2])

    with open("scripts/populate_data/system.csv") as file:
        reader = csv.reader(file)
        next(reader)

        DictSystem.objects.all().delete()

        for row in reader:
            print(row[1])
            if row[0]:
                par = DictSystem.objects.get(name=row[0])
                flag = False
                if row[5]=="TRUE":
                    flag=True
                c, _ = DictSystem.objects.get_or_create(parent=par, name=row[1], short_name=row[1], is_leaf=flag)
            else:
                c, _ = DictSystem.objects.get_or_create(name=row[1], short_name=row[1])

    with open("scripts/populate_data/space_subtype.csv") as file:
        reader = csv.reader(file)
        next(reader)

        DictSpaceSubtype.objects.all().delete()

        for row in reader:
            print(row[1])
            c, _ = DictSpaceSubtype.objects.get_or_create(type=row[0], slug=row[1], name=row[2], short_name=row[2], description=row[7],grp=row[4])

