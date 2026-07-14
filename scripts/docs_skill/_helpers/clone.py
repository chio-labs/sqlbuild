"""Docs repository cloning for skill generation."""

import shutil
import subprocess
from pathlib import Path


def clone_docs_repo(*, repo_url: str, clone_dir: Path) -> Path:
    """Clone the configured docs repository into a clean directory."""

    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
        check=True,
    )
    return clone_dir
