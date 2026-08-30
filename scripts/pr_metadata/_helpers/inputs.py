"""Pull request metadata input resolution."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def load_event_metadata(path: Path) -> tuple[str, str, str]:
    """Load branch, title, and body from a GitHub pull request payload."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    pull_request: dict[str, Any] = payload.get("pull_request", payload)
    return (
        pull_request["head"]["ref"],
        pull_request["title"],
        pull_request.get("body") or "",
    )


def get_current_branch() -> str:
    """Return the current Git branch name."""
    return subprocess.run(
        ["git", "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
