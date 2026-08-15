from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.functional import cached_property
from django.views.generic import ListView

from parties.models import Org

from .document_display import documents_shown
from .models import Document


class DocumentListView(LoginRequiredMixin, ListView):
    """The "Документы" section — an organisation's whole shelf on one screen.

    The first screen in the project reached without opening a building: a document may be
    linked to several BCs and may be linked to none, and an entry through a building would
    hide the charter and the licence, which belong to no building at all.
    """

    template_name = "documents/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        """The data is taken through the documents chokepoint (ADR 0006); no filter is
        assembled here."""
        return (
            Document.objects.visible_to(self.request.user)
            # The organisation and the issuing party are said by name, so they travel in
            # the same query as the documents themselves.
            .select_related("org__party", "issuer_party")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documents = context["documents"]
        # The count is worked out over the same set that will go into the table: the
        # number beneath it and the rows within it must not diverge.
        context["shown"] = documents_shown(len(documents))
        # The organisation is named for whoever handles more than one client: for them
        # the shelf is shared, and "whose paper is this" is a question they ask of every
        # row. For an employee of a single client the column would repeat one name down
        # the whole table.
        #
        # This is asked about the reader, not about what is shown: a column depending on
        # the data would disappear exactly when the second client has no documents yet —
        # and that is precisely the case where the organisation does need naming.
        context["organisation_named"] = self.organisations_of_the_reader > 1
        return context

    @cached_property
    def organisations_of_the_reader(self):
        """How many clients the reader handles — a question about them, not about their
        documents.

        It disposes of no permissions and selects no rows: whose documents to show is
        decided by the single chokepoint (ADR 0006), while what is worked out here is
        whether they need labelling. A superuser reads on everyone's behalf, so all the
        organisations are theirs.
        """
        user = self.request.user
        if user.is_superuser:
            return Org.objects.count()
        return user.memberships.count()
