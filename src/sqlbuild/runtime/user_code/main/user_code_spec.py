"""Module specs for project Python files that always load from current source."""

from importlib.machinery import ModuleSpec
from importlib.util import spec_from_file_location
from pathlib import Path

from sqlbuild.runtime.user_code.classes.source_only_loader import SourceOnlyLoader
from sqlbuild.runtime.user_code.main.register_user_code_root import register_user_code_root


def user_code_spec(
    *,
    name: str,
    file_path: Path,
    root: Path,
    submodule_search_locations: list[str] | None = None,
) -> ModuleSpec | None:
    """A spec loading `file_path` from source, with `root` registered for its own imports."""

    _ = register_user_code_root(root)
    return spec_from_file_location(
        name,
        file_path,
        loader=SourceOnlyLoader(name, str(file_path)),
        submodule_search_locations=submodule_search_locations,
    )
