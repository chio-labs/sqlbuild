"""Mutable virtual-build project capture for exception finalization."""

from sqlbuild.compiler.compile.models import CompiledProject


class VirtualBuildProjectCapture:
    """Capture the compiled project once the virtual plan establishes a run ID."""

    def __init__(self) -> None:
        self.project: CompiledProject | None = None

    def capture(self, project: CompiledProject) -> None:
        self.project = project
