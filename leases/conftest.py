"""What the аренда tests are staged on.

The организации, the employees, Manhattan and its first floor come from the root
`conftest`, and so do the Стороны and the factory for an аренда — the полка помещений asks
who sits where as well, and there must not be a second ТОО «Альфа» for it to ask about.
What stands here is only what the карточка needs: the помещения an аренда is staged on and
the two signed-in clients.

The помещения stand here rather than in one of the test modules because three of them ask
about the same two — the model, the block on the карточка and the form on it — and a
кабинет of 300 м² defined three times would drift into three different кабинеты. The two
signed-in clients stand here for the same reason: «сотрудник без права» and «администратор
организации» are the pair every screen of this stage is read through.
"""

import pytest


@pytest.fixture
def reader(client, member):
    """A сотрудник УК without the administrator right: the карточка is a screen, not a бланк."""
    client.force_login(member)
    return client


@pytest.fixture
def entering(client, administrator):
    """The администратор организации — the one every write is offered to (ADR 0005)."""
    client.force_login(administrator)
    return client


@pytest.fixture
def kab305(first_floor, make_space):
    """An арендопригодное помещение of a known площадь — the ordinary subject of an аренда."""
    return make_space(
        first_floor, "man-f1-c", "каб305", area_m2=300, is_leasable=True, is_common=False
    )


@pytest.fixture
def lobby(first_floor, make_space):
    """A МОП: not let as a whole, and still holding a банкомат of two metres."""
    return make_space(
        first_floor, "man-f1-d", "Лобби", area_m2=500, is_leasable=False, is_common=True
    )
