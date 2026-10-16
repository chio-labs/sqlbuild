"""Register a project root whose modules always load from current source."""

import sys
from pathlib import Path

from sqlbuild.runtime.user_code._helpers.finder import user_code_finder


def register_user_code_root(root: Path) -> None:
    """Load every module later imported from under `root` from its current source."""

    user_code_finder.roots.add(root.resolve())
    if user_code_finder not in sys.meta_path:
        sys.meta_path.insert(0, user_code_finder)
