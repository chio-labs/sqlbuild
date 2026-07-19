"""Load the dupscore TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import DupscoreConfig

_ALLOWLIST_KEY: str = "allowlist"
_SURFACES_KEY: str = "persisted_state_surfaces"
_PAIR_KEY: str = "pair"
_REASON_KEY: str = "reason"
_PAIR_LENGTH: int = 2


def load_config(config_path: Path) -> DupscoreConfig:
    """Load and validate dupscore configuration from a TOML file."""

    if not config_path.is_file():
        return DupscoreConfig()
    raw: dict[str, object] = tomllib.loads(config_path.read_text(encoding="utf-8"))
    surfaces_raw: object = raw.get(_SURFACES_KEY, [])
    if not isinstance(surfaces_raw, list):
        raise DupscoreConfigError(f"{_SURFACES_KEY} must be a list of module prefixes")
    surfaces: list[str] = []
    for surface in surfaces_raw:
        if not isinstance(surface, str):
            raise DupscoreConfigError(f"{_SURFACES_KEY} entries must be strings")
        surfaces.append(surface)

    allowlist_raw: object = raw.get(_ALLOWLIST_KEY, [])
    if not isinstance(allowlist_raw, list):
        raise DupscoreConfigError(f"{_ALLOWLIST_KEY} must be an array of tables")
    allowlisted_pairs: dict[tuple[str, str], str] = {}
    for item in allowlist_raw:
        if not isinstance(item, dict):
            raise DupscoreConfigError(f"{_ALLOWLIST_KEY} entries must be tables")
        pair_raw: object = item.get(_PAIR_KEY)
        reason_raw: object = item.get(_REASON_KEY)
        if not isinstance(pair_raw, list) or len(pair_raw) != _PAIR_LENGTH:
            raise DupscoreConfigError(
                f"{_ALLOWLIST_KEY} entries need a two-element {_PAIR_KEY} list"
            )
        if not isinstance(reason_raw, str) or not reason_raw:
            raise DupscoreConfigError(f"{_ALLOWLIST_KEY} entries need a non-empty {_REASON_KEY}")
        left, right = str(pair_raw[0]), str(pair_raw[1])
        ordered: tuple[str, str] = (left, right) if left <= right else (right, left)
        allowlisted_pairs[ordered] = reason_raw
    return DupscoreConfig(
        persisted_state_surfaces=tuple(sorted(surfaces)),
        allowlisted_pairs=allowlisted_pairs,
    )
