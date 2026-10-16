"""A meta-path finder that loads modules under registered project roots from source."""

import sys
import sysconfig
from collections.abc import Sequence
from importlib.machinery import ModuleSpec, PathFinder, SourceFileLoader
from pathlib import Path
from types import ModuleType

from sqlbuild.runtime.user_code.classes.source_only_loader import SourceOnlyLoader

_INSTALLED_PACKAGE_DIRECTORIES: frozenset[str] = frozenset({"site-packages", "dist-packages"})


class UserCodeFinder:
    """Find modules normally, switching source files under a project root to source-only loading."""

    def __init__(self) -> None:
        self.roots: set[Path] = set()
        self.installed: tuple[Path, ...] = tuple(
            Path(location).resolve()
            for location in {
                sys.prefix,
                sys.base_prefix,
                sys.exec_prefix,
                *sysconfig.get_paths().values(),
            }
        )

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
        if not any(origin.is_relative_to(root) for root in tuple(self.roots)):
            return None
        if _INSTALLED_PACKAGE_DIRECTORIES.intersection(origin.parts) or any(
            origin.is_relative_to(location) for location in self.installed
        ):
            return None
        spec.loader = SourceOnlyLoader(fullname, spec.origin)
        return spec
