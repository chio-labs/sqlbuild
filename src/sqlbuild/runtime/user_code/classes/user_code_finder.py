"""A meta-path finder that loads modules under registered project roots from source."""

from collections.abc import Sequence
from importlib.machinery import ModuleSpec, PathFinder, SourceFileLoader
from pathlib import Path
from types import ModuleType

from sqlbuild.runtime.user_code.classes.source_only_loader import SourceOnlyLoader


class UserCodeFinder:
    """Find modules normally, switching source files under a project root to source-only loading."""

    def __init__(self) -> None:
        self.roots: set[Path] = set()

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        spec: ModuleSpec | None = PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.origin is None or not isinstance(spec.loader, SourceFileLoader):
            return None
        origin: Path = Path(spec.origin)
        if not any(origin.is_relative_to(root) for root in self.roots):
            return None
        spec.loader = SourceOnlyLoader(fullname, spec.origin)
        spec.cached = None
        return spec
