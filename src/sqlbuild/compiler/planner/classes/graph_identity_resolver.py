"""Memoized graph identity resolution over one dependency graph."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphIdentityComposer

type _Resolve = Callable[[GraphNodeKey], str | None]


class GraphIdentityResolver:
    """Resolve expected or selected-write identity hashes, each node once, in linear time."""

    def __init__(
        self,
        *,
        nodes: Mapping[GraphNodeKey, GraphIdentityNode],
        compose_identity: GraphIdentityComposer,
        base_hashes: Mapping[GraphNodeKey, str | None],
        selected_keys: frozenset[GraphNodeKey] | None,
    ) -> None:
        self._nodes: Mapping[GraphNodeKey, GraphIdentityNode] = nodes
        self._compose_identity: GraphIdentityComposer = compose_identity
        self._selected_keys: frozenset[GraphNodeKey] | None = selected_keys
        self._hashes: dict[GraphNodeKey, str | None] = dict(base_hashes)
        self._resolved_selected: dict[GraphNodeKey, str] = {}
        self._visiting: set[GraphNodeKey] = set()

    @property
    def hashes(self) -> dict[GraphNodeKey, str | None]:
        """Return every hash recorded so far, in first-recorded order."""

        return self._hashes

    def resolve_expected(self, key: GraphNodeKey) -> str | None:
        """Compose a node's expected hash from its upstream expected hashes."""

        if key in self._hashes:
            return self._hashes[key]
        node: GraphIdentityNode | None = self._nodes.get(key)
        if node is None or node.local_hash is None:
            self._hashes[key] = None
            return None
        if key in self._visiting:
            self._hashes[key] = node.local_hash
            return node.local_hash
        composed: str = self._compose(
            key=key, local_hash=node.local_hash, node=node, resolve=self.resolve_expected
        )
        self._hashes[key] = composed
        return composed

    def resolve_write(self, key: GraphNodeKey) -> str | None:
        """Recompute a selected node's hash from upstream write hashes; others keep theirs."""

        if self._selected_keys is None or key not in self._selected_keys:
            return self._hashes.get(key)
        if key in self._resolved_selected:
            return self._resolved_selected[key]
        node: GraphIdentityNode | None = self._nodes.get(key)
        if node is None or node.local_hash is None:
            return self._hashes.get(key)
        if key in self._visiting:
            return node.local_hash
        composed: str = self._compose(
            key=key, local_hash=node.local_hash, node=node, resolve=self.resolve_write
        )
        self._hashes[key] = composed
        self._resolved_selected[key] = composed
        return composed

    def _compose(
        self, *, key: GraphNodeKey, local_hash: str, node: GraphIdentityNode, resolve: _Resolve
    ) -> str:
        self._visiting.add(key)
        upstream_hashes: list[tuple[GraphNodeKey, str]] = []
        upstream_key: GraphNodeKey
        for upstream_key in node.upstream_keys:
            upstream_hash: str | None = resolve(upstream_key)
            if upstream_hash is not None:
                upstream_hashes.append((upstream_key, upstream_hash))
        self._visiting.discard(key)
        return self._compose_identity(local_hash=local_hash, upstream_hashes=tuple(upstream_hashes))
