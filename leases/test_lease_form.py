"""Ведение договоров с экрана: заведение, правка, удаление и пролонгация.

Шов тот же, что у остальных экранов, — граница HTTP: тест открывает Список договоров
или карточку и отправляет форму тестовым клиентом от имени пользователя с известным
членством. Проверяется наблюдаемое: предложена ли форма, каким кодом отвечает запрос,
что осталось в базе после отказа и что видно на экране после успеха.

Опора в разметке — атрибуты `data-lease-form`, `data-lease-delete` и
`data-lease-prolong`. Это договор экрана: по ним видно, предложено ли действие, а
сотруднику без флага администратора оно не предлагается вовсе. Ни классы, ни имена
полей в разметке не проверяются: вернувшуюся форму тест спрашивает у самого ответа
(`response.context`), потому что перестройка вёрстки ниже уровня URL не должна
переписывать набор тестов.

Отказы модели здесь не переписываются: пересечение периодов, чужая организация и
неарендопригодное помещение проверены в `test_lease` там, где они и живут. Здесь
спрашивается другое — доезжает ли отказ до формы вместе с уже введёнными значениями.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from leases.models import Lease, LeaseSubject
from parties.models import OrgMembership

pytestmark = pytest.mark.django_db


def list_url():
    return reverse("leases:lease_list")


def card_url(lease):
    return reverse("leases:lease_detail", args=[lease.pk])


def delete_url(lease):
    return reverse("leases:lease_delete", args=[lease.pk])


def stated(page):
    """Страница одной строкой: фраза не должна ломаться о перенос в разметке."""
    return " ".join(page.split())


def subject(space, rate="", area_m2=""):
    """Строка предмета в отправляемой форме: помещение со своей ставкой и площадью."""
    return {"space": str(space.pk), "rate": rate, "area_m2": area_m2}


def kept(existing, **fields):
    """Строка уже заведённого предмета: со своим ключом, иначе он заведётся заново."""
    return {
        "id": str(existing.pk),
        "space": str(existing.space_id),
        "rate": "" if existing.rate is None else str(existing.rate),
        "area_m2": "" if existing.area_m2 is None else str(existing.area_m2),
        **fields,
    }


def entered(org, tenant, *subjects, **fields):
    """Заполненная форма договора: сам договор и строки предмета под своим префиксом."""
    data = {
        "org": str(org.pk),
        "tenant": str(tenant.pk),
        "valid_from": "2025-01-01",
        "valid_to": "",
        "number": "",
        "signed_at": "",
        "prolongs": "",
        "subjects-TOTAL_FORMS": str(len(subjects)),
        "subjects-INITIAL_FORMS": str(sum("id" in row for row in subjects)),
        "subjects-MIN_NUM_FORMS": "1",
        "subjects-MAX_NUM_FORMS": "1000",
    }
    data.update(fields)
    for index, row in enumerate(subjects):
        for name, value in row.items():
            data[f"subjects-{index}-{name}"] = value
    return data


@pytest.fixture
def administrator(django_user_model, downtown):
    """Администратор организации: тот же сотрудник УК, но с правом вести данные."""
    user = django_user_model.objects.create_user("director")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    return user


@pytest.fixture
def our_lease(downtown, tenant, office, make_lease, make_subject):
    """Заведённый договор — то, что правят, расторгают, удаляют и пролонгируют."""
    lease = make_lease(
        downtown,
        tenant,
        date(2025, 1, 1),
        date(2025, 12, 31),
        number="12-А",
        signed_at=date(2024, 12, 20),
    )
    make_subject(lease, office, rate=Decimal("450000.00"), area_m2=Decimal("52.30"))
    return lease


def open_page(client, user, url):
    client.force_login(user)
    return client.get(url).content.decode()


# Кто может


def test_an_administrator_of_the_organisation_is_offered_the_form_on_the_list(
    client, administrator
):
    """Ведение договоров перестаёт требовать админки Django."""
    assert 'data-lease-form="create"' in open_page(client, administrator, list_url())


def test_a_member_without_the_flag_is_offered_no_create_control_at_all(client, member):
    """Действие, которого сотруднику не совершить, ему и не предлагается."""
    assert "data-lease-form" not in open_page(client, member, list_url())


def test_a_member_without_the_flag_is_offered_no_edit_or_delete_control_at_all(
    client, member, our_lease
):
    """Карточка договора читателю остаётся карточкой: править на ней нечего."""
    page = open_page(client, member, card_url(our_lease))

    assert "data-lease-form" not in page
    assert "data-lease-delete" not in page


def test_an_administrator_is_offered_edit_and_delete_on_the_card(
    client, administrator, our_lease
):
    """Правят и удаляют там же, где смотрят: другого места у договора нет."""
    page = open_page(client, administrator, card_url(our_lease))

    assert 'data-lease-form="edit"' in page
    assert "data-lease-delete" in page


# Заведение


def test_an_administrator_creates_a_lease_naming_several_spaces_in_one_action(
    client, administrator, downtown, tenant, office, warehouse
):
    """Офис в Manhattan и склад в Boston — один договор, как он и есть на бумаге."""
    client.force_login(administrator)

    response = client.post(
        list_url(),
        entered(
            downtown,
            tenant,
            subject(office, rate="450000", area_m2="52.30"),
            subject(warehouse, rate="90000"),
            number="12-А",
            signed_at="2024-12-20",
            valid_from="2025-01-01",
            valid_to="2025-12-31",
        ),
    )

    lease = Lease.objects.get()
    assert response.status_code == 302
    assert response.url == card_url(lease)
    assert lease.org == downtown and lease.tenant == tenant
    assert lease.number == "12-А" and lease.signed_at == date(2024, 12, 20)
    assert lease.valid_from == date(2025, 1, 1) and lease.valid_to == date(2025, 12, 31)
    subjects = {row.space: row for row in lease.subjects.all()}
    assert subjects[office].rate == Decimal("450000.00")
    assert subjects[office].area_m2 == Decimal("52.30")
    assert subjects[warehouse].rate == Decimal("90000.00")
    assert subjects[warehouse].area_m2 is None


def test_a_lease_names_more_spaces_than_the_form_drew_rows_for(
    client, administrator, downtown, tenant, office, warehouse, first_floor,
    make_leasable
):
    """Договор на десять машиномест — одна отправка, а не два прохода.

    Строку добавляют на самой форме, и формсет принимает столько строк, сколько
    прислано: числом нарисованных сервером пустых строк договор не ограничен.
    """
    spaces = [office, warehouse] + [
        make_leasable(first_floor, f"man-f1-p{index}", f"Машиноместо {index}")
        for index in range(4)
    ]
    client.force_login(administrator)

    response = client.post(
        list_url(),
        entered(downtown, tenant, *(subject(space) for space in spaces)),
    )

    assert response.status_code == 302
    assert set(Lease.objects.get().subjects.values_list("space_id", flat=True)) == {
        space.pk for space in spaces
    }


def test_a_lease_saves_with_no_number_no_signing_date_and_no_rate(
    client, administrator, downtown, tenant, office
):
    """Договор заводят раньше, чем держат в руках каждую его подробность."""
    client.force_login(administrator)

    response = client.post(list_url(), entered(downtown, tenant, subject(office)))

    lease = Lease.objects.get()
    assert response.status_code == 302
    assert lease.number is None or lease.number == ""
    assert lease.signed_at is None
    assert lease.subjects.get().rate is None


def test_a_created_lease_is_shown_on_the_list_it_was_created_from(
    client, administrator, downtown, tenant, office
):
    """Подтверждение — сам экран: заведённый договор виден там, где его заводили."""
    client.force_login(administrator)
    client.post(list_url(), entered(downtown, tenant, subject(office), number="12-А"))

    page = client.get(list_url()).content.decode()

    assert "12-А" in page
    assert "Ромашка ТОО" in page


def test_a_member_without_the_flag_cannot_create_even_by_posting_directly(
    client, member, downtown, tenant, office
):
    """Отказано не только показу кнопки: право проверяется на самом запросе."""
    client.force_login(member)

    response = client.post(list_url(), entered(downtown, tenant, subject(office)))

    assert response.status_code == 403
    assert Lease.objects.count() == 0


def test_a_lease_without_a_single_space_is_refused(
    client, administrator, downtown, tenant
):
    """Договор без предмета не договор: сдавать нечего и красить на плане нечего."""
    client.force_login(administrator)

    response = client.post(list_url(), entered(downtown, tenant))

    assert response.status_code == 200
    assert "хотя бы одно помещение" in stated(response.content.decode())
    assert Lease.objects.count() == 0


# Отказы на форме


def test_an_overlapping_lease_is_refused_naming_the_space_and_the_conflicting_lease(
    client, administrator, downtown, tenant, office, warehouse, our_lease
):
    """Найти прежний договор надо, а не угадать: отказ называет и помещение, и его."""
    client.force_login(administrator)

    response = client.post(
        list_url(),
        entered(
            downtown,
            tenant,
            subject(warehouse),
            subject(office),
            valid_from="2025-06-01",
        ),
    )

    said = stated(response.content.decode())
    assert response.status_code == 200
    assert "Офис 101" in said and "man-f1-101" in said
    assert "12-А" in said
    assert Lease.objects.count() == 1  # отказ не записал ни договора, ни предмета
    assert LeaseSubject.objects.count() == 1


def test_a_refused_lease_comes_back_with_everything_already_entered(
    client, administrator, downtown, tenant, office, warehouse, our_lease
):
    """Перенабирать договор целиком из-за одной плохой строки — то, после чего
    данные перестают заводить вовсе."""
    client.force_login(administrator)

    response = client.post(
        list_url(),
        entered(
            downtown,
            tenant,
            subject(warehouse, rate="90000"),
            subject(office),
            number="ЧЕРНОВИК-7",
            valid_from="2025-06-01",
        ),
    )

    returned = response.context["writing"]
    assert returned.form["number"].value() == "ЧЕРНОВИК-7"
    assert returned.form["valid_from"].value() == "2025-06-01"
    assert returned.subjects.forms[0]["space"].value() == str(warehouse.pk)
    assert returned.subjects.forms[0]["rate"].value() == "90000"


def test_a_space_of_another_organisation_is_refused_naming_the_space(
    client, django_user_model, downtown, central, tenant, office
):
    """Предмет и организация договора расходиться не должны (ADR 0009).

    Проверяется на сотруднике, ведущем двух клиентов: у него в списке помещения
    обоих, и назвать помещение одного в договоре другого он может — отказ приходит
    от самой модели и называет помещение.
    """
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=True)
    client.force_login(user)

    response = client.post(list_url(), entered(central, tenant, subject(office)))

    said = stated(response.content.decode())
    assert response.status_code == 200
    assert "принадлежит другой организации" in said
    assert "Офис 101" in said
    assert Lease.objects.count() == 0


def test_a_space_of_an_organisation_the_administrator_does_not_lead_is_not_offered(
    client, administrator, downtown, tenant, their_office
):
    """Помещение чужого клиента в списке — уже утечка имён, а не промах выбора."""
    client.force_login(administrator)

    response = client.post(list_url(), entered(downtown, tenant, subject(their_office)))

    assert response.status_code == 200
    assert Lease.objects.count() == 0
    assert "Кабинет" not in client.get(list_url()).content.decode()


def test_a_space_that_is_not_leasable_is_neither_offered_nor_accepted(
    client, administrator, downtown, tenant, first_floor
):
    """Венткамера не должна попадать в список вовсе: МОП и техническое не сдаются."""
    itp = first_floor.subspace.get(code="man-f1-b")
    client.force_login(administrator)

    response = client.post(list_url(), entered(downtown, tenant, subject(itp)))

    assert response.status_code == 200
    assert Lease.objects.count() == 0
    assert "ИТП" not in client.get(list_url()).content.decode()


def test_the_same_space_named_twice_in_one_lease_is_refused(
    client, administrator, downtown, tenant, office
):
    """У одного помещения одна ставка: вторая строка о том же — опечатка, а не предмет."""
    client.force_login(administrator)

    response = client.post(
        list_url(),
        entered(downtown, tenant, subject(office, rate="1"), subject(office, rate="2")),
    )

    assert response.status_code == 200
    assert "дважды" in stated(response.content.decode())
    assert Lease.objects.count() == 0


# Правка и расторжение


def test_an_administrator_corrects_a_lease_entered_wrongly(
    client, administrator, our_lease, office
):
    """Опечатка исправляется на карточке, а не заявкой администратору платформы."""
    client.force_login(administrator)
    subject_of = our_lease.subjects.get()

    response = client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(subject_of, rate="470000"),
            number="12-Б",
            valid_from="2025-01-01",
            valid_to="2025-12-31",
            signed_at="2024-12-20",
        ),
    )

    our_lease.refresh_from_db()
    assert response.status_code == 302
    assert response.url == card_url(our_lease)
    assert our_lease.number == "12-Б"
    assert our_lease.subjects.get().rate == Decimal("470000.00")
    assert LeaseSubject.objects.count() == 1  # правка строки, а не вторая строка


def test_a_correction_adds_a_space_to_the_lease_and_removes_another(
    client, administrator, our_lease, warehouse
):
    """Договор меняется целиком: арендатор доснял склад и съехал из офиса."""
    client.force_login(administrator)
    subject_of = our_lease.subjects.get()

    client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(subject_of, DELETE="on"),
            subject(warehouse, rate="90000"),
            valid_from="2025-01-01",
            valid_to="2025-12-31",
        ),
    )

    assert [row.space for row in our_lease.subjects.all()] == [warehouse]


def test_moving_the_period_past_a_space_taken_off_in_the_same_correction_takes_two(
    client, administrator, downtown, tenant, office, warehouse, our_lease, make_lease,
    make_subject
):
    """Названная плата за порядок проверок, а не забытый случай.

    Срок договора сверяется с предметами по базе — иначе правка срока прошла бы мимо
    проверки вовсе, — и снимаемое этой же отправкой помещение там ещё стоит. Значит,
    «продлить и снять офис» разом отказывается по офису; отказ при этом называет
    его, и вторым заходом правка проходит.
    """
    make_subject(make_lease(downtown, tenant, date(2026, 1, 1), date(2026, 12, 31)), office)
    client.force_login(administrator)
    taken_off = entered(
        our_lease.org,
        our_lease.tenant,
        kept(our_lease.subjects.get(), DELETE="on"),
        subject(warehouse),
        valid_from="2025-01-01",
        valid_to="2026-06-30",
    )

    refused = client.post(card_url(our_lease), taken_off)

    assert refused.status_code == 200
    assert "Офис 101" in stated(refused.content.decode())

    # Тем же двум действиям порознь ничто не мешает.
    taken_off["valid_to"] = "2025-12-31"
    client.post(card_url(our_lease), taken_off)
    client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(our_lease.subjects.get()),
            valid_from="2025-01-01",
            valid_to="2026-06-30",
        ),
    )

    our_lease.refresh_from_db()
    assert our_lease.valid_to == date(2026, 6, 30)
    assert [row.space for row in our_lease.subjects.all()] == [warehouse]


def test_a_lease_ends_on_the_date_the_administrator_states(
    client, administrator, our_lease
):
    """Досрочное расторжение закрывает период днём, когда оно случилось (ADR 0007)."""
    client.force_login(administrator)

    client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(our_lease.subjects.get()),
            valid_from="2025-01-01",
            valid_to="2025-08-31",
        ),
    )

    our_lease.refresh_from_db()
    assert our_lease.valid_to == date(2025, 8, 31)


def test_the_form_offers_no_end_date_of_its_own(
    client, administrator, downtown, tenant, office, make_lease, make_subject
):
    """Подставленное сегодня приняли бы не глядя, и договор кончился бы днём формы."""
    open_ended = make_lease(downtown, tenant, date(2025, 3, 1))
    make_subject(open_ended, office)
    client.force_login(administrator)

    response = client.get(card_url(open_ended))

    assert response.context["writing"].form["valid_to"].value() is None
    assert timezone.localdate().isoformat() not in response.content.decode()


def test_a_lease_whose_period_has_ended_stays_readable(
    client, administrator, our_lease
):
    """«Кто сидел здесь в прошлом году» должно иметь ответ: истёкший договор остаётся."""
    client.force_login(administrator)
    client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(our_lease.subjects.get()),
            valid_from="2025-01-01",
            valid_to="2025-02-28",
        ),
    )

    card = client.get(card_url(our_lease))
    listed = client.get(list_url()).content.decode()

    assert card.status_code == 200
    assert "01.01.2025 — 28.02.2025" in listed
    assert Lease.objects.count() == 1


def test_a_correction_that_overlaps_another_lease_is_refused_and_changes_nothing(
    client, administrator, downtown, tenant, office, our_lease, make_lease, make_subject
):
    """Правка срока идёт мимо проверки предмета, если та стоит только на предмете."""
    neighbour = make_lease(downtown, tenant, date(2026, 1, 1), date(2026, 12, 31))
    make_subject(neighbour, office)
    client.force_login(administrator)

    response = client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(our_lease.subjects.get()),
            valid_from="2025-01-01",
            valid_to="2026-06-30",
        ),
    )

    our_lease.refresh_from_db()
    assert response.status_code == 200
    assert "Офис 101" in stated(response.content.decode())
    assert our_lease.valid_to == date(2025, 12, 31)


def test_a_member_without_the_flag_cannot_correct_even_by_posting_directly(
    client, member, our_lease
):
    """Отказано не только показу формы: право проверяется на самом запросе."""
    client.force_login(member)

    response = client.post(
        card_url(our_lease),
        entered(
            our_lease.org,
            our_lease.tenant,
            kept(our_lease.subjects.get()),
            number="ПОДМЕНА",
        ),
    )

    our_lease.refresh_from_db()
    assert response.status_code == 403
    assert our_lease.number == "12-А"


def test_correcting_a_lease_of_another_organisation_is_missing_rather_than_forbidden(
    client, administrator, central, their_office, tenant, make_lease, make_subject
):
    """403 подтверждал бы, что договор есть, — та же утечка, что и на чтении."""
    theirs = make_lease(central, tenant, number="ЧУЖОЙ-1")
    make_subject(theirs, their_office)
    client.force_login(administrator)

    response = client.post(
        card_url(theirs),
        entered(central, tenant, kept(theirs.subjects.get()), number="ПОДМЕНА"),
    )

    theirs.refresh_from_db()
    assert response.status_code == 404
    assert theirs.number == "ЧУЖОЙ-1"


# Удаление


def test_an_administrator_deletes_a_lease_entered_by_mistake(
    client, administrator, our_lease
):
    """Опечатка фактом истории не была никогда, и остаётся ей нечем (ADR 0007)."""
    client.force_login(administrator)

    response = client.post(delete_url(our_lease))

    assert response.status_code == 302
    assert response.url == list_url()
    assert Lease.objects.count() == 0
    assert LeaseSubject.objects.count() == 0
    assert "удалён" in stated(client.get(list_url()).content.decode())


def test_a_member_without_the_flag_cannot_delete_even_by_posting_directly(
    client, member, our_lease
):
    """Читателю удаление не предлагается и не разрешается."""
    client.force_login(member)

    response = client.post(delete_url(our_lease))

    assert response.status_code == 403
    assert Lease.objects.count() == 1


def test_deleting_a_lease_of_another_organisation_is_missing_rather_than_forbidden(
    client, administrator, central, their_office, tenant, make_lease, make_subject
):
    """Чужой договор отвечает одинаково на чтение и на запись: его не существует."""
    theirs = make_lease(central, tenant)
    make_subject(theirs, their_office)
    client.force_login(administrator)

    response = client.post(delete_url(theirs))

    assert response.status_code == 404
    assert Lease.objects.count() == 1


def test_a_lease_a_prolongation_points_at_is_not_deleted_silently(
    client, administrator, downtown, tenant, office, our_lease, make_lease, make_subject
):
    """Цепочку пролонгаций рвать молча нечем: снявший ссылку должен знать, что снимает."""
    renewal = make_lease(downtown, tenant, date(2026, 1, 1), prolongs=our_lease)
    make_subject(renewal, office)
    client.force_login(administrator)

    response = client.post(delete_url(our_lease))

    assert response.status_code == 302
    assert response.url == card_url(our_lease)
    assert Lease.objects.filter(pk=our_lease.pk).exists()
    assert "пролонгация" in stated(client.get(card_url(our_lease)).content.decode())


def test_a_lease_is_not_deleted_by_following_a_link(client, administrator, our_lease):
    """Договор удаляют кнопкой в форме, а не переходом по адресу."""
    client.force_login(administrator)

    response = client.get(delete_url(our_lease))

    assert response.status_code == 405
    assert Lease.objects.count() == 1


# Пролонгация


def test_the_card_offers_prolongation_from_the_lease_being_prolonged(
    client, administrator, our_lease
):
    """Продлевают с карточки прежнего договора: он и есть то, ради чего сюда пришли."""
    page = open_page(client, administrator, card_url(our_lease))

    assert "data-lease-prolong" in page
    assert f"{list_url()}?prolongs={our_lease.pk}" in page


def test_prolongation_opens_a_form_filled_with_what_is_being_prolonged(
    client, administrator, our_lease, tenant, office
):
    """Продлевается то, что и было: арендатор, помещения и договорная площадь.

    Ставка — нет: при продлении она почти всегда меняется, и подставленная старая,
    принятая не глядя, стёрла бы ответ на «по какой ставке сдавалось в марте».
    """
    client.force_login(administrator)

    offered = client.get(f"{list_url()}?prolongs={our_lease.pk}").context["writing"]

    assert offered.form["prolongs"].value() == our_lease.pk
    assert offered.form["tenant"].value() == tenant.pk
    assert offered.form["valid_from"].value() is None
    first_row = offered.subjects.forms[0]
    assert first_row["space"].value() == office.pk
    assert first_row["area_m2"].value() == Decimal("52.30")  # площадь не меняется
    assert first_row["rate"].value() is None


def test_a_prolongation_saves_as_a_new_lease_beside_the_one_it_prolongs(
    client, administrator, our_lease, office
):
    """Пролонгация — новый договор со ссылкой на прежний, а не передвинутый конец."""
    client.force_login(administrator)

    response = client.post(
        list_url(),
        entered(
            our_lease.org,
            our_lease.tenant,
            subject(office, rate="500000"),
            valid_from="2026-01-01",
            valid_to="2026-12-31",
            prolongs=str(our_lease.pk),
        ),
    )

    renewal = Lease.objects.get(valid_from=date(2026, 1, 1))
    our_lease.refresh_from_db()
    assert response.status_code == 302
    assert renewal.prolongs == our_lease
    assert renewal.subjects.get().rate == Decimal("500000.00")
    # Прежний договор читается со своей ставкой: сохранённая история ставок и есть
    # то, ради чего пролонгация — новый договор, а не правка старого.
    assert our_lease.valid_to == date(2025, 12, 31)
    assert our_lease.subjects.get().rate == Decimal("450000.00")


def test_a_lease_of_another_organisation_does_not_fill_the_form_by_its_address(
    client, administrator, central, their_office, make_lease, make_subject, make_org
):
    """Ключ подставляют в адрес руками: чужой договор по нему открыться не должен.

    Сторона в списке арендаторов при этом общая: она заводится один раз на всю
    систему, и «Незабудка ТОО» — не данные клиента, а сама Сторона. Чужой договор —
    данные: ни его номер, ни его арендатор, ни его помещения на форму не встают.
    """
    their_tenant = make_org("Незабудка ТОО", "201140031474").party
    theirs = make_lease(central, their_tenant, number="ЧУЖОЙ-1")
    make_subject(theirs, their_office)
    client.force_login(administrator)

    response = client.get(f"{list_url()}?prolongs={theirs.pk}")

    offered = response.context["writing"]
    assert "ЧУЖОЙ-1" not in response.content.decode()
    assert offered.form["prolongs"].value() is None
    assert offered.form["tenant"].value() is None
    assert offered.subjects.forms[0]["space"].value() is None


def test_an_address_naming_no_lease_at_all_opens_a_blank_form(client, administrator):
    """Сломать экран правкой его адреса не должно быть возможно."""
    page = open_page(client, administrator, f"{list_url()}?prolongs=не-ключ-вовсе")

    assert 'data-lease-form="create"' in page


# Доступ


@pytest.mark.parametrize("action", ["create", "correct", "delete"])
def test_an_anonymous_write_request_is_sent_to_the_login_screen(
    client, downtown, tenant, office, our_lease, action
):
    """До входа не пишут ничего — как и не читают."""
    url, data = {
        "create": (list_url(), entered(downtown, tenant, subject(office))),
        "correct": (card_url(our_lease), entered(downtown, tenant, subject(office))),
        "delete": (delete_url(our_lease), {}),
    }[action]

    response = client.post(url, data)

    assert response.status_code == 302
    assert reverse("login") in response.url
    assert Lease.objects.count() == 1
    assert Lease.objects.get().number == "12-А"


def test_a_platform_wide_staff_flag_grants_nothing(
    client, django_user_model, downtown, tenant, office
):
    """Право вести данные даёт флаг на членстве, а не `is_staff` (ADR 0005)."""
    staffer = django_user_model.objects.create_user("clerk", is_staff=True)
    OrgMembership.objects.create(user=staffer, org=downtown, is_admin=False)
    client.force_login(staffer)

    assert "data-lease-form" not in client.get(list_url()).content.decode()
    assert client.post(list_url(), entered(downtown, tenant, subject(office))).status_code == 403
    assert Lease.objects.count() == 0


def test_administering_one_organisation_does_not_administer_another(
    client, django_user_model, downtown, central, their_office, tenant, make_lease,
    make_subject
):
    """Администраторство принадлежит паре «сотрудник + организация» (ADR 0005)."""
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=False)
    theirs = make_lease(central, tenant)
    make_subject(theirs, their_office)

    page = open_page(client, user, card_url(theirs))

    assert "data-lease-form" not in page
    assert "data-lease-delete" not in page
    assert client.post(delete_url(theirs)).status_code == 403


def test_a_superuser_creates_a_lease_without_granting_themselves_a_membership(
    client, django_user_model, downtown, tenant, office
):
    """Разработчик воспроизводит проблему клиента, не выписывая себе членство."""
    client.force_login(django_user_model.objects.create_superuser("developer"))

    response = client.post(list_url(), entered(downtown, tenant, subject(office)))

    assert response.status_code == 302
    assert Lease.objects.count() == 1


# Разметка


@pytest.mark.parametrize("screen", ["list", "card"])
def test_the_page_with_the_form_carries_no_leftover_template_comments(
    client, administrator, our_lease, screen
):
    """Многострочный `{# … #}` Django комментарием не считает и печатает на экране."""
    url = list_url() if screen == "list" else card_url(our_lease)

    assert "{#" not in open_page(client, administrator, url)
