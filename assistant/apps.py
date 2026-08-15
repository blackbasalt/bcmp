from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """The AI manager. There are no models: the conversation lives in the session."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "assistant"
