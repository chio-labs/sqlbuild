"""Project roots whose files log as project code rather than as installed libraries."""

from __future__ import annotations

import os
from pathlib import Path


def diagnostic_project_roots(*, project_dir: Path) -> tuple[str, ...]:
    """The project directory as given and resolved, whose files log as project code."""

    return tuple(dict.fromkeys((os.path.abspath(project_dir), str(project_dir.resolve()))))
