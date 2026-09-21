"""Public compile command entrypoint."""

from sqlbuild.cli.commands.main.project._compile import run_compile as _run_compile
from sqlbuild.cli.compile.models import CompileCommandRequest


def run_compile(request: CompileCommandRequest) -> int:
    """Run one compile command request."""

    return _run_compile(request)
