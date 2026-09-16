from django.urls import path

from . import views

#: Пространство имён — оно же раздел меню: пункт подсвечен на каждом экране, чей `app_name`
#: этот (ADR 0016).
app_name = "contracts"
urlpatterns = [
    # Полка стоит на своём адресе, а не под зданием: расходный договор здания не называет
    # вовсе (ADR 0033), и вход через БЦ спрятал бы четыре вида из пяти.
    path("", views.ContractListView.as_view(), name="contract_list"),
]
