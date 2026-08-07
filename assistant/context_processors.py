"""Переписка в контексте каждого шаблона.

Панель стоит в общем макете, то есть на каждом экране, и при загрузке экрана должна
показывать то, что уже спрошено. Отдельным запросом за историей это стоило бы лишнего
обращения на каждой странице ради панели, которая по умолчанию закрыта.
"""

from .conversation import history


def conversation(request):
    """До входа панели на экране нет — и переписки в контексте тоже."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {"conversation": history(request.session)}
