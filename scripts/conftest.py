"""Помещения посевных файлов — одной постройкой на оба посевных набора тестов.

`test_lease_filling` ставит наполнение на Manhattan, `test_seed` — настоящие аренды на все
пять БЦ, и обоим нужны те же помещения, которыми живёт рабочая база. Две сборки одного и
того же `space.csv` разошлись бы молча: наполнение легло бы на помещения, которых посев не
знает, и ни один тест об этом не сказал бы.
"""

from decimal import Decimal

import pytest

from building_passport.models import Space

from . import load_real_data


@pytest.fixture
def build_spaces(db):
    """Помещения из `space.csv` — родителями вперёд, потому что порядок в файле не обещан.

    Отбор строк передаётся вызывающим: Manhattan одному, все пять БЦ другому. Родитель,
    оставшийся за отбором, становится пустым — Manhattan сам по себе висит на участке, а
    участка в отборе одного БЦ нет, — и корнем тогда встаёт то, что отобрали.

    Дальше ставится всё, что есть в строке, — площадь, номер этажа и оба флага, с которых
    читается вид помещения: полки ставят условие на каждое из них, и помещение, заведённое
    без них, отвечало бы не тем, чем настоящее.
    """

    def _build_spaces(org, rows):
        pending = list(rows)
        within = {row["code"] for row in pending}
        spaces = {}
        while pending:
            deferred = []
            for row in pending:
                if row["parent"] in within and row["parent"] not in spaces:
                    deferred.append(row)
                    continue
                spaces[row["code"]] = Space.objects.create(
                    org=org,
                    parent=spaces.get(row["parent"]),
                    building=spaces.get(row["building"]),
                    type=row["type"],
                    code=row["code"],
                    name=row["name"],
                    floor_number=int(row["floor_number"]) if row["floor_number"] else None,
                    area_m2=Decimal(row["area_m2"]) if row["area_m2"] else None,
                    is_common=row["is_common"] == "TRUE" if row["is_common"] else None,
                    is_leasable=row["is_leasable"] == "TRUE" if row["is_leasable"] else None,
                )
            assert len(deferred) < len(pending), "помещение ссылается на несуществующего родителя"
            pending = deferred
        return spaces

    return _build_spaces


@pytest.fixture
def export_rows():
    """Строки `space.csv` — тем же чтением, которым их берёт сам посев."""
    return load_real_data.rows("space.csv")
