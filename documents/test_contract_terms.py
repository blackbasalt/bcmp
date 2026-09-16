"""Условия договора — строка сбоку от документа, и то, что её заводит и держит на месте.

Обычный шов этого проекта — HTTP, и здесь его нет почти нигде намеренно: экранов у договора
пока не построено, а правила, которые этот этап заводит, стоят на модели — там, где скрипт
получит их в тех же словах, что и будущая форма (ADR 0035). Форма правки документа вида не
спрашивает вовсе (`DocumentParticularsForm` держит пять полей, и `kind` среди них нет), так
что отказ «сначала очисти условия» другим концом и не достать.

Через HTTP проверено ровно одно — пакетная загрузка, потому что про неё ADR 0035 и написан:
сорок сканов, попавших на полку раньше, чем кто-нибудь проставит им вид, должны нести условия
с первой секунды, и путь, которым они заводятся, — единственный, кроме рук.

Правила рода (`contracts/genus.py`) здесь нет и не будет: его читают экраны, и экраны его
проверяют — как у `space_kind`, `plan_completeness` и `occupancy`.
"""

from importlib import import_module

import pytest
from django.apps import apps as installed
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documents.models import ContractTerms, Document

pytestmark = pytest.mark.django_db

#: Заполнение, которое миграция делает уже лежащим договорам. Достаётся из самой миграции, а
#: не переписывается сюда: переписанное правило — второе изложение одного, и разошлось бы оно
#: молча, ровно в тот день, когда первое исправят.
give_every_contract_its_terms = import_module(
    "documents.migrations.0008_contract_terms"
).give_every_contract_its_terms


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Загруженное ложится во временный каталог, а не в рабочую копию."""
    settings.MEDIA_ROOT = tmp_path


def contract(org, title="Договор аренды №17"):
    """Документ вида «Договор», заведённый руками, — и ничего, кроме него."""
    return Document.objects.create(org=org, kind=Document.Kind.CONTRACT, title=title)


def filled(document, **conditions):
    """Заполнить условия договора — и вернуть тот же документ."""
    terms = document.attached_terms()
    for field, value in conditions.items():
        setattr(terms, field, value)
    terms.save()
    return document


# Строка условий заводится сама


def test_a_contract_entered_by_hand_gets_its_terms_with_nobody_asking(downtown):
    """Строка заводится сразу, пустая: вид проставят потом, а потерять договор нельзя."""
    document = contract(downtown)

    terms = document.attached_terms()

    assert terms is not None
    assert terms.kind is None
    assert terms.counterparty_id is None
    assert not terms.is_perpetual
    assert not terms.auto_prolongs


def test_the_terms_of_a_fresh_contract_read_as_empty(downtown):
    """Пустая строка так о себе и говорит — на ней стоит отказ смены вида."""
    assert not contract(downtown).attached_terms().filled()


def test_a_contract_carried_across_in_a_batch_gets_its_terms(client, administrator):
    """Сорок сканов пачкой попадают на полку раньше, чем узнан их вид (ADR 0035)."""
    client.force_login(administrator)

    client.post(
        reverse("documents:document_list"),
        {
            "files": [SimpleUploadedFile("Договор аренды №17.pdf", b"%PDF-1.4\nskan")],
            "kind": Document.Kind.CONTRACT,
        },
    )

    assert Document.objects.get().attached_terms() is not None


def test_a_document_of_another_kind_carries_no_terms(downtown):
    """Условия — у договора и ни у чего больше: акт с ними был бы подписью, которая врёт."""
    act = Document.objects.create(org=downtown, kind=Document.Kind.ACT, title="Акт")

    assert act.attached_terms() is None
    assert ContractTerms.objects.count() == 0


def test_a_document_that_becomes_a_contract_gets_its_terms_then(downtown):
    """Вид проставлен не при загрузке, а после — строка заводится в тот же миг."""
    act = Document.objects.create(org=downtown, kind=Document.Kind.ACT, title="Акт")

    act.kind = Document.Kind.CONTRACT
    act.save()

    assert act.attached_terms() is not None


# Вид документа уходит с «Договора» — или не уходит


def test_the_kind_moves_freely_while_the_terms_are_empty(downtown):
    """Пустые условия не сирота: ронять нечего, и вид меняется без разговора."""
    document = contract(downtown)

    document.kind = Document.Kind.ACT
    document.save()

    document.refresh_from_db()
    assert document.kind == Document.Kind.ACT
    assert ContractTerms.objects.count() == 0
    assert document.attached_terms() is None


def test_the_kind_refuses_to_leave_a_contract_whose_terms_are_filled(downtown, alpha):
    """Переименовать «Договор» в «Акт» значило бы осиротить контрагента (ADR 0035)."""
    document = filled(contract(downtown), counterparty=alpha)

    document.kind = Document.Kind.ACT
    with pytest.raises(ValidationError) as refusal:
        document.save()

    assert "контрагент" in str(refusal.value)
    document.refresh_from_db()
    assert document.kind == Document.Kind.CONTRACT


def test_a_document_read_before_the_terms_were_filled_still_refuses(downtown, alpha):
    """Отказ спрашивает таблицу, а не свою память о ней.

    Экземпляр, прочитанный до того, как условия заполнили, помнит их пустыми — и вид, ушедший
    по этой памяти, унёс бы контрагента молча. Путь не выдуманный: страницу документа
    открывают и сохраняют, а условия между этими двумя мгновениями заводит кто-то другой.
    """
    document = contract(downtown)
    read_earlier = Document.objects.get(pk=document.pk)
    assert read_earlier.attached_terms().filled() is False
    filled(document, counterparty=alpha)

    read_earlier.kind = Document.Kind.ACT
    with pytest.raises(ValidationError):
        read_earlier.save()

    read_earlier.refresh_from_db()
    assert read_earlier.kind == Document.Kind.CONTRACT
    assert ContractTerms.objects.get().counterparty_id == alpha.pk


def test_the_refusal_names_every_condition_somebody_filled(downtown, alpha):
    """Отказ называет, что именно очистить, — иначе читателю искать это самому."""
    document = filled(
        contract(downtown),
        counterparty=alpha,
        kind=ContractTerms.Kind.LEASE,
        is_perpetual=True,
        auto_prolongs=True,
    )

    document.kind = Document.Kind.ACT
    with pytest.raises(ValidationError) as refusal:
        document.save()

    said = str(refusal.value)
    assert "контрагент" in said
    assert "вид договора" in said
    assert "бессрочность" in said
    assert "автопролонгация" in said


def test_the_refusal_is_named_on_the_kind_itself(downtown):
    """Отказ стоит на поле, которое только что тронули: форме есть куда его поставить."""
    document = filled(contract(downtown), kind=ContractTerms.Kind.SUPPLY)

    document.kind = Document.Kind.ACT
    with pytest.raises(ValidationError) as refusal:
        document.save()

    assert list(refusal.value.message_dict) == ["kind"]


def test_the_same_refusal_comes_before_the_save_as_well(downtown, alpha):
    """Проверка формы и сохранение отказывают одними словами, а не двумя."""
    document = filled(contract(downtown), counterparty=alpha)

    document.kind = Document.Kind.ACT
    with pytest.raises(ValidationError):
        document.full_clean()


def test_a_contract_whose_terms_were_cleared_lets_its_kind_go(downtown, alpha):
    """Отказ говорит «сначала очисти», и очищенное действительно отпускает."""
    document = filled(contract(downtown), counterparty=alpha)
    filled(document, counterparty=None)

    document.kind = Document.Kind.ACT
    document.save()

    document.refresh_from_db()
    assert document.kind == Document.Kind.ACT


# Уже лежащие договоры


def test_the_migration_gives_terms_to_a_contract_stored_before_it(downtown):
    """Строка заводится и тем договорам, что легли до этого этапа."""
    document = contract(downtown)
    ContractTerms.objects.all().delete()

    give_every_contract_its_terms(installed, None)

    assert ContractTerms.objects.filter(document=document).exists()


def test_the_migration_leaves_filled_terms_as_they_stand(downtown, alpha):
    """Второй прогон не заводит второй строки и не затирает первую."""
    document = filled(contract(downtown), counterparty=alpha)

    give_every_contract_its_terms(installed, None)

    assert ContractTerms.objects.count() == 1
    assert document.attached_terms().counterparty_id == alpha.pk


def test_the_migration_passes_documents_of_other_kinds_by(downtown):
    """Акт условий не получает — ни тогда, ни теперь."""
    Document.objects.create(org=downtown, kind=Document.Kind.ACT, title="Акт")

    give_every_contract_its_terms(installed, None)

    assert ContractTerms.objects.count() == 0
