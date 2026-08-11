from django.urls import path

from . import views

app_name = "leases"
urlpatterns = [
    # Договор не принадлежит ни одному БЦ, поэтому адрес не вложен в здание (ADR 0009):
    # вложенный говорил бы, что договор чей-то, а он называет помещения нескольких БЦ.
    path("", views.LeaseListView.as_view(), name="lease_list"),
    path("<uuid:pk>/", views.LeaseDetailView.as_view(), name="lease_detail"),
    # Удаление — свой адрес, потому что с карточки оно уводит в любом случае, и
    # только POST: договор не удаляют переходом по ссылке.
    path("<uuid:pk>/delete/", views.LeaseDeleteView.as_view(), name="lease_delete"),
]
