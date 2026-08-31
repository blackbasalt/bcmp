"""Заведение аренды на карточке помещения — форма и выбор Стороны поиском.

The seam is `building_passport:space_card`, the карточка's own address: the form stands on
the карточка and is submitted to that same address, where a refusal has the карточка to come
back onto (ADR 0005). The stage adds no address of its own, so there is no second place for
a test to look either — заведение, the refusal and the поиск Стороны are all read off this
one response.

The footholds in the markup are `data-lease-form` on the form, mirroring `data-upload` on
the two upload forms: it says whether заведение is offered at all, which is how the
administrator right is checked. Which Стороны the search found is read off the `<select>`
they are chosen from, by their keys — a label is a phrase and may be reworded, a key is the
contract.

Manhattan, its first floor and the администратор организации come from the root `conftest`;
the помещения and the Стороны from `leases/conftest.py`. What is defined here is only the
submission itself.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from leases.models import Lease
from parties.models import OrgMembership, Party

from .test_card_leases import carries_the_block, leases_on, open_card, stated

pytestmark = pytest.mark.django_db

#: The Стороны a field offers — what the search found, as the screen puts it on the list.
OFFERED = re.compile(
    r'<select[^>]*name="(?P<field>tenant|landlord)"[^>]*>(?P<options>.*?)</select>', re.DOTALL
)
OPTION = re.compile(r'<option[^>]*value="(?P<key>[^"]*)"[^>]*>(?P<label>.*?)</option>', re.DOTALL)


def carries_the_form(page) -> bool:
    """Whether заведение is offered on this карточка at all."""
    return "data-lease-form" in page


def offered(page, field):
    """The Стороны on offer for one field, by key: what the поиск put on the list."""
    for select in OFFERED.finditer(page):
        if select["field"] == field:
            return {
                option["key"]: stated(option["label"])
                for option in OPTION.finditer(select["options"])
                if option["key"]
            }
    return {}


def card_url(space):
    return reverse("building_passport:space_card", args=[space.pk])


def enter(client, space, tenant=None, **fields):
    """Submit the аренда form — to the карточка's own address, the one it stands on."""
    filled = {"valid_from": timezone.localdate().isoformat(), **fields}
    if tenant is not None:
        filled["tenant"] = str(tenant.pk)
    return client.post(card_url(space), filled)


def search(client, space, **asked):
    """The поиск Стороны: a parameter on the карточка's own address, redrawing the карточка."""
    response = client.get(card_url(space), asked)
    return response, response.content.decode()


@pytest.fixture
def today():
    return timezone.localdate()


@pytest.fixture
def reader(client, member):
    """A сотрудник УК without the administrator right — the card is a screen, not a form."""
    client.force_login(member)
    return client


@pytest.fixture
def entering(client, administrator):
    """The администратор организации: the one the form is offered to (ADR 0005)."""
    client.force_login(administrator)
    return client


# Кому форма предложена


def test_an_administrator_of_the_organisation_is_offered_the_form(entering, kab305):
    """An аренда is entered where the помещение is already open in front of the reader."""
    _, page = open_card(entering, kab305)

    assert carries_the_form(page)


def test_a_member_without_the_right_is_offered_no_form_at_all(reader, kab305):
    """An action that would be refused is not offered, and the карточка stays a screen."""
    _, page = open_card(reader, kab305)

    assert carries_the_block(page)
    assert not carries_the_form(page)


def test_administering_one_organisation_does_not_offer_the_form_on_another(
    client, django_user_model, downtown, central, make_building, make_floor, make_space
):
    """Администраторство belongs to the pair «сотрудник + организация» (ADR 0005)."""
    user = django_user_model.objects.create_user("consultant")
    OrgMembership.objects.create(user=user, org=downtown, is_admin=True)
    OrgMembership.objects.create(user=user, org=central, is_admin=False)
    theirs = make_space(
        make_floor(make_building(central, "ctr"), 1), "ctr-f1-a", "каб1", is_leasable=True
    )
    client.force_login(user)

    _, page = open_card(client, theirs)

    assert not carries_the_form(page)


def test_the_form_is_submitted_to_the_card_itself(entering, kab305):
    """Никакого нового адреса: the write goes where the карточка already is (ADR 0005)."""
    _, page = open_card(entering, kab305)

    assert f'hx-post="{card_url(kab305)}"' in page


# Что обязательно


def test_a_tenant_and_a_start_date_are_enough(entering, kab305, alpha, today):
    """Entering what is known is not blocked by what is not."""
    response = enter(entering, kab305, alpha)

    assert response.status_code == 200
    lease = Lease.objects.get()
    assert (lease.space, lease.tenant, lease.valid_from) == (kab305, alpha, today)
    assert (lease.landlord, lease.rate, lease.valid_to) == (None, None, None)


def test_an_empty_area_is_recorded_as_not_entered_and_never_as_the_whole_room(
    entering, kab305, alpha
):
    """Одно пустое поле не носит двух противоположных смыслов."""
    enter(entering, kab305, alpha, area_m2="")

    lease = Lease.objects.get()
    assert lease.area_m2 is None
    assert kab305.area_m2 == 300


def test_everything_entered_is_written_down(entering, kab305, alpha, petrov, today):
    """Арендодатель, площадь, ставка и номер договора — необязательны, но записываются."""
    enter(
        entering,
        kab305,
        alpha,
        landlord=str(petrov.pk),
        area_m2="40",
        rate="4500",
        contract_no="№17",
        valid_to=(today + timedelta(days=300)).isoformat(),
    )

    lease = Lease.objects.get()
    assert (lease.landlord, lease.area_m2, lease.rate) == (petrov, 40, 4500)
    assert (lease.contract_no, lease.valid_to) == ("№17", today + timedelta(days=300))


def test_a_lease_without_a_tenant_is_refused(entering, kab305):
    """«Кто сидит» is the one thing an аренда exists to answer."""
    response = enter(entering, kab305)

    assert response.status_code == 200
    assert Lease.objects.count() == 0


def test_a_lease_without_a_start_date_is_refused(entering, kab305, alpha):
    """A record that cannot say whether it is in force today answers nothing."""
    response = enter(entering, kab305, alpha, valid_from="")

    assert response.status_code == 200
    assert Lease.objects.count() == 0


# Отказ и успех


def test_a_period_that_ends_before_it_begins_is_refused(entering, kab305, alpha, today):
    """A typo in a date is caught where it is made — and nothing is written."""
    response = enter(
        entering, kab305, alpha, valid_to=(today - timedelta(days=1)).isoformat()
    )

    assert response.status_code == 200
    assert "Период заканчивается раньше, чем начинается." in stated(response.content.decode())
    assert Lease.objects.count() == 0


def test_a_refusal_comes_back_on_the_card_and_keeps_what_was_typed(
    entering, kab305, alpha, today
):
    """The reason stands next to the field, and the аренда is fixed rather than retyped."""
    response = enter(
        entering,
        kab305,
        alpha,
        area_m2="40",
        rate="4500",
        contract_no="№17",
        valid_to=(today - timedelta(days=1)).isoformat(),
    )
    page = response.content.decode()

    assert carries_the_block(page)
    assert carries_the_form(page)
    assert offered(page, "tenant") == {str(alpha.pk): f"{alpha.name} — {alpha.bin_iin}"}
    assert 'value="40"' in page
    assert 'value="4500"' in page
    assert 'value="№17"' in page


def test_a_successful_entry_answers_with_the_card_redrawn_around_the_new_lease(
    entering, kab305, alpha
):
    """Экран сам себе подтверждение: there is no redirect and no second request."""
    response = enter(entering, kab305, alpha, area_m2="40")
    page = response.content.decode()

    assert response.status_code == 200
    lease = Lease.objects.get()
    assert leases_on(page)[str(lease.pk)].startswith("ТОО «Альфа»")
    assert "Сдано 40 из 300 м²" in stated(page)


def test_a_successful_entry_offers_an_empty_form_again(entering, kab305, alpha):
    """The next аренда of a shared помещение is entered without reopening the карточка."""
    response = enter(entering, kab305, alpha, area_m2="40")
    page = response.content.decode()

    assert carries_the_form(page)
    assert offered(page, "tenant") == {}


# Помещения, на которых аренда заводится


def test_a_lease_is_entered_on_a_common_space(entering, lobby, alpha):
    """The банкомат in the лобби is recordable — it surfaces as a находка, not as a refusal."""
    response = enter(entering, lobby, alpha, area_m2="2")

    assert response.status_code == 200
    assert Lease.objects.get().space == lobby


def test_a_lease_is_entered_on_a_technical_space(entering, first_floor, make_space, alpha):
    """A венткамера let by a slip of the dropdown is a находка on the полка, not a refusal."""
    itp = make_space(first_floor, "man-f1-t", "Венткамера", area_m2=20)

    response = enter(entering, itp, alpha)

    assert response.status_code == 200
    assert Lease.objects.get().space == itp


def test_the_form_stands_on_a_common_space_with_no_leases(entering, lobby):
    """Without the form there the банкомат in the лобби has nowhere to be entered."""
    _, page = open_card(entering, lobby)

    assert carries_the_form(page)


def test_a_reader_still_gets_no_block_on_an_empty_common_space(reader, lobby):
    """A section promising data that does not exist is not put in front of a reader."""
    _, page = open_card(reader, lobby)

    assert not carries_the_block(page)


# Изоляция и вход


def test_entering_a_lease_on_another_organisations_space_is_refused(
    entering, central, make_building, make_floor, make_space, alpha
):
    """The form is not a way round the checkpoint (ADR 0001, ADR 0005)."""
    theirs = make_space(
        make_floor(make_building(central, "ctr"), 1), "ctr-f1-a", "каб1", is_leasable=True
    )

    response = enter(entering, theirs, alpha)

    assert response.status_code == 404
    assert Lease.objects.count() == 0


def test_a_member_without_the_right_cannot_enter_a_lease_by_posting_directly(
    reader, kab305, alpha
):
    """It is not only the form that is withheld: the right is checked on the request itself."""
    response = enter(reader, kab305, alpha)

    assert response.status_code == 403
    assert Lease.objects.count() == 0


def test_an_anonymous_request_to_the_form_is_sent_to_login(client, kab305, alpha):
    """Before signing in nothing is written — just as nothing is read."""
    response = enter(client, kab305, alpha)

    assert response.status_code == 302
    assert reverse("login") in response.url
    assert Lease.objects.count() == 0


# Выбор Стороны поиском


def test_the_search_redraws_the_card_with_the_matches(entering, kab305, alpha, petrov):
    """В реестре 699 Сторон — списком это не выбирается, и поиск едет в адресе."""
    response, page = search(entering, kab305, tenant_q="аль")

    assert response.status_code == 200
    assert carries_the_block(page)
    assert set(offered(page, "tenant")) == {str(alpha.pk)}


def test_nothing_is_offered_until_something_is_looked_for(entering, kab305, alpha, petrov):
    """A list of 699 Сторон is not a choice, it is a scroll."""
    _, page = open_card(entering, kab305)

    assert offered(page, "tenant") == {}


def test_the_search_finds_a_party_by_its_bin(entering, kab305, alpha, petrov):
    """Две компании с похожими названиями различаются номером."""
    _, page = search(entering, kab305, tenant_q=alpha.bin_iin)

    assert set(offered(page, "tenant")) == {str(alpha.pk)}


def test_the_offered_party_is_named_with_its_bin(entering, kab305, alpha):
    """Иначе два «ТОО «Альфа»» на списке — это выбор наугад."""
    _, page = search(entering, kab305, tenant_q="аль")

    assert offered(page, "tenant")[str(alpha.pk)] == f"{alpha.name} — {alpha.bin_iin}"


def test_the_search_folds_case_for_russian(entering, kab305, alpha):
    """«альфа» finds «Альфа»: on SQLite `LIKE` folds case for ASCII alone (ADR 0014)."""
    _, page = search(entering, kab305, tenant_q="альфа")

    assert set(offered(page, "tenant")) == {str(alpha.pk)}


def test_the_search_looks_across_all_parties_and_not_across_one_organisation(
    entering, kab305, central
):
    """Реестр Сторон общесистемный, а изоляция стоит на помещении (ADR 0018).

    Otherwise a new арендатор nobody has met yet could not be found at all — and the Сторона
    of another client's организация is a Сторона like any other in that register.
    """
    _, page = search(entering, kab305, tenant_q="Central")

    assert set(offered(page, "tenant")) == {str(central.party.pk)}


def test_the_same_search_is_offered_for_the_landlord(entering, kab305, alpha, petrov):
    """Два поля ведут себя одинаково — иначе одно из них учат отдельно."""
    _, page = search(entering, kab305, landlord_q="альфа")

    assert set(offered(page, "landlord")) == {str(alpha.pk)}


def test_the_search_keeps_what_has_already_been_typed(entering, kab305, alpha):
    """Поиск арендодателя не стирает набранного об аренде."""
    _, page = search(entering, kab305, tenant=str(alpha.pk), area_m2="40", landlord_q="петров")

    assert set(offered(page, "tenant")) == {str(alpha.pk)}
    assert 'value="40"' in page


def test_an_address_that_asks_no_search_fills_the_form_in_with_nothing(entering, kab305):
    """Бланк заполняет тот, кто заводит аренду, а не тот, кто прислал ссылку.

    Without the gate `…/card/?rate=99999&valid_from=2020-01-01` would open the карточка with
    a дата начала nobody typed — and a pre-filled date is accepted without a glance
    (ADR 0004).
    """
    _, page = search(entering, kab305, rate="99999", valid_from="2020-01-01")

    assert 'value="99999"' not in page
    assert 'value="2020-01-01"' not in page


def test_what_was_typed_comes_back_only_alongside_a_search(entering, kab305):
    """It is the поиск that redraws the карточка, so it is the поиск that carries the form."""
    _, page = search(entering, kab305, rate="99999", tenant_q="альфа")

    assert 'value="99999"' in page


def test_a_party_that_is_not_found_is_offered_as_a_separate_step_and_is_not_created(
    entering, kab305, alpha
):
    """Иначе реестр набьётся «ТОО Альфа», «Альфа ТОО» и «ТОО «Альфа»»."""
    before = Party.objects.count()

    _, page = search(entering, kab305, tenant_q="Гамма")

    assert offered(page, "tenant") == {}
    assert "Сторону заводят отдельно" in stated(page)
    assert Party.objects.count() == before


def test_the_form_creates_no_party_of_its_own(entering, kab305, alpha):
    """Арендатор выбирается из реестра, а не набирается в поле."""
    before = Party.objects.count()

    enter(entering, kab305, alpha, tenant_q="ТОО «Бета»", landlord_q="ТОО «Гамма»")

    assert Party.objects.count() == before
