import json
from pathlib import Path
from typing import Any


def read_ledger(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").strip())
