from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """ИИ-управляющий. Моделей нет: переписка живёт в сессии."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "assistant"
