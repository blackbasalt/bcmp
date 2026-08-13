from django.urls import path

from . import views

app_name = "documents"
urlpatterns = [
    # Раздел стоит своим адресом, а не под зданием: документ бывает привязан к
    # нескольким БЦ и бывает не привязан ни к одному. По имени раздела меню и
    # понимает, какой пункт подсветить.
    path("", views.DocumentListView.as_view(), name="document_list"),
]
