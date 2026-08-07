from django.urls import path

from . import views

app_name = "building_passport"
urlpatterns = [
    path("", views.BCListView.as_view(), name="bc_list"),
    path("bc/<uuid:pk>/", views.BCDetailView.as_view(), name="bc_detail"),
    # Адрес называет и здание, и этаж: его посылают коллеге, и по нему видно, куда идут.
    path("bc/<uuid:bc_pk>/floor/<uuid:pk>/", views.FloorView.as_view(), name="floor"),
    # Не адрес для человека, а источник картинки: чертёж называет себя расширением,
    # а к какому этажу он относится — знает сам план.
    path("plan/<uuid:pk>.svg", views.FloorPlanSVGView.as_view(), name="floor_plan_svg"),
]
