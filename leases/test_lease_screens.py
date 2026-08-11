"""Список договоров и карточка договора — то, что сотрудник УК видит по HTTP.

Шов тот же, что у экранов паспорта: граница HTTP. Тест ходит тестовым клиентом по
именованным адресам от имени пользователя с известным членством и проверяет
наблюдаемое — что на экране и какой код ответа. Разметка и классы не проверяются:
перестройка вёрстки ниже уровня URL не должна переписывать набор тестов.

Отдельно проверяется третий чокпоинт: договор не принадлежит ни одному БЦ, поэтому
изоляция клиентов на нём стоит своя (ADR 0009), и её ошибка не поймается ни одним
тестом помещений.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from parties.models import OrgMembership, Party

pytestmark = pytest.mark.django_db


def list_url():
    return reverse("leases:lease_list")


def card_url(lease):
    return reverse("leases:lease_detail", args=[lease.pk])


def open_page(client, url):
    response = client.get(url)
    return response, response.content.decode()


@pytest.fixture
def their_lease(central, their_office, make_lease, make_subject):
    """Договор другого клиента платформы — со своим арендатором и своим помещением."""
    their_tenant = Party.objects.create(
        kind=Party.Kind.COMPANY, name="Незабудка ТОО", bin_iin="201140031474"
    )
    lease = make_lease(central, their_tenant, number="ЧУЖОЙ-1")
    make_subject(lease, their_office)
    return lease


@pytest.fixture
def our_lease(downtown, tenant, office, warehouse, make_lease, make_subject):
    """Договор на офис в Manhattan и склад в Boston — заполнен целиком."""
    lease = make_lease(
        downtown,
        tenant,
        date(2025, 1, 1),
        date(2025, 12, 31),
        number="12-А",
        signed_at=date(2024, 12, 20),
    )
    make_subject(lease, office, rate=Decimal("450000.00"), area_m2=Decimal("52.30"))
    make_subject(lease, warehouse, rate=Decimal("90000.00"))
    return lease


# Список договоров


def test_the_list_shows_what_tells_the_leases_apart(client, member, our_lease):
    """Арендатор, срок, номер и сколько помещений названо — по чему договор и ищут."""
    client.force_login(member)

    response, page = open_page(client, list_url())

    assert response.status_code == 200
    assert "Ромашка ТОО" in page
    assert "01.01.2025 — 31.12.2025" in page
    assert "12-А" in page
    assert "2 помещения" in page


def test_the_list_counts_the_spaces_the_lease_names(
    client, member, downtown, tenant, office, first_floor, make_leasable, make_lease,
    make_subject
):
    """Сколько помещений в договоре — число словом при нём, а не цифра без подписи."""
    single = make_lease(downtown, tenant, date(2020, 1, 1), date(2020, 12, 31))
    make_subject(single, office)
    many = make_lease(downtown, tenant, date(2021, 1, 1), date(2021, 12, 31))
    for index in range(5):
        make_subject(many, make_leasable(first_floor, f"man-f1-20{index}", f"Офис 20{index}"))
    client.force_login(member)

    _, page = open_page(client, list_url())

    assert "1 помещение" in page
    assert "5 помещений" in page


def test_a_lease_without_a_number_reads_as_no_data_rather_than_as_a_blank(
    client, member, downtown, tenant, office, make_lease, make_subject
):
    """Пустое место в столбце можно прочитать как «номера нет»; прочерк — нельзя."""
    make_subject(make_lease(downtown, tenant), office)
    client.force_login(member)

    _, page = open_page(client, list_url())

    assert "— нет данных" in page


def test_an_open_ended_lease_reads_as_in_force_rather_than_as_never_in_force(
    client, member, downtown, tenant, office, make_lease, make_subject
):
    """Пустая дата окончания — «по сей день», как у периодов планов (ADR 0007)."""
    make_subject(make_lease(downtown, tenant, date(2025, 3, 1)), office)
    client.force_login(member)

    _, page = open_page(client, list_url())

    assert "01.03.2025 — по сей день" in page


def test_the_newest_lease_is_listed_first(
    client, member, downtown, tenant, office, make_lease, make_subject
):
    """Свежий договор сверху: с ним и работают, а прошлогодний ищут по номеру."""
    make_subject(make_lease(downtown, tenant, date(2024, 1, 1), date(2024, 12, 31),
                            number="11-А"), office)
    make_subject(make_lease(downtown, tenant, date(2025, 1, 1), date(2025, 12, 31),
                            number="12-А"), office)
    client.force_login(member)

    _, page = open_page(client, list_url())

    assert page.index("12-А") < page.index("11-А")


def test_an_empty_list_explains_itself_rather_than_rendering_a_blank_table(
    client, member
):
    """Новый клиент должен увидеть, с чего начать, а не пустую таблицу."""
    client.force_login(member)

    response, page = open_page(client, list_url())

    assert response.status_code == 200
    assert "не заведено" in page


def test_the_list_opens_the_card_of_its_lease(client, member, our_lease):
    """Открыть договор — щелчок по строке, а не поиск в админке."""
    client.force_login(member)

    _, page = open_page(client, list_url())
    opened = client.get(card_url(our_lease))

    assert card_url(our_lease) in page
    assert opened.status_code == 200


# Карточка договора


def test_the_card_names_the_lease_in_full(client, member, our_lease):
    """Арендатор, период, номер и дата подписания — всё, чем договор назван на бумаге."""
    client.force_login(member)

    response, page = open_page(client, card_url(our_lease))

    assert response.status_code == 200
    assert "Ромашка ТОО" in page
    assert "01.01.2025 — 31.12.2025" in page
    assert "12-А" in page
    assert "20.12.2024" in page


def test_the_card_names_every_subject_with_its_rate_and_contract_area(
    client, member, our_lease
):
    """Предмет — помещение со своей ставкой и своей договорной площадью, а не строка."""
    client.force_login(member)

    _, page = open_page(client, card_url(our_lease))

    assert "Офис 101" in page
    assert "Склад" in page  # предмет из другого БЦ того же договора
    assert "450 000,00" in page
    assert "90 000,00" in page
    assert "52,30 м²" in page


def test_a_subject_without_a_rate_reads_as_no_data(
    client, member, downtown, tenant, office, make_lease, make_subject
):
    """Ставку заводят не сразу, и пустая клетка прочиталась бы как «бесплатно».

    Договорная площадь у предмета при этом есть: она показывает, что прочерков ровно
    столько, сколько пустых полей, — а не столько, сколько клеток в таблице.
    """
    lease = make_lease(downtown, tenant)
    make_subject(lease, office, area_m2=Decimal("52.30"))
    client.force_login(member)

    _, page = open_page(client, card_url(lease))

    assert "52,30 м²" in page  # площадь предмета — неразрывными пробелами
    assert page.count("— нет данных") == 3  # номер, дата подписания и ставка


def test_a_space_outside_any_building_leaves_the_building_unnamed(
    client, member, downtown, tenant, office, make_lease, make_subject
):
    """Здание у помещения может быть не проставлено — это «нет данных», а не поломка.

    Бизнес-центр назван рядом с помещением, потому что договор называет помещения
    нескольких БЦ. Помещение, загруженное без здания, эту клетку оставляет пустой, и
    падать на ней экран не должен.
    """
    office.building = None
    office.save(update_fields=["building"])
    lease = make_lease(downtown, tenant)
    make_subject(lease, office)
    client.force_login(member)

    response, page = open_page(client, card_url(lease))

    assert response.status_code == 200
    assert "Офис 101" in page
    assert "Manhattan" not in page


def test_a_renewal_names_the_lease_it_prolongs(
    client, member, downtown, tenant, office, make_lease, make_subject
):
    """Пролонгация — новый договор со ссылкой на прежний, и ссылка видна (ADR 0007)."""
    ended = make_lease(downtown, tenant, date(2024, 1, 1), date(2024, 12, 31), number="11-А")
    make_subject(ended, office)
    renewal = make_lease(
        downtown, tenant, date(2025, 1, 1), date(2025, 12, 31), prolongs=ended
    )
    make_subject(renewal, office)
    client.force_login(member)

    _, page = open_page(client, card_url(renewal))

    assert "11-А" in page
    assert card_url(ended) in page


def test_a_prior_lease_of_another_organisation_is_not_named(
    client, member, downtown, tenant, office, their_lease, make_lease, make_subject
):
    """Ссылку на прежний договор ведут руками, и вести её на чужой ничто не мешает.

    На экран прежний договор едет тем же чокпоинтом, что и сам открытый: второе
    место, решающее чьи данные показывать, — это способ им однажды разойтись.
    """
    renewal = make_lease(downtown, tenant, prolongs=their_lease)
    make_subject(renewal, office)
    client.force_login(member)

    response, page = open_page(client, card_url(renewal))

    assert response.status_code == 200
    assert "ЧУЖОЙ-1" not in page
    assert "Незабудка ТОО" not in page


# Доступ и изоляция


def test_a_member_sees_their_own_leases_and_not_another_clients(
    client, member, our_lease, their_lease
):
    """Изоляция клиентов на договорах — ровно то, ради чего заведён третий чокпоинт."""
    client.force_login(member)

    _, page = open_page(client, list_url())

    assert "Ромашка ТОО" in page
    assert "Незабудка ТОО" not in page
    assert card_url(their_lease) not in page


def test_another_organisations_lease_is_missing_rather_than_forbidden(
    client, member, their_lease
):
    """Ответ, отличающий «нельзя» от «нет», подтвердил бы, что данные клиента есть."""
    client.force_login(member)

    response, _ = open_page(client, card_url(their_lease))

    assert response.status_code == 404


def test_a_user_without_membership_reaches_no_lease_at_all(
    client, django_user_model, our_lease
):
    """Членства нет — нет и договоров: чокпоинт молчит одинаково для всех чужих."""
    client.force_login(django_user_model.objects.create_user("newcomer"))

    listed, page = open_page(client, list_url())
    opened, _ = open_page(client, card_url(our_lease))

    assert listed.status_code == 200
    assert "Ромашка ТОО" not in page
    assert opened.status_code == 404


def test_a_superuser_reaches_every_organisations_leases(
    client, django_user_model, our_lease, their_lease
):
    """Разработчик воспроизводит проблему клиента, не выписывая себе членство."""
    client.force_login(django_user_model.objects.create_superuser("developer"))

    _, page = open_page(client, list_url())
    opened, _ = open_page(client, card_url(their_lease))

    assert "Ромашка ТОО" in page
    assert "Незабудка ТОО" in page
    assert opened.status_code == 200


def test_a_member_of_both_organisations_sees_both_sets(
    client, django_user_model, downtown, central, our_lease, their_lease
):
    """Сотрудник, ведущий двух клиентов, видит договоры обоих — и ничего сверх того."""
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown)
    OrgMembership.objects.create(user=user, org=central)
    client.force_login(user)

    _, page = open_page(client, list_url())

    assert "Ромашка ТОО" in page
    assert "Незабудка ТОО" in page


@pytest.mark.parametrize("screen", ["list", "card"])
def test_an_anonymous_visitor_is_sent_to_the_login_screen(client, our_lease, screen):
    """Про арендаторов наших клиентов без сессии не видно ничего."""
    url = list_url() if screen == "list" else card_url(our_lease)

    response, _ = open_page(client, url)

    assert response.status_code == 302
    assert "/login/" in response["Location"]


# Разметка


@pytest.mark.parametrize("screen", ["list", "card"])
def test_the_page_carries_no_leftover_template_comments(
    client, member, our_lease, screen
):
    """Многострочный `{# … #}` Django комментарием не считает и печатает на экране."""
    client.force_login(member)
    url = list_url() if screen == "list" else card_url(our_lease)

    _, page = open_page(client, url)

    assert "{#" not in page
