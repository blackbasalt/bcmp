"""What lies under a floor: the tree of spaces and the same set as a flat list.

It is assembled here rather than in a template or by a query per node: spaces nest to an
arbitrary depth, and walking `subspace` recursively would cost a query for each of the
82 spaces. The caller hands in a set already filtered by the checkpoint — in one query
per building — and gets back ready nodes.

The order of the children is the order of the incoming set: sorting is specified in the
query so that the tree does not rearrange what the caller has already ordered.

This module imports no models: on the contrary, they import it.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Space


@dataclass(frozen=True)
class Node:
    """A space and what lies under it. A leaf is a node with an empty `children`."""

    space: "Space"
    children: tuple["Node", ...]


def tree_under(floor: "Space", spaces: Iterable["Space"]) -> tuple[Node, ...]:
    """The spaces under a floor, nested the way they are linked through `parent`.

    Only what really lies under this floor gets into the set: another floor, the
    building itself and a branch that never reached the set stay outside. Visited nodes
    are remembered — a looping `parent` must not hang the screen.
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
    """The same subtree as a flat list: parsing a plan needs the spaces, not the nesting.

    A space of any type and at any depth — a cubicle inside a toilet no less than an
    office — may carry a contour, so the descent goes down to the leaves rather than to
    the direct children of the floor.
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
