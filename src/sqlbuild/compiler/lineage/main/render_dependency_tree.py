"""Public entry for rendering a box-drawing lineage dependency tree."""

from __future__ import annotations

from collections.abc import Callable, Hashable

from sqlbuild.compiler.lineage.helpers.tree_render import (
    SupportsSortKey,
    render_dependency_branch,
)


def render_dependency_tree[Node: Hashable](
    *,
    focus: Node,
    deps: dict[Node, list[Node]],
    seen: set[Node],
    format_node: Callable[[Node], str],
    sort_key: Callable[[Node], SupportsSortKey],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
) -> list[str]:
    """Render the box-drawing dependency tree lines for one focus node."""

    return render_dependency_branch(
        focus,
        deps=deps,
        prefix="",
        seen=seen,
        format_node=format_node,
        sort_key=sort_key,
        branch_style=branch_style,
        already_shown=already_shown,
    )
