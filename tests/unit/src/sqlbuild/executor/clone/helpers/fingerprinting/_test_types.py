from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.executor.clone.types import CloneAction


@dataclass(frozen=True)
class CloneFingerprintPropagationTestCase:
    description: str
    cloned_actions: tuple[tuple[str, CloneAction], ...]
    expected_written_identities: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CloneFingerprintReadDedupTestCase:
    description: str
    model_names: tuple[str, ...]
    origin_schema: str
    expected_read_schemas: tuple[str, ...]
