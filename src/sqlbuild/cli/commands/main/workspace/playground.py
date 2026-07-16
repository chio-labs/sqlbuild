"""Create a local SQLBuild playground project."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.playground.completion_output import (
    render_playground_completion_text,
)
from sqlbuild.cli.commands._helpers.playground.scaffold import (
    resolve_playground_target,
    write_playground_project,
)
from sqlbuild.cli.commands.models import (
    PlaygroundCommandRequest,
    PlaygroundTarget,
)


def run_playground(request: PlaygroundCommandRequest) -> int:
    """Create a self-contained waffle shop playground project."""

    target: PlaygroundTarget = resolve_playground_target(request=request)
    write_playground_project(target=target)
    completion_text: str = render_playground_completion_text(request=request, target=target)
    print(completion_text, end="")
    return 0
