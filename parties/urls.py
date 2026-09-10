from django.urls import path

from . import views

#: The namespace is also the раздел of the menu: the item is highlighted on every screen
#: whose `app_name` is this one (ADR 0016). `parties` was already an app — it holds `Party`,
#: `Org`, `OrgMembership`, `PartyRecord` and the rest — and simply had no addresses; the
#: fourth раздел needs no fifth app.
app_name = "parties"
urlpatterns = [
    # The полка stands at its own address rather than under a building: a Сторона is dealt
    # with by the организация and not by one БЦ, and 637 of the 699 are поставщики tied to no
    # building at all.
    path("", views.PartyListView.as_view(), name="party_list"),
    # Экран одной учётной карточки. Организации в адресе нет — ровно как у документа в
    # адресе нет здания: адрес называет карточку, а чья она, карточка знает сама. Ключ в
    # нём — ключ карточки, а не Стороны: то, что экран показывает, висит на карточке, и
    # Сторона, которую знают два клиента одного читателя, дала бы один адрес с двумя
    # ответами (ADR 0020).
    path("<uuid:pk>/", views.PartyDetailView.as_view(), name="party_detail"),
]
