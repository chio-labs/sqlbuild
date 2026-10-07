"""Read one stage capture from disk node by node instead of parsing it whole."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.compare import as_json_object, shared_digest
from scripts.compiler_differential._helpers.comparing.normalize import normalize_artifact_text
from sqlbuild.compiler.frontier.constants import (
    STAGE_CAPTURE_ROOT_KEY,
    STAGE_CAPTURE_SHARED_NODES_KEY,
)

_SHARED_HEADER: bytes = f"{{{json.dumps(STAGE_CAPTURE_SHARED_NODES_KEY)}: {{\n".encode()
_ROOT_PREFIX: bytes = f"{json.dumps(STAGE_CAPTURE_ROOT_KEY)}: ".encode()
_SHARED_DOCUMENT_KEYS: frozenset[str] = frozenset(
    {STAGE_CAPTURE_SHARED_NODES_KEY, STAGE_CAPTURE_ROOT_KEY}
)
_DIGEST_CHARACTERS: int = 64
_NODE_PREFIX_BYTES: int = _DIGEST_CHARACTERS + len(b'"": ')


class CaptureFile:
    """A normalized stage capture whose shared nodes are parsed only when resolved."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._offsets: dict[str, int] = {}
        self.root: object = self._index()

    def resolve(self, value: object) -> object:
        """Return the shared node a reference names, or the value itself."""

        digest: str | None = shared_digest(value)
        return value if digest is None else self._node(digest)

    def _index(self) -> object:
        with self._path.open("rb") as stream:
            if stream.readline() != _SHARED_HEADER:
                return _parse(self._path.read_bytes())
            root: object = None
            offset: int = stream.tell()
            for line in iter(stream.readline, b""):
                if line.startswith(_ROOT_PREFIX):
                    root = _parse(line[len(_ROOT_PREFIX) :])
                elif line.startswith(b'"') and len(line) > _NODE_PREFIX_BYTES:
                    self._offsets[line[1 : _DIGEST_CHARACTERS + 1].decode("ascii")] = offset
                offset += len(line)
            return root

    def _node(self, digest: str) -> object:
        offset: int | None = self._offsets.get(digest)
        if offset is None:
            raise json.JSONDecodeError(f"missing shared node {digest}", str(self._path), 0)
        with self._path.open("rb") as stream:
            _ = stream.seek(offset)
            line: bytes = stream.readline()
        return _parse(line[_NODE_PREFIX_BYTES:])


def expand_capture_text(text: str) -> object:
    """Parse a whole capture document, replacing every shared reference by its node."""

    document: object = json.loads(text)
    mapping: dict[str, object] | None = as_json_object(document)
    nodes: dict[str, object] | None = as_json_object(
        None if mapping is None else mapping.get(STAGE_CAPTURE_SHARED_NODES_KEY)
    )
    if mapping is None or nodes is None or set(mapping) != _SHARED_DOCUMENT_KEYS:
        return document
    expanded: dict[str, object] = {}
    for digest, node in nodes.items():
        expanded[digest] = _expanded(value=node, nodes=expanded)
    return _expanded(value=mapping[STAGE_CAPTURE_ROOT_KEY], nodes=expanded)


def _expanded(*, value: object, nodes: dict[str, object]) -> object:
    digest: str | None = shared_digest(value)
    if digest is not None:
        return nodes[digest]
    items: dict[str, object] | None = as_json_object(value)
    if items is not None:
        return {key: _expanded(value=item, nodes=nodes) for key, item in items.items()}
    if isinstance(value, list):
        return [_expanded(value=item, nodes=nodes) for item in value]
    return value


def _parse(data: bytes) -> object:
    text: str = data.decode("utf-8").rstrip("\n")
    return json.loads(normalize_artifact_text(text.removesuffix(",")))
