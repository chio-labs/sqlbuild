"""Debug command output models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.commands._helpers.debug.types import DebugCheckStatus


@dataclass(frozen=True)
class DebugLine:
    label: str
    message: str
    status: DebugCheckStatus | None = None
    status_message: str | None = None


@dataclass(frozen=True)
class DebugResult:
    runtime: tuple[DebugLine, ...]
    configuration: tuple[DebugLine, ...]
    providers: tuple[DebugLine, ...]
    connection: tuple[DebugLine, ...]

    @property
    def success(self) -> bool:
        return all(line.status != DebugCheckStatus.ERROR for line in self.lines)

    @property
    def lines(self) -> tuple[DebugLine, ...]:
        return self.runtime + self.configuration + self.providers + self.connection
