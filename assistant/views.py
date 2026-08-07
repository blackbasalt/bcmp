from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .conversation import ask


@require_POST
def message(request):
    """Отправка сообщения в панель ИИ-управляющего.

    Обычное представление Django, а не эндпойнт DRF: что именно ИИ-управляющий будет
    спрашивать у системы, ещё не известно, и API пришлось бы проектировать дважды.
    Ответ — кусок разметки с перепиской, который HTMX подставляет на место прежней.
    """
    if not request.user.is_authenticated:
        return _sign_in_again(request)

    conversation = ask(request.session, request.POST.get("text", ""))
    return render(request, "assistant/_conversation.html", {"conversation": conversation})


def _sign_in_again(request):
    """Ответ на сообщение, отправленное без сессии.

    `login_required` здесь не годится: HTMX идёт за 302 прозрачно и вклеил бы форму
    входа внутрь панели вместо переписки. Поэтому ему отвечаем заголовком, по которому
    он уводит на вход целой страницей; обычному POST-у остаётся привычный редирект.

    Возврата на этот адрес нет: он принимает только POST, и после входа сотрудник
    попадает туда же, куда после обычного входа.
    """
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=401)
        response["HX-Redirect"] = settings.LOGIN_URL
        return response
    return redirect(settings.LOGIN_URL)
