"""Stable microbatch history value types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope


class MicrobatchRecordType(StrEnum):
    PARTITION_COMPLETION = "partition_completion"
    REPLAY_REQUIREMENT = "replay_requirement"
    SYNTHETIC_COMPLETION = "synthetic_completion"


class MicrobatchRunType(StrEnum):
    NORMAL = "normal"
    BACKFILL = "backfill"
    REPLAY_ON_CHANGE = "replay_on_change"


class MicrobatchCompletionType(StrEnum):
    INITIAL = "initial"
    RECOVERY = "recovery"


class MicrobatchFingerprintStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class UnaccountedPartitionPolicy(StrEnum):
    SYNTHESIZE = "synthesize"
    RECOVER_EMPTY = "recover_empty"
    RECOVER_ALL = "recover_all"


class ReplayRequirementState(StrEnum):
    INCOMPLETE = "incomplete"
    VERIFIED_COMPLETE = "verified_complete"
    COMPLETE_WITH_UNKNOWN_FINGERPRINTS = "complete_with_unknown_fingerprints"
    SUPERSEDED = "superseded"


class MicrobatchEventStore(Protocol):
    """Mode-independent append/read contract used by the shared executor."""

    def write(self, event: MicrobatchEvent) -> None: ...

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]: ...

    def read_model_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]: ...
