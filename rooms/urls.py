from django.urls import path

from . import views

#: The namespace is also the раздел of the menu: the item is highlighted on every screen
#: whose `app_name` is this one (ADR 0016).
app_name = "rooms"
urlpatterns = [
    # The полка stands at its own address rather than under a building: it spans the whole
    # portfolio, and «где каб101» is asked by someone who does not know which БЦ it is in.
    path("", views.RoomListView.as_view(), name="room_list"),
]
