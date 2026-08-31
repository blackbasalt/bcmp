"""Правка и удаление аренды на карточке помещения — две отправки на тот же адрес.

The seam is `building_passport:space_card` again, and deliberately so: правка and удаление
stand in the аренда block on the карточка, are submitted to the карточка's own address and
are told apart by `submitted`, the way five submissions share the документ's page. The stage
adds no address, so there is no second place for a test to look.

Two footholds in the markup, both inside the row the аренда is printed on — `data-lease` is
already the row's key, so everything about one аренда is read within its own row rather than
by hunting the page for the right form:

- `data-lease-edit` on the form правки: whether правка is offered at all, which is how the
  administrator right is checked;
- `data-deletion` beside it, mirroring the документ's page: whether удаление is offered or
  the screen is holding the question over it.

What is pinned here by name, because it is what a future reader will try to "fix": a съезд
is a дата «по» and not a deletion — the аренда stays in the base and goes behind the
складка; and there is no «продлить», because продление is a new аренда (ADR 0017).
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse

from leases.models import Lease
from parties.models import OrgMembership

from .test_card_leases import (
    LEASE,
    carries_a_fold,
    carries_the_block,
    leases_on,
    open_card,
    stated,
)
from .test_lease_entry import card_url, carries_the_form, parties_offered
from .test_lease_entry import offered as offered_in_the_entry_form

pytestmark = pytest.mark.django_db

#: What the screen says about deleting one аренда: offered, or holding the question. Absent
#: from a row shown to whoever may not write — an action that cannot be performed is not
#: named on their screen either.
DELETION = re.compile(r'data-deletion="(?P<state>[^"]+)"')
#: The складка standing open. A question answered into a shut one is a карточка that came
#: back looking exactly as it went.
FOLD_OPEN = re.compile(r"data-past-leases[^>]*\bopen\b")


def row_markup(page, lease) -> str:
    """One аренда's row as it stands in the markup — the form правки included.

    Read as markup rather than as words: правка and удаление are read off attributes, and
    the row is what holds them together with the аренда they are about.
    """
    for row in LEASE.finditer(page):
        if row["key"] == str(lease.pk):
            return row["text"]
    return ""


def carries_the_edit_form(page, lease) -> bool:
    """Whether правка is offered on this аренда at all."""
    return "data-lease-edit" in row_markup(page, lease)


def deletion_state(page, lease):
    """What the row says about deleting this аренда, or None if it does not offer it."""
    found = DELETION.search(row_markup(page, lease))
    return found["state"] if found else None


def offered_on(page, lease, field):
    """The Стороны the form правки of one аренда offers — the list read inside its own row."""
    return parties_offered(row_markup(page, lease), field)


def correct(client, lease, space=None, **fields):
    """Править аренду — the submission that names itself `lease-edit`.

    The арендатор and the дата начала are filled in from the аренда as it stands: правка
    is sent by a form that came up already filled in, and a test about the ставка should not
    have to retype the rest of the аренда to say so.
    """
    filled = {
        "submitted": "lease-edit",
        "lease": str(lease.pk),
        "tenant": str(lease.tenant_id),
        "valid_from": lease.valid_from.isoformat(),
        **fields,
    }
    return client.post(card_url(space or lease.space), filled)


def ask_to_delete(client, lease, space=None):
    """Press «Удалить аренду» — the submission that asks the question and destroys nothing."""
    return client.post(
        card_url(space or lease.space),
        {"submitted": "lease-deletion", "lease": str(lease.pk)},
    )


def confirm_deletion(client, lease, space=None):
    """Answer the question — the submission the confirmation itself sends."""
    return client.post(
        card_url(space or lease.space),
        {"submitted": "lease-deletion-confirmed", "lease": str(lease.pk)},
    )


# Кому правка и удаление предложены


def test_an_administrator_is_offered_the_edit_form_on_the_lease_itself(
    entering, kab305, alpha, make_lease
):
    """Ставка исправляется на месте, а не вторым «правильным» рядом рядом с неправильным."""
    lease = make_lease(kab305, alpha, area_m2=40, rate=4000)

    _, page = open_card(entering, kab305)

    assert carries_the_edit_form(page, lease)
    assert deletion_state(page, lease) == "offered"


def test_a_reader_is_offered_neither_editing_nor_deletion(reader, kab305, alpha, make_lease):
    """Карточка для читателя остаётся экраном, а не бланком (ADR 0005)."""
    lease = make_lease(kab305, alpha, area_m2=40)

    _, page = open_card(reader, kab305)

    assert carries_the_block(page)
    assert str(lease.pk) in leases_on(page)
    assert not carries_the_edit_form(page, lease)
    assert deletion_state(page, lease) is None


def test_administering_one_organisation_does_not_offer_writes_on_another(
    client, django_user_model, downtown, central, make_building, make_floor, make_space,
    alpha, make_lease,
):
    """Администраторство принадлежит паре «сотрудник + организация» (ADR 0005)."""
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=False)
    theirs = make_space(
        make_floor(make_building(central, "ctr"), 1), "ctr-f1-a", "каб1", is_leasable=True
    )
    lease = make_lease(theirs, alpha, area_m2=40)
    client.force_login(user)

    _, page = open_card(client, theirs)

    assert not carries_the_edit_form(page, lease)
    assert deletion_state(page, lease) is None


def test_a_lease_behind_the_fold_is_edited_and_deleted_where_it_stands(
    entering, kab305, alpha, make_lease, today
):
    """Аренда, заведённая по ошибке год назад, исправляется там же, где напечатана."""
    gone = make_lease(
        kab305,
        alpha,
        area_m2=40,
        valid_from=today - timedelta(days=400),
        valid_to=today - timedelta(days=200),
    )

    _, page = open_card(entering, kab305)

    assert carries_the_edit_form(page, gone)
    assert deletion_state(page, gone) == "offered"


# Отправки различаются полем `submitted`


def test_the_writes_name_themselves_on_the_cards_own_address(
    entering, kab305, alpha, make_lease
):
    """Три отправки на один адрес, различаемые полем — как пять на странице документа."""
    lease = make_lease(kab305, alpha, area_m2=40)

    _, page = open_card(entering, kab305)
    row = row_markup(page, lease)

    assert f'hx-post="{card_url(kab305)}"' in row
    assert 'name="submitted" value="lease-edit"' in row
    assert 'name="submitted" value="lease-deletion"' in row


# Правка


def test_the_edit_form_comes_up_filled_in_with_the_lease_as_it_stands(
    entering, kab305, alpha, make_lease, today
):
    """Исправляют то, что записано: форма, пришедшая пустой, стёрла бы остальную аренду."""
    lease = make_lease(kab305, alpha, area_m2=40, rate=4500, contract_no="№17")

    _, page = open_card(entering, kab305)
    form = row_markup(page, lease)

    assert 'value="40.00"' in form
    assert 'value="4500.00"' in form
    assert 'value="№17"' in form
    assert f'value="{lease.valid_from:%Y-%m-%d}"' in form
    assert offered_on(page, lease, "tenant") == {
        str(alpha.pk): f"{alpha.name} — {alpha.bin_iin}"
    }


def test_a_corrected_rate_is_saved_in_place(entering, kab305, alpha, make_lease):
    """Исправленная ставка не заводит второй аренды рядом с неправильной."""
    lease = make_lease(kab305, alpha, area_m2=40, rate=4000)

    response = correct(entering, lease, area_m2="40", rate="4500")

    assert response.status_code == 200
    lease.refresh_from_db()
    assert lease.rate == 4500
    assert Lease.objects.count() == 1


def test_a_correction_answers_with_the_card_redrawn_around_it(
    entering, kab305, alpha, make_lease
):
    """Экран сам себе подтверждение: ни редиректа, ни второго запроса."""
    lease = make_lease(kab305, alpha, area_m2=40, rate=4000)

    response = correct(entering, lease, area_m2="40", rate="4500")
    page = response.content.decode()

    assert carries_the_block(page)
    assert "4 500,00 за м² в месяц" in leases_on(page)[str(lease.pk)]
    assert "Сдано 40 из 300 м²" in stated(page)


def test_a_refused_correction_comes_back_on_the_card_and_changes_nothing(
    entering, kab305, alpha, make_lease, today
):
    """Причина стоит у поля, а аренда в базе остаётся такой, какой была."""
    lease = make_lease(
        kab305, alpha, area_m2=40, rate=4000, valid_from=today - timedelta(days=30)
    )

    response = correct(
        entering,
        lease,
        valid_from=(today - timedelta(days=30)).isoformat(),
        rate="4500",
        valid_to=(today - timedelta(days=60)).isoformat(),
    )
    page = response.content.decode()

    assert response.status_code == 200
    assert "Период заканчивается раньше, чем начинается." in stated(page)
    lease.refresh_from_db()
    assert (lease.rate, lease.valid_to) == (4000, None)


def test_a_refused_correction_leaves_the_row_saying_what_is_recorded(
    entering, kab305, alpha, make_lease, today
):
    """Отказ ничего не записал, и строка не должна читаться как записанная."""
    lease = make_lease(
        kab305, alpha, area_m2=40, rate=4000, valid_from=today - timedelta(days=30)
    )

    response = correct(
        entering,
        lease,
        valid_from=(today - timedelta(days=30)).isoformat(),
        valid_to=(today - timedelta(days=60)).isoformat(),
    )

    row = leases_on(response.content.decode())[str(lease.pk)]
    assert "по сей день" in row


def test_a_correction_keeps_the_lease_where_it_was_and_adds_none(
    entering, kab305, alpha, petrov, make_lease
):
    """Правится названная аренда, а соседние по помещению остаются нетронутыми."""
    corrected = make_lease(kab305, alpha, area_m2=40, rate=4000)
    neighbour = make_lease(kab305, petrov, area_m2=60, rate=3000)

    correct(entering, corrected, area_m2="40", rate="4500")

    neighbour.refresh_from_db()
    assert neighbour.rate == 3000
    assert Lease.objects.count() == 2


# Съезд — это дата «по», а не удаление


def test_a_departure_is_recorded_as_an_end_date_and_the_lease_stays(
    entering, kab305, alpha, make_lease, today
):
    """История аренды помещения не стирается всякий раз, когда кто-то съехал."""
    lease = make_lease(
        kab305, alpha, area_m2=40, valid_from=today - timedelta(days=30)
    )

    response = correct(
        entering,
        lease,
        valid_from=(today - timedelta(days=30)).isoformat(),
        area_m2="40",
        valid_to=(today - timedelta(days=1)).isoformat(),
    )
    page = response.content.decode()

    lease.refresh_from_db()
    assert lease.valid_to == today - timedelta(days=1)
    assert str(lease.pk) in leases_on(page)
    assert "Свободно" in stated(page)
    assert "Прошлые аренды (1)" in stated(page)


def test_there_is_no_button_to_extend_a_lease(entering, kab305, alpha, make_lease):
    """Продление — новая аренда, а не сдвинутый конец у прежней (ADR 0017)."""
    make_lease(kab305, alpha, area_m2=40)

    _, page = open_card(entering, kab305)

    assert "родлить" not in stated(page)


# Удаление в два шага


def test_the_first_submission_asks_and_deletes_nothing(
    entering, kab305, alpha, make_lease
):
    """У записи нет отмены, и промах мыши не должен её стоить."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = ask_to_delete(entering, lease)
    page = response.content.decode()

    assert response.status_code == 200
    assert deletion_state(page, lease) == "confirming"
    assert Lease.objects.filter(pk=lease.pk).exists()


def test_the_question_names_the_tenant_and_says_that_a_departure_is_not_a_deletion(
    entering, kab305, alpha, make_lease
):
    """Иначе съехавшего арендатора удалят вместе с историей помещения."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = ask_to_delete(entering, lease)
    asked = stated(row_markup(response.content.decode(), lease))

    assert "ТОО «Альфа»" in asked
    assert "съехал" in asked
    assert "дату «по»" in asked


def test_a_confirmed_deletion_removes_the_lease_and_redraws_the_card(
    entering, kab305, alpha, make_lease
):
    """Аренда, заведённая по ошибке, удаляется целиком."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = confirm_deletion(entering, lease)
    page = response.content.decode()

    assert response.status_code == 200
    assert not Lease.objects.filter(pk=lease.pk).exists()
    assert carries_the_block(page)
    assert leases_on(page) == {}
    assert "Свободно" in stated(page)


def test_deleting_one_lease_leaves_the_others_on_the_space(
    entering, kab305, alpha, petrov, make_lease
):
    """Удаляется одна аренда, а не всё, что стоит на помещении."""
    mistaken = make_lease(kab305, alpha, area_m2=40)
    kept = make_lease(kab305, petrov, area_m2=60)

    confirm_deletion(entering, mistaken)
    _, page = open_card(entering, kab305)

    assert set(leases_on(page)) == {str(kept.pk)}
    assert "Сдано 60 из 300 м²" in stated(page)


def test_a_past_lease_entered_by_mistake_is_deleted_too(
    entering, kab305, alpha, make_lease, today
):
    """Ошибку заводят и в истории, и убирать её приходится там же."""
    gone = make_lease(
        kab305,
        alpha,
        area_m2=40,
        valid_from=today - timedelta(days=400),
        valid_to=today - timedelta(days=200),
    )

    response = confirm_deletion(entering, gone)

    assert response.status_code == 200
    assert not Lease.objects.exists()


def test_a_question_about_a_lease_behind_the_fold_opens_the_fold(
    entering, kab305, alpha, make_lease, today
):
    """Иначе вопрос задан в закрытую складку, и карточка вернулась такой же, какой ушла."""
    gone = make_lease(
        kab305,
        alpha,
        area_m2=40,
        valid_from=today - timedelta(days=400),
        valid_to=today - timedelta(days=200),
    )

    response = ask_to_delete(entering, gone)
    page = response.content.decode()

    assert deletion_state(page, gone) == "confirming"
    assert FOLD_OPEN.search(page)


def test_a_refused_correction_behind_the_fold_opens_the_fold(
    entering, kab305, alpha, make_lease, today
):
    """Причина отказа, спрятанная под складкой, — это отказ, которого никто не видит."""
    gone = make_lease(
        kab305,
        alpha,
        area_m2=40,
        valid_from=today - timedelta(days=400),
        valid_to=today - timedelta(days=200),
    )

    response = correct(
        entering,
        gone,
        valid_from=(today - timedelta(days=400)).isoformat(),
        valid_to=(today - timedelta(days=500)).isoformat(),
    )

    assert FOLD_OPEN.search(response.content.decode())


def test_the_fold_of_a_card_nobody_asked_anything_about_stays_shut(
    entering, kab305, alpha, make_lease, today
):
    """Складка на то и складка: десять съехавших арендаторов не хоронят того, кто сидит."""
    make_lease(
        kab305,
        alpha,
        area_m2=40,
        valid_from=today - timedelta(days=400),
        valid_to=today - timedelta(days=200),
    )

    _, page = open_card(entering, kab305)

    assert carries_a_fold(page)
    assert not FOLD_OPEN.search(page)


def test_asking_about_one_lease_does_not_ask_about_another(
    entering, kab305, alpha, petrov, make_lease
):
    """Вопрос задан о названной аренде: соседняя строка не должна выглядеть спрошенной."""
    asked_about = make_lease(kab305, alpha, area_m2=40)
    other = make_lease(kab305, petrov, area_m2=60)

    response = ask_to_delete(entering, asked_about)
    page = response.content.decode()

    assert deletion_state(page, asked_about) == "confirming"
    assert deletion_state(page, other) == "offered"


def test_deleting_a_lease_that_is_already_gone_answers_that_it_is_missing(
    entering, kab305, alpha, make_lease
):
    """Второй щелчок двойного: аренды, названной отправкой, больше нет."""
    lease = make_lease(kab305, alpha, area_m2=40)
    confirm_deletion(entering, lease)

    response = confirm_deletion(entering, lease)

    assert response.status_code == 404


def test_a_key_that_names_no_lease_of_this_space_is_answered_as_missing(
    entering, kab305
):
    """Адрес набирают и вставляют руками, и ключ, который не ключ, — тот же ответ."""
    response = entering.post(
        card_url(kab305), {"submitted": "lease-edit", "lease": "не-ключ"}
    )

    assert response.status_code == 404


def test_a_lease_of_another_space_is_not_edited_through_this_card(
    entering, kab305, lobby, alpha, make_lease
):
    """Карточка ведёт аренды своего помещения: право на запись спрошено о нём."""
    lease = make_lease(lobby, alpha, area_m2=2, rate=4000)

    response = correct(entering, lease, space=kab305, rate="9999")

    assert response.status_code == 404
    lease.refresh_from_db()
    assert lease.rate == 4000


# Права и изоляция


def test_a_reader_cannot_correct_a_lease_by_posting_directly(
    reader, kab305, alpha, make_lease
):
    """Право спрошено о запросе, а не только о том, что предложено на экране."""
    lease = make_lease(kab305, alpha, area_m2=40, rate=4000)

    response = correct(reader, lease, rate="9999")

    assert response.status_code == 403
    lease.refresh_from_db()
    assert lease.rate == 4000


def test_a_reader_cannot_delete_a_lease_by_posting_directly(
    reader, kab305, alpha, make_lease
):
    """Читателю аренду не удалить и в обход экрана."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = confirm_deletion(reader, lease)

    assert response.status_code == 403
    assert Lease.objects.filter(pk=lease.pk).exists()


def test_a_reader_is_not_even_allowed_to_ask_the_question(
    reader, kab305, alpha, make_lease
):
    """Подтверждение — экран удаления, и отказывают в нём вместе с удалением."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = ask_to_delete(reader, lease)

    assert response.status_code == 403


def test_correcting_a_lease_of_another_organisation_is_refused(
    entering, central, make_building, make_floor, make_space, alpha, make_lease
):
    """Форма правки — не обход изоляции (ADR 0001, ADR 0018)."""
    theirs = make_space(
        make_floor(make_building(central, "ctr"), 1), "ctr-f1-a", "каб1", is_leasable=True
    )
    lease = make_lease(theirs, alpha, area_m2=40, rate=4000)

    response = correct(entering, lease, rate="9999")

    assert response.status_code == 404
    lease.refresh_from_db()
    assert lease.rate == 4000


def test_deleting_a_lease_of_another_organisation_is_refused(
    entering, central, make_building, make_floor, make_space, alpha, make_lease
):
    """Чужое помещение отвечает «нет такого» и на запись — как и на чтение (ADR 0001)."""
    theirs = make_space(
        make_floor(make_building(central, "ctr"), 1), "ctr-f1-a", "каб1", is_leasable=True
    )
    lease = make_lease(theirs, alpha, area_m2=40)

    response = confirm_deletion(entering, lease)

    assert response.status_code == 404
    assert Lease.objects.filter(pk=lease.pk).exists()


def test_an_anonymous_request_to_delete_is_sent_to_login(client, kab305, alpha, make_lease):
    """До входа ничего не удаляется — как ничего и не читается."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = confirm_deletion(client, lease)

    assert response.status_code == 302
    assert reverse("login") in response.url
    assert Lease.objects.filter(pk=lease.pk).exists()


# Поиск Стороны в форме правки


def test_the_search_from_an_edit_form_comes_back_into_that_form(
    entering, kab305, alpha, petrov, make_lease
):
    """Поиск перерисовывает карточку, и найденное возвращается в ту форму, что спросила.

    Найденный встаёт рядом с уже выбранным, а не вместо него: сделанный выбор не исчезает
    из своего же списка, иначе поиск замены стоил бы арендатора, которого правят.
    """
    lease = make_lease(kab305, alpha, area_m2=40)

    response = entering.get(
        card_url(kab305), {"lease": str(lease.pk), "submitted": "lease-edit", "tenant_q": "петров"}
    )
    page = response.content.decode()

    assert set(offered_on(page, lease, "tenant")) == {str(petrov.pk), str(alpha.pk)}


def test_a_search_from_an_edit_form_does_not_fill_in_the_entry_form(
    entering, kab305, alpha, petrov, make_lease
):
    """Форма заведения не должна открываться заполненной тем, чего в неё не вводили."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = entering.get(
        card_url(kab305),
        {"lease": str(lease.pk), "submitted": "lease-edit", "tenant_q": "петров", "rate": "99999"},
    )
    page = response.content.decode()

    assert carries_the_form(page)
    assert offered_in_the_entry_form(page, "tenant") == {}


def test_an_address_naming_a_lease_without_the_field_does_not_open_a_correction(
    entering, kab305, alpha, petrov, make_lease
):
    """Отправку узнают по полю `submitted`, и поиск — та же отправка, только в адресе."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = entering.get(
        card_url(kab305), {"lease": str(lease.pk), "tenant_q": "петров", "rate": "99999"}
    )
    page = response.content.decode()

    assert offered_on(page, lease, "tenant") == {
        str(alpha.pk): f"{alpha.name} — {alpha.bin_iin}"
    }
    assert 'value="99999"' not in row_markup(page, lease)


def test_the_search_from_the_entry_form_leaves_the_edit_forms_as_they_were(
    entering, kab305, alpha, petrov, make_lease
):
    """Адрес без ключа аренды спрашивает от имени формы заведения, и только её."""
    lease = make_lease(kab305, alpha, area_m2=40)

    response = entering.get(card_url(kab305), {"tenant_q": "петров"})
    page = response.content.decode()

    assert offered_on(page, lease, "tenant") == {
        str(alpha.pk): f"{alpha.name} — {alpha.bin_iin}"
    }
