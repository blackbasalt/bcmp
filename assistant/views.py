from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .conversation import ask


@require_POST
def message(request):
    """Sending a message to the AI manager panel.

    An ordinary Django view rather than a DRF endpoint: what exactly the AI manager will
    ask of the system is not yet known, and the API would have to be designed twice. The
    response is a chunk of markup with the conversation, which HTMX puts in place of the
    previous one.
    """
    if not request.user.is_authenticated:
        return _sign_in_again(request)

    conversation = ask(request.session, request.POST.get("text", ""))
    return render(request, "assistant/_conversation.html", {"conversation": conversation})


def _sign_in_again(request):
    """The reply to a message sent without a session.

    `login_required` does not fit here: HTMX follows a 302 transparently and would paste
    the sign-in form inside the panel instead of the conversation. So it is answered with
    a header that sends it to sign-in as a whole page; an ordinary POST keeps the usual
    redirect.

    There is no return to this address: it accepts POST only, and after signing in the
    employee lands where they land after an ordinary sign-in.
    """
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=401)
        response["HX-Redirect"] = settings.LOGIN_URL
        return response
    return redirect(settings.LOGIN_URL)
