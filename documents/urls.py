from django.urls import path

from . import views

app_name = "documents"
urlpatterns = [
    # The section stands at its own address rather than under a building: a document may
    # be linked to several BCs and may be linked to none. It is by the section's name that
    # the menu knows which item to highlight.
    path("", views.DocumentListView.as_view(), name="document_list"),
]
