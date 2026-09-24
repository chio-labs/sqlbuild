from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.cli.commands.models import (
    AuditInvocation,
    CheckInvocation,
    SeedInvocation,
    TestInvocation,
)


@dataclass(frozen=True)
class CommandInvocationTestCase:
    description: str
    resolve: Callable[..., AuditInvocation | CheckInvocation | SeedInvocation | TestInvocation]
    request_type: Callable[..., object]
    json_output: bool
    expected_invocation_type_name: str
    expected_stream_name: str
    expected_has_progress_reporters: bool
