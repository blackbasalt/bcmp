"""Договор аренды и его предмет: сущность, отказ и период.

Экранов у аренды пока нет, поэтому шов здесь — сама модель: договор заводится
`Lease.objects.create()`, предмет — `LeaseSubject.objects.create()`, и отказ
приходит оттуда же, откуда придёт админке и будущей форме. Так же проверялся
чокпоинт до появления экранов (`test_scoping`).

Проверяется то, чего по данным не восстановить: что предмет несёт свою ставку и
свою площадь, что периоды на одном помещении не пересекаются и что отказ называет
помещение и договор, с которым вышло пересечение.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from building_passport.models import Space, SpaceArea
from dictionary.models import DictDocumentRole
from documents.models import Document, DocumentLink
from leases.models import Lease, LeaseSubject
from parties.models import Party

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db):
    """Сторона, которую арендатором делает договор и только он (ADR 0008)."""
    return Party.objects.create(
        kind=Party.Kind.COMPANY, name="Ромашка ТОО", bin_iin="180540035879"
    )


def leasable(space):
    """Помещение, которое может сдаваться: арендопригодность — свойство помещения."""
    space.is_leasable = True
    space.save(update_fields=["is_leasable"])
    return space


@pytest.fixture
def office(first_floor, make_space):
    return leasable(make_space(first_floor, "man-f1-101", "Офис 101"))


@pytest.fixture
def boston(downtown, make_floor, make_space):
    """Второй БЦ той же организации: договор не привязан к зданию вовсе."""
    building = Space.objects.create(
        org=downtown, type="building", code="bos", name="Boston"
    )
    return make_floor(building, 1)


@pytest.fixture
def warehouse(boston, make_space):
    return leasable(make_space(boston, "bos-f1-01", "Склад"))


def make_lease(org, tenant, valid_from=date(2025, 1, 1), valid_to=None, **fields):
    return Lease.objects.create(
        org=org, tenant=tenant, valid_from=valid_from, valid_to=valid_to, **fields
    )


def test_a_lease_names_several_spaces_across_buildings_each_with_its_own_rate(
    downtown, tenant, office, warehouse
):
    """Арендатор с офисом в Manhattan и складом в Boston — один договор, как на бумаге."""
    lease = make_lease(downtown, tenant, number="12-А", signed_at=date(2024, 12, 20))
    LeaseSubject.objects.create(
        lease=lease, space=office, rate=Decimal("450000.00"), area_m2=Decimal("52.30")
    )
    LeaseSubject.objects.create(lease=lease, space=warehouse, rate=Decimal("90000.00"))

    subjects = lease.subjects.order_by("space__code")
    assert [subject.space for subject in subjects] == [warehouse, office]
    assert [subject.rate for subject in subjects] == [
        Decimal("90000.00"),
        Decimal("450000.00"),
    ]
    assert subjects[1].area_m2 == Decimal("52.30")
    assert subjects[0].area_m2 is None
    assert lease.tenant == tenant


def test_a_lease_conflicting_on_one_space_of_three_names_that_space(
    downtown, tenant, office, warehouse, first_floor, make_space
):
    """Пересечение ищется по каждому помещению отдельно, а не по договору целиком."""
    kitchen = leasable(make_space(first_floor, "man-f1-102", "Кафе"))
    let = make_lease(downtown, tenant, date(2025, 1, 1), date(2025, 12, 31), number="12-А")
    LeaseSubject.objects.create(lease=let, space=office)

    new = make_lease(downtown, tenant, date(2025, 6, 1))
    LeaseSubject.objects.create(lease=new, space=warehouse)
    LeaseSubject.objects.create(lease=new, space=kitchen)
    with pytest.raises(ValidationError) as refusal:
        LeaseSubject.objects.create(lease=new, space=office)

    said = " ".join(refusal.value.messages)
    assert "Офис 101" in said and "man-f1-101" in said
    assert "12-А" in said
    assert "Кафе" not in said and "Склад" not in said


def test_leases_that_do_not_touch_share_one_space(downtown, tenant, office):
    """Прежний арендатор съехал, новый заехал: помещение сдаётся второй раз."""
    first = make_lease(downtown, tenant, date(2024, 1, 1), date(2024, 12, 31))
    LeaseSubject.objects.create(lease=first, space=office)
    second = make_lease(downtown, tenant, date(2025, 1, 1), date(2025, 12, 31))
    LeaseSubject.objects.create(lease=second, space=office)

    assert office.lease_subjects.count() == 2


def test_a_lease_beginning_on_the_day_another_ends_is_an_overlap(
    downtown, tenant, office
):
    """Период включает оба конца: в день закрытия действовали бы оба договора."""
    ending = make_lease(downtown, tenant, date(2024, 1, 1), date(2024, 12, 31))
    LeaseSubject.objects.create(lease=ending, space=office)

    starting = make_lease(downtown, tenant, date(2024, 12, 31))
    with pytest.raises(ValidationError):
        LeaseSubject.objects.create(lease=starting, space=office)


def test_an_open_ended_lease_blocks_a_lease_starting_after_it(downtown, tenant, office):
    """Пустая дата окончания читается «по сей день» и не кончается никогда."""
    forever = make_lease(downtown, tenant, date(2020, 1, 1))
    LeaseSubject.objects.create(lease=forever, space=office)

    later = make_lease(downtown, tenant, date(2030, 6, 1))
    with pytest.raises(ValidationError):
        LeaseSubject.objects.create(lease=later, space=office)


@pytest.fixture
def their_office(central, make_floor, make_space):
    """Арендопригодное помещение другого клиента платформы."""
    building = Space.objects.create(
        org=central, type="building", code="ctr", name="Central Tower"
    )
    return leasable(make_space(make_floor(building, 1), "ctr-f1-01", "Кабинет"))


def test_a_space_of_another_organisation_is_refused(downtown, tenant, their_office):
    """Ошибка, которую надо назвать, а не редкий случай, который надо поддержать (ADR 0009)."""
    lease = make_lease(downtown, tenant)

    with pytest.raises(ValidationError) as refusal:
        LeaseSubject.objects.create(lease=lease, space=their_office)

    said = " ".join(refusal.value.messages)
    assert "ctr-f1-01" in said
    assert "организации" in said


def test_a_space_that_is_not_leasable_is_refused(downtown, tenant, first_floor):
    """Венткамера не должна сдаваться из-за промаха в выпадающем списке."""
    itp = Space.objects.get(code="man-f1-b")
    lease = make_lease(downtown, tenant)

    with pytest.raises(ValidationError) as refusal:
        LeaseSubject.objects.create(lease=lease, space=itp)

    said = " ".join(refusal.value.messages)
    assert "ИТП" in said
    assert "арендопригодн" in said


def test_letting_a_parent_space_does_not_let_the_spaces_inside_it(
    downtown, tenant, office, make_space
):
    """Тамбур и кабинет за ним сдаются разным арендаторам, и система не возражает.

    Связь в дереве означает одно из двух — содержание или объединение, — и правило,
    выводящее занятость из иерархии, было бы верно для одного и молча неверно для
    другого. Цена принята и названа, чтобы её не прочли как недосмотр.
    """
    inner = leasable(make_space(office, "man-f1-101a", "Кабинет в офисе"))
    outer = make_lease(downtown, tenant, date(2025, 1, 1), date(2025, 12, 31))
    LeaseSubject.objects.create(lease=outer, space=office)

    another = Party.objects.create(kind=Party.Kind.COMPANY, name="Василёк ТОО")
    inner_lease = make_lease(downtown, another, date(2025, 1, 1), date(2025, 12, 31))
    subject = LeaseSubject.objects.create(lease=inner_lease, space=inner)

    assert subject.pk is not None


def test_a_renewal_names_the_lease_it_prolongs_and_leaves_its_rate_alone(
    downtown, tenant, office
):
    """Пролонгация — новый договор со ссылкой, а не передвинутый конец прежнего.

    Ставка при продлении меняется, и правка на месте стирала бы ответ на вопрос
    «по какой ставке помещение сдавалось в марте» (ADR 0007).
    """
    ended = make_lease(downtown, tenant, date(2024, 1, 1), date(2024, 12, 31))
    LeaseSubject.objects.create(lease=ended, space=office, rate=Decimal("400000.00"))

    renewal = make_lease(
        downtown, tenant, date(2025, 1, 1), date(2025, 12, 31), prolongs=ended
    )
    LeaseSubject.objects.create(lease=renewal, space=office, rate=Decimal("450000.00"))

    assert renewal.prolongs == ended
    assert list(ended.prolonged_by.all()) == [renewal]
    assert ended.subjects.get().rate == Decimal("400000.00")


def test_a_period_that_ends_before_it_begins_is_refused(downtown, tenant):
    lease = Lease(
        org=downtown, tenant=tenant, valid_from=date(2025, 6, 1), valid_to=date(2025, 1, 1)
    )

    with pytest.raises(ValidationError):
        lease.save()


def test_moving_a_lease_onto_a_period_already_let_is_refused(downtown, tenant, office):
    """Проверка стоит и на договоре: иначе правка срока обошла бы её мимо предмета."""
    ended = make_lease(downtown, tenant, date(2024, 1, 1), date(2024, 12, 31))
    LeaseSubject.objects.create(lease=ended, space=office)
    later = make_lease(downtown, tenant, date(2025, 1, 1), date(2025, 12, 31))
    LeaseSubject.objects.create(lease=later, space=office)

    later.valid_from = date(2024, 6, 1)
    with pytest.raises(ValidationError) as refusal:
        later.save()

    assert "man-f1-101" in " ".join(refusal.value.messages)


def test_a_scan_is_filed_against_the_lease_itself(downtown, tenant, office):
    """Скан подшивается к договору: подшить его было не к чему — вида не было (ADR 0006)."""
    lease = make_lease(downtown, tenant)
    LeaseSubject.objects.create(lease=lease, space=office)
    scan = Document.objects.create(
        org=downtown, kind=Document.Kind.CONTRACT, title="Договор аренды, скан"
    )

    link = DocumentLink.objects.create(
        document=scan,
        entity_type=DocumentLink.EntityType.LEASE,
        entity_id=lease.pk,
        role=DictDocumentRole.objects.create(name="Оригинал", short_name="ориг"),
    )

    assert link.entity_type == "lease"
    assert DocumentLink.objects.filter(
        entity_type="lease", entity_id=lease.pk
    ).get() == link


def test_a_lease_writes_neither_the_area_of_the_space_nor_a_measurement(
    downtown, tenant, office
):
    """Договорная площадь — условие соглашения, а не обмер здания (ADR 0006).

    `SpaceArea.Source.LEASE` остаётся для ручного случая, когда обмера нет вовсе,
    и автоматически не пишется никогда: дырка, закрытая правдоподобным числом,
    перестаёт быть видимой.
    """
    lease = make_lease(downtown, tenant)
    LeaseSubject.objects.create(lease=lease, space=office, area_m2=Decimal("62.40"))

    office.refresh_from_db()
    assert office.area_m2 is None
    assert not SpaceArea.objects.filter(space=office).exists()


def lease_form(org, tenant, subjects, valid_from="2025-06-01", valid_to="", **fields):
    """Договор с предметами так, как их отправляет админка: одной формой с инлайном."""
    posted = {
        "org": str(org.pk),
        "tenant": str(tenant.pk),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "number": "",
        "signed_at": "",
        "prolongs": "",
        "subjects-TOTAL_FORMS": str(len(subjects)),
        "subjects-INITIAL_FORMS": "0",
        "subjects-MIN_NUM_FORMS": "1",
        "subjects-MAX_NUM_FORMS": "1000",
        # Инлайн «Документы» на странице договора шлёт свой формсет: скан подшивается
        # там же, где договор заводится.
        "form-TOTAL_FORMS": "0",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        **fields,
    }
    for index, space in enumerate(subjects):
        posted[f"subjects-{index}-space"] = str(space.pk)
        posted[f"subjects-{index}-rate"] = ""
        posted[f"subjects-{index}-area_m2"] = ""
        posted[f"subjects-{index}-id"] = ""
        posted[f"subjects-{index}-lease"] = ""
    return posted


@pytest.fixture
def administrator(django_user_model):
    """Администратор платформы: пока формы нет, договоры заводятся в админке."""
    return django_user_model.objects.create_superuser("administrator")


def test_django_admin_receives_the_same_refusal_and_saves_nothing(
    client, administrator, downtown, tenant, office
):
    """Отказ приходит с модели и виден на форме, а не пятисоткой при сохранении."""
    let = make_lease(downtown, tenant, date(2025, 1, 1), date(2025, 12, 31), number="12-А")
    LeaseSubject.objects.create(lease=let, space=office)
    client.force_login(administrator)

    response = client.post(
        reverse("admin:leases_lease_add"), lease_form(downtown, tenant, [office])
    )

    assert response.status_code == 200
    assert "уже сдано" in response.content.decode()
    assert list(Lease.objects.all()) == [let]


def test_a_lease_without_a_single_subject_is_refused_by_the_form(
    client, administrator, downtown, tenant
):
    """Договор без предмета не договор: сдавать нечего, и красить на плане нечего."""
    client.force_login(administrator)

    response = client.post(
        reverse("admin:leases_lease_add"), lease_form(downtown, tenant, [])
    )

    assert response.status_code == 200
    assert "хотя бы одно помещение" in response.content.decode()
    assert not Lease.objects.exists()


def test_django_admin_enters_a_lease_with_its_subjects_in_one_action(
    client, administrator, downtown, tenant, office, warehouse
):
    client.force_login(administrator)

    response = client.post(
        reverse("admin:leases_lease_add"),
        lease_form(downtown, tenant, [office, warehouse]),
    )

    assert response.status_code == 302
    lease = Lease.objects.get()
    assert {subject.space for subject in lease.subjects.all()} == {office, warehouse}
