"""На чём стоят тесты раздела «Договоры».

Корневой `conftest` держит организации, сотрудников и Стороны, сидящие в помещениях, —
ТОО «Альфа» и ИП Петров те самые, через которых читается каждый экран этого этапа, и
второго определения ни у одной из них быть не должно. Здесь стоит то, что принадлежит
договорам: сам договор — документ вида «Договор» с условиями сбоку — и заполнение этих
условий одной строкой.

Фабрика, а не готовый договор: почти каждый тест полки ставит, какие условия заведены и
какие нет, — и это разное от теста к тесту.
"""

import pytest

from documents.models import Document


@pytest.fixture
def make_contract(db):
    """Договор организации: документ вида «Договор» и его условия, заполненные или нет.

    Условия строкой заводит сама модель (ADR 0035), а тест называет лишь те, что кто-то
    завёл: `kind`, `counterparty`, `is_perpetual`, `auto_prolongs` приходят сюда наравне с
    полями документа и раскладываются по двум таблицам здесь, потому что читатель полки
    держит в руках договор, а не его половину.
    """
    conditions = {"kind", "counterparty", "is_perpetual", "auto_prolongs"}

    def _make_contract(org, title, **fields):
        terms_fields = {name: fields.pop(name) for name in conditions & fields.keys()}
        document = Document.objects.create(
            org=org, kind=Document.Kind.CONTRACT, title=title, **fields
        )
        if terms_fields:
            terms = document.attached_terms()
            for name, value in terms_fields.items():
                setattr(terms, name, value)
            terms.save()
        return document

    return _make_contract
