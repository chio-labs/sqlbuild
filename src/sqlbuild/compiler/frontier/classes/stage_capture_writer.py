"""Stream one stage capture so shared subtrees reach the file as they are encoded."""

from __future__ import annotations

import json
from typing import TextIO

from sqlbuild.compiler.frontier.constants import (
    STAGE_CAPTURE_ROOT_KEY,
    STAGE_CAPTURE_SHARED_NODES_KEY,
)


class StageCaptureWriter:
    """Write a capture as one JSON document with each shared node and the root on its own line."""

    def __init__(self, stream: TextIO) -> None:
        self._stream: TextIO = stream
        self._shared: bool = False

    def write_shared(self, *, digest: str, text: str) -> None:
        """Append one shared node, given as compact JSON."""

        prefix: str = (
            ",\n" if self._shared else f"{{{json.dumps(STAGE_CAPTURE_SHARED_NODES_KEY)}: {{\n"
        )
        self._shared = True
        _ = self._stream.write(f"{prefix}{json.dumps(digest)}: {text}")

    def finish(self, root: object) -> None:
        """Write the root and close the document."""

        if not self._shared:
            _ = self._stream.write(
                json.dumps(root, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
            )
            return
        compact: str = json.dumps(root, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        _ = self._stream.write(f"\n}},\n{json.dumps(STAGE_CAPTURE_ROOT_KEY)}: {compact}\n}}\n")
