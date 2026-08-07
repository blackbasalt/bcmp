"""Что лежит под этажом: дерево помещений и тот же набор плоским списком.

Собирается здесь, а не в шаблоне и не запросом на узел: помещения вложены на
произвольную глубину, а рекурсивный обход по `subspace` стоил бы по запросу на
каждое из 82 помещений. Вызывающий отдаёт сюда уже отфильтрованный чокпоинтом
набор — одним запросом на здание, — и получает готовые узлы.

Порядок детей — порядок пришедшего набора: сортировка задаётся в запросе, чтобы
дерево не переупорядочивало то, что вызывающий уже выстроил.

Моделей этот модуль не импортирует: наоборот, они импортируют его.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Space


@dataclass(frozen=True)
class Node:
    """Помещение и то, что под ним. Лист — узел с пустым `children`."""

    space: "Space"
    children: tuple["Node", ...]


def tree_under(floor: "Space", spaces: Iterable["Space"]) -> tuple[Node, ...]:
    """Помещения под этажом, вложенные так же, как связаны через `parent`.

    В набор попадает только то, что действительно лежит под этим этажом: чужой
    этаж, само здание и не доехавшая до набора ветка остаются снаружи. Пройденные
    узлы запоминаются — зациклённый `parent` не должен подвешивать экран.
    """
    children = _children_by_parent(spaces)
    visited: set[uuid.UUID] = set()

    def branch(parent: "Space") -> tuple[Node, ...]:
        visited.add(parent.pk)
        return tuple(
            Node(space=child, children=branch(child))
            for child in children.get(parent.pk, ())
            if child.pk not in visited
        )

    return branch(floor)


def spaces_under(floor: "Space", spaces: Iterable["Space"]) -> tuple["Space", ...]:
    """То же поддерево плоским списком: разбору плана нужны помещения, а не вложенность.

    Помещение любого типа и любой глубины — кабина внутри уборной не хуже кабинета —
    может нести контур, поэтому спуск идёт до листьев, а не до прямых детей этажа.
    """
    children = _children_by_parent(spaces)
    visited = {floor.pk}
    under: list[Space] = []
    queue = [floor]
    while queue:
        for child in children.get(queue.pop().pk, ()):
            if child.pk in visited:
                continue
            visited.add(child.pk)
            under.append(child)
            queue.append(child)
    return tuple(under)


def _children_by_parent(spaces: Iterable["Space"]) -> dict[uuid.UUID, list["Space"]]:
    children: dict[uuid.UUID, list[Space]] = {}
    for space in spaces:
        if space.parent_id is not None:
            children.setdefault(space.parent_id, []).append(space)
    return children
