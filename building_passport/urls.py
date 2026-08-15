from django.urls import path

from . import views

app_name = "building_passport"
urlpatterns = [
    path("", views.BCListView.as_view(), name="bc_list"),
    path("bc/<uuid:pk>/", views.BCDetailView.as_view(), name="bc_detail"),
    # The address names both the building and the floor: it gets sent to a colleague,
    # and it shows where it leads.
    path("bc/<uuid:bc_pk>/floor/<uuid:pk>/", views.FloorView.as_view(), name="floor"),
    # Not an address for a human but the source of an image: the drawing names itself by
    # its extension, and which floor it belongs to is known to the plan itself.
    path("plan/<uuid:pk>.svg", views.FloorPlanSVGView.as_view(), name="floor_plan_svg"),
    # Also not a screen but the right-hand rail of the floor screen: a space names
    # itself, and needs no floor in its address — the tree is walked without leaving the
    # floor one is standing on.
    path("space/<uuid:pk>/card/", views.SpaceCardView.as_view(), name="space_card"),
]
