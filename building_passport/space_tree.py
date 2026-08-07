"""Дерево помещений этажа, собранное из плоского набора пространств.

Собирается здесь, а не в шаблоне и не запросом на узел: помещения вложены на
произвольную глубину, а рекурсивный обход по `subspace` стоил бы по запросу на
каждое из 82 помещений. Представление отдаёт сюда уже отфильтрованный чокпоинтом
набор — одним запросом на здание, — и получает готовые узлы.

Порядок детей — порядок пришедшего набора: сортировка задаётся в запросе, чтобы
дерево не переупорядочивало то, что представление уже выстроило.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Space


@dataclass(frozen=True)
class Node:
    """Помещение и то, что под ним. Лист — узел с пустым `children`."""

    space: Space
    children: tuple["Node", ...]


def tree_under(floor: Space, spaces: Iterable[Space]) -> tuple[Node, ...]:
    """Помещения под этажом, вложенные так же, как связаны через `parent`.

    В набор попадает только то, что действительно лежит под этим этажом: чужой
    этаж, само здание и не доехавшая до набора ветка остаются снаружи. Пройденные
    узлы запоминаются — зациклённый `parent` не должен подвешивать экран.
    """
    children: dict[uuid.UUID, list[Space]] = {}
    for space in spaces:
        if space.parent_id is not None:
            children.setdefault(space.parent_id, []).append(space)

    visited: set[uuid.UUID] = set()

    def branch(parent: Space) -> tuple[Node, ...]:
        visited.add(parent.pk)
        return tuple(
            Node(space=child, children=branch(child))
            for child in children.get(parent.pk, ())
            if child.pk not in visited
        )

    return branch(floor)
