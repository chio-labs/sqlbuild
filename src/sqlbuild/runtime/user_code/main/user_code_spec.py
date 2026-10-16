"""Module specs for project Python files that always load from current source."""

import sys
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_file_location
from pathlib import Path

from sqlbuild.runtime.user_code._helpers.finder import user_code_finder
from sqlbuild.runtime.user_code.classes.source_only_loader import SourceOnlyLoader


def register_user_code_root(root: Path) -> None:
    """Load every module later imported from under `root` from its current source."""

    user_code_finder.roots.add(root.resolve())
    if user_code_finder not in sys.meta_path:
        sys.meta_path.insert(0, user_code_finder)


def user_code_spec(
    name: str,
    file_path: Path,
    *,
    root: Path,
    submodule_search_locations: list[str] | None = None,
) -> ModuleSpec | None:
    """A spec loading `file_path` from source, with `root` registered for its own imports."""

    register_user_code_root(root)
    return spec_from_file_location(
        name,
        file_path,
        loader=SourceOnlyLoader(name, str(file_path)),
        submodule_search_locations=submodule_search_locations,
    )
