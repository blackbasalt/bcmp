from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views.generic import ListView, View

from parties.models import Org

from .batch_upload import DocumentBatchForm
from .document_display import batch_report, documents_shown
from .models import Document
from .uploaded_files import content_type_for, head_of


class DocumentListView(LoginRequiredMixin, ListView):
    """The "Документы" section — an organisation's whole shelf on one screen.

    The first screen in the project reached without opening a building: a document may be
    linked to several BCs and may be linked to none, and an entry through a building would
    hide the charter and the licence, which belong to no building at all.

    The batch upload form stands here and posts to this same address: files are brought in
    where they are read about, and a refusal comes back onto the screen that holds the
    shelf — the same arrangement as the plan upload on the floor screen (ADR 0005).
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
        # The form goes only to whoever may upload: an action an employee cannot perform is
        # not offered to them either. A rejection brings its own already filled-in form, so
        # the empty one is only put in its place.
        if not self.administers_anything:
            context["upload"] = None
        else:
            context.setdefault("upload", DocumentBatchForm(user=self.request.user))
        return context

    def post(self, request, *args, **kwargs):
        """Uploading a batch: the same address as the section — the form stands on it.

        A refusal returns the same screen with the reason on the form, and a batch that
        stored anything at all redirects back to it: the reloaded shelf is the
        confirmation, and what became of each file is said in words above it.
        """
        if not self.administers_anything:
            # 403, not 404: this employee can see the section, and answering "it does not
            # exist" would lie about what has already been shown. What gets hidden is other
            # clients' data, not one's own lack of rights (ADR 0005).
            raise PermissionDenied("Загружать документы организации может её администратор.")
        form = DocumentBatchForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            self.object_list = self.get_queryset()
            return self.render_to_response(self.get_context_data(upload=form))
        for level, said in batch_report(form.save()):
            messages.add_message(request, level, said)
        return redirect("documents:document_list")

    @cached_property
    def administers_anything(self):
        """Whether this employee maintains any organisation's data at all (ADR 0005).

        The same checkpoint is asked as on writing: the form that is shown and the request
        that is accepted must answer one question the same way, otherwise the screen offers
        what is later refused. Which organisation in particular is decided by the batch —
        by the building it names — and this is only about whether there is a form at all.
        """
        return Org.objects.administered_by(self.request.user).exists()

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


class DocumentFileView(LoginRequiredMixin, View):
    """The original file — the way the archive comes back out, through the same chokepoint.

    Serving it through nginx around the application would hand a client's scanned contract
    to anyone who guesses the address: `MEDIA_URL` is unset for exactly that reason, and
    there is no `/media/` location. So the file travels through `visible_to`, and another
    client's document answers 404 rather than 403 (ADR 0006).
    """

    def get(self, request, pk):
        document = get_object_or_404(Document.objects.visible_to(request.user), pk=pk)
        if not document.file_uri:
            # A document created in the admin may have no file at all. "There is no file"
            # is the truth about it, and it is told the same way as about a document that
            # is not ours: what does not exist is missing, not forbidden.
            raise Http404("У документа нет файла.")
        stream = document.file_uri.open("rb")
        # The type is read from the file itself by the same rule that accepted it, rather
        # than guessed from the name: with `nosniff` on the response, the type we state is
        # the only one the browser will use.
        response = FileResponse(
            stream,
            content_type=content_type_for(head_of(stream)),
            # The document is downloaded under the name it is read about on screen: the
            # stored file name may carry a suffix Django added to avoid a collision, and a
            # folder of «акт_K7x2p1.pdf» is a folder nobody can navigate.
            as_attachment=True,
            filename=f"{document.title}{Path(document.file_uri.name).suffix}",
        )
        # The file comes from whoever uploaded it and is served from the application's own
        # domain: opened by its address it would otherwise act as one of our pages. The
        # sandbox strips it of our origin, and `nosniff` of the chance to call itself
        # another type — the same treatment as the plan drawings.
        response["Content-Security-Policy"] = "sandbox"
        response["X-Content-Type-Options"] = "nosniff"
        return response
