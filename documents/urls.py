from django.urls import path

from . import views

app_name = "documents"
urlpatterns = [
    # The section stands at its own address rather than under a building: a document may
    # be linked to several BCs and may be linked to none. It is by the section's name that
    # the menu knows which item to highlight.
    path("", views.DocumentListView.as_view(), name="document_list"),
    # The document's own page: it names itself and needs no building in its address — a
    # document may be attached to several BCs and may be attached to none, so an address
    # through a building would have nowhere to put the устав.
    path("<uuid:pk>/", views.DocumentDetailView.as_view(), name="document_detail"),
    # Not an address for a human but the file itself: the document names itself, and what
    # kind of file it is the document knows. It carries no extension, because the extension
    # would be a second account of the format alongside the one the file's own bytes give.
    path("<uuid:pk>/file/", views.DocumentFileView.as_view(), name="document_file"),
]
