from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView, View

from building_passport.models import Space
from parties.models import Org

from .batch_upload import DocumentBatchForm
from .document_display import (
    batch_report,
    document_deleted,
    documents_shown,
    twin_removed,
    twin_report,
)
from .document_edit import DocumentParticularsForm
from .document_page import Deletion, linked_buildings, particulars, taken_with
from .models import Document, DocumentTwin
from .twin_attach import DocumentTwinForm
from .uploaded_files import MARKDOWN_CONTENT_TYPE, content_type_for, head_of


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
            # Whether the ИИ-управляющий can read this документ, in the same query as the
            # rows: there are hundreds of them, and a близнец asked for row by row would be
            # a query per document. The subquery goes through no checkpoint of its own —
            # the близнец is another client's exactly when its документ is (ADR 0006).
            .annotate(has_twin=Exists(DocumentTwin.objects.filter(document=OuterRef("pk"))))
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


class DocumentDetailView(LoginRequiredMixin, DetailView):
    """A документ's own page — everything recorded about it, and the filling in of the rest.

    The other half of the bulk transfer: a batch lands with nothing but a название, and the
    реквизиты are entered here, one document at a time, as they are found. The form stands
    on the page and posts to that same address — the same arrangement as the batch upload
    on the section screen and the plan upload on the floor screen (ADR 0005): a refusal
    comes back onto the page the реквизиты are read from.
    """

    template_name = "documents/document_detail.html"
    context_object_name = "document"

    def get_queryset(self):
        """Another client's document answers 404, not 403 — the documents chokepoint (ADR 0006).

        The answer must not confirm that the document exists: telling "forbidden" from "no
        such thing" tells a reader what another client has on their shelf.
        """
        return Document.objects.visible_to(self.request.user).select_related(
            # The organisation and the issuing party are said by name, so they travel in
            # the same query as the document itself.
            "org__party",
            "issuer_party",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["particulars"] = particulars(self.object)
        # The привязки are resolved against the BCs this reader may see: a document and a
        # building answer to two different checkpoints, and the page asks both.
        context["links"] = linked_buildings(
            self.object, Space.objects.buildings_visible_to(self.request.user)
        )
        # The близнец, or nothing at all — and nothing is the ordinary state: BCMP stores
        # близнецы and does not make them (ADR 0007), so the page says which of the two it
        # is. A документ the ИИ-управляющий cannot read is identifiable only if it says so.
        context["twin"] = self.twin
        # The forms go only to whoever may write: an action an employee cannot perform is
        # not offered to them either. A rejection brings its own already filled-in form, so
        # the empty one is only put in its place.
        if not self.administers_the_document:
            context["edit"] = None
            context["attach"] = None
            # The deletion is not offered to a reader at all: the shelf is not editable by
            # them, and an action they would be refused is not named on their screen either.
            context["deletion"] = None
        else:
            context.setdefault("edit", DocumentParticularsForm(instance=self.object))
            context.setdefault("attach", DocumentTwinForm(document=self.object))
            context.setdefault("deletion", Deletion(confirming=False))
        return context

    def post(self, request, *args, **kwargs):
        """Five submissions at one address: the реквизиты, the близнец, taking it off, and
        the two steps of a deletion.

        One address because all of them stand on this page and are read off it: a refusal
        comes back onto the page it was sent from, with the document around it (ADR 0005).
        The близнец and the deletion name their submissions, and the реквизиты do not need
        to: they are the page's own form, and everything that does not name itself is them.
        """
        self.object = self.get_object()
        if not self.administers_the_document:
            # 403 and not 404, by the rule the section screen states in full: a document
            # this employee has already been shown does not become non-existent because
            # they may not write to it (ADR 0005).
            raise PermissionDenied("Вести данные документа может администратор организации.")
        submitted = request.POST.get("submitted")
        if submitted == "twin":
            return self.attach_twin(request)
        if submitted == "twin-removal":
            return self.remove_twin(request)
        if submitted == "deletion":
            return self.ask_about_deletion()
        if submitted == "deletion-confirmed":
            return self.delete_document(request)
        return self.fill_in_particulars(request)

    def fill_in_particulars(self, request):
        """Filling in the реквизиты — the other half of the bulk transfer.

        A refusal returns the same page with the reason on the form, and a save redirects
        back to it: the reloaded page is the confirmation, and what was entered is read
        where it was entered.
        """
        form = DocumentParticularsForm(request.POST, instance=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(edit=form))
        form.save()
        messages.success(request, "Реквизиты документа сохранены.")
        return redirect("documents:document_detail", self.object.pk)

    def attach_twin(self, request):
        """Attaching a близнец, or replacing the one that is there — one submission for both.

        What was attached is said in words, because the reloaded page shows only that there
        is a близнец: how many pictures came with it, and which of its references found
        none, are read nowhere else at that moment.
        """
        form = DocumentTwinForm(request.POST, request.FILES, document=self.object)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(attach=form))
        messages.add_message(request, *twin_report(form.save()))
        return redirect("documents:document_detail", self.object.pk)

    def remove_twin(self, request):
        """Taking a близнец off: a bad conversion is withdrawn, the документ stays as it was.

        A документ that has no близнец by now is not a failure: this submission is only sent
        from a page that showed the button, so the second click of a double is what reaches
        here, and it asks for a state the page is already in.
        """
        if self.twin is not None:
            self.twin.discard()
            messages.success(request, twin_removed())
        return redirect("documents:document_detail", self.object.pk)

    def ask_about_deletion(self):
        """The question, asked on the документ's own page and destroying nothing.

        Asked by the application and not by the browser. Everything else on this page is
        decided on the request rather than by what the screen offers, and a confirmation is
        no different: one that lived in a script would be gone the moment the script did not
        run, and the press behind it would delete a документ nobody was asked about.

        Two presses in two different places, and the second one is reached only through a
        reloaded page — which is what makes the misclick this exists for impossible, not the
        wording of the sentence between them.
        """
        return self.render_to_response(
            self.get_context_data(deletion=Deletion(confirming=True, taken=taken_with(self.object)))
        )

    def delete_document(self, request):
        """Destroy the документ, and with it everything that only existed as part of it.

        What went is worked out before the deleting and not after: the близнец and its
        картинки go with the документ, and afterwards the phrase would have nothing left to
        count.

        The reader lands on the shelf, because the page they deleted from is gone with the
        документ. A документ deleted twice — the second click of a double — finds nothing to
        delete and is answered by `get_object` the way everything missing is answered.
        """
        taken = taken_with(self.object)
        title = self.object.title
        self.object.discard()
        messages.success(request, document_deleted(title, taken))
        return redirect("documents:document_list")

    @cached_property
    def twin(self):
        """The документ's близнец, or `None`. Asked once per request: the page states whether
        there is one, and the removal takes the same one off."""
        return self.object.attached_twin()

    @cached_property
    def administers_the_document(self):
        """Whether this employee maintains the data of this document's organisation (ADR 0005).

        Narrower than the section's question and deliberately so: there the batch names the
        organisation it lands on, so "does this employee administer anything at all" is the
        most that can be asked before the form is filled in, while here the organisation is
        already named by the document. Asking the broader question on this page would offer
        an administrator of one client the form over another client's paper.
        """
        return Org.objects.administered_by(self.request.user).filter(pk=self.object.org_id).exists()


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


class DocumentTwinView(LoginRequiredMixin, View):
    """The близнец itself — what the ИИ-управляющий would be reading, so a человек can check.

    It comes out through the документ's own chokepoint and not through one of its own: the
    близнец is visible exactly where the документ is, and a second place deciding whose data
    to show would be a second place to one day disagree with the first (ADR 0006). Another
    client's близнец is therefore missing rather than forbidden, like their документ.
    """

    def get(self, request, pk):
        document = get_object_or_404(Document.objects.visible_to(request.user), pk=pk)
        twin = document.attached_twin()
        if twin is None or not twin.markdown:
            # Having no близнец is the ordinary state of a документ, and it is told the same
            # way as a документ that is not ours: what does not exist is missing.
            raise Http404("У документа нет близнеца.")
        response = FileResponse(
            twin.markdown.open("rb"),
            # Stated rather than read off the file: text begins with nothing in particular,
            # and the reading that accepted it — that it decodes as UTF-8 — is what this
            # says out loud.
            content_type=MARKDOWN_CONTENT_TYPE,
            as_attachment=True,
            # Under the документ's own name, like the original: the stored name is the file
            # the converter happened to produce, and a folder of «akt_K7x2p1.md» is a folder
            # nobody can navigate.
            filename=f"{document.title}.md",
        )
        # The близнец comes from whoever converted the документ and is served from our own
        # domain — the same treatment as the original file and the plan drawings.
        response["Content-Security-Policy"] = "sandbox"
        response["X-Content-Type-Options"] = "nosniff"
        return response
