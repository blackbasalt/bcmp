"""The conversation in the context of every template.

The panel sits in the shared layout, that is, on every screen, and when a screen loads
it must show what has already been asked. Fetching the history with a separate request
would cost an extra round trip on every page for the sake of a panel that is closed by
default.
"""

from .conversation import history


def conversation(request):
    """Before sign-in there is no panel on the screen — and no conversation in the context."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {"conversation": history(request.session)}
