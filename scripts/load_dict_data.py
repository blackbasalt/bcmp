"""Словари, поставляемые с системой: их наливает эта загрузка и никто больше.

«Поставляется фикстурой» (ADR 0027) читается здесь как «поставляется тем же способом, что и
остальные словари» — поставочный файл рядом с этой загрузкой, а не `loaddata` и не
`dictionary/fixtures/`: заводить второй способ поставки ради трёх справочников значило бы
завести и второй ответ на вопрос «чем налита база».

    uv run python manage.py runscript load_dict_data
"""

import csv
from pathlib import Path

from django.contrib.auth.models import User

from dictionary.models import *

DATA = Path(__file__).parent / "populate_data"


def rows(name):
    """Строки поставочного файла — заголовком, а не номером колонки.

    Отсюда же их берут посев и тесты: файл, прочитанный дважды, однажды разойдётся во втором
    чтении кодировкой или диалектом. Словари, заведённые до этой строки, читают свои файлы
    позиционно и остаются как есть — переписывать их этот тикет не звали.
    """
    with (DATA / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fill_banks():
    """Банки БВУ: БИК в `code`, название в `name`, и ничего больше.

    `bank.csv` несёт ещё `is_license_revocation` и `bik_end_date_bvu`, и они не переезжают:
    обновлять справочник некому и нечем, а через год экран показал бы отозванную лицензию
    действующей (ADR 0022). Сорок три ликвидированных банка едут вместе с остальными, и БИК
    у них пуст — это и значит «этим БИК уже никто не платит».

    Опознаются по `uuid` выгрузки: банк, которому в источнике поправили написание названия,
    должен остаться той же строкой, на которую ссылается заведённый комплект реквизитов.
    """
    for row in rows("bank.csv"):
        DictBank.objects.update_or_create(
            external_id=row["uuid"],
            defaults={
                "code": row["bik"] or None,
                "name": row["bank_name"],
                "short_name": row["bank_name"],
            },
        )


def fill_lines_of_business():
    """Сферы деятельности — около двадцати пяти отраслей, составленных от календаря (ADR 0024).

    Наливается поверх себя, а не сносится и заводится заново, как словари выше: на отрасли
    ссылаются Стороны, и прогон, стирающий таблицу, отобрал бы у них сферу молча — вместе с
    выводом профессионального повода, ради которого справочник и заведён.
    """
    for row in rows("line_of_business.csv"):
        DictLineOfBusiness.objects.update_or_create(
            slug=row["slug"],
            defaults={"name": row["name"], "short_name": row["short_name"]},
        )


def fill_professional_holidays():
    """Календарь профессиональных праздников РК — правилами, а не датами (ADR 0027).

    Пустая клетка в файле — это «эта форма правила не про меня»: у праздника заполнены либо
    число и месяц, либо неделя месяца и день недели, и обе сразу база не примет.

    Источник — приказ Минтруда РК от 29 июня 2023 года № 258 с дополнениями от 11 июня 2024
    года. Поимённо, потому что перечень меняли и будут менять: «День работников связи и
    информации» в 2019 году разошёлся на День работников связи 17 мая и День работников СМИ
    28 июня, и календарь, списанный со старой публикации, поздравил бы связистов чужим днём.
    """
    lines_of_business = {line.slug: line for line in DictLineOfBusiness.objects.all()}

    for row in rows("professional_holiday.csv"):
        line = lines_of_business.get(row["line_of_business"])
        if line is None:
            # Назван и файл, и строка: праздник, повисший в воздухе, некому вывести, и
            # молчаливый пропуск читался бы как «у этой отрасли праздника нет».
            raise KeyError(
                f"professional_holiday.csv: «{row['name']}» ссылается на сферу деятельности "
                f"«{row['line_of_business']}», которой нет в line_of_business.csv"
            )

        DictProfessionalHoliday.objects.update_or_create(
            slug=row["slug"],
            defaults={
                "line_of_business": line,
                "name": row["name"],
                "short_name": row["short_name"],
                "month": int(row["month"]),
                "day": int(row["day"]) if row["day"] else None,
                "week_of_month": int(row["week_of_month"]) if row["week_of_month"] else None,
                "weekday": int(row["weekday"]) if row["weekday"] else None,
            },
        )


def run():
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

    with open("scripts/populate_data/document_role.csv") as file:
        reader = csv.reader(file)
        next(reader)

        DictDocumentRole.objects.all().delete()

        for row in reader:
            c, _ = DictDocumentRole.objects.get_or_create(id=int(row[0]),slug=row[3], name=row[1], short_name=row[2])

    # Три справочника Сторон едут вместе с остальными словарями: банк, сфера деятельности и
    # календарь праздников поставляются с системой и администратору организации не
    # принадлежат — календарь РК одинаков у всех клиентов (ADR 0027). Отрасли раньше
    # праздников: праздник висит на отрасли.
    fill_banks()
    fill_lines_of_business()
    fill_professional_holidays()

