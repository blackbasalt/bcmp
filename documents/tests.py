"""Адреса раздела «Документы»: собственное пространство имён под `/documents/`.

Отдельное пространство имён нужно не для порядка в коде, а для меню: пункт
подсвечивается по разделу, в котором стоит читатель, и различить два раздела
можно только тем, что у них разные имена.
"""

from django.urls import reverse


def test_the_section_reverses_under_its_own_namespace():
    """Имя адреса и include проекта договорились — иначе шаблон падает на `url`."""
    assert reverse("documents:document_list") == "/documents/"
