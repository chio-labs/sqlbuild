"""Load the dupscore TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import CloneAllowlistEntry, ContractExemptionEntry, DupscoreConfig

_ALLOWLIST_KEY: str = "allowlist"
_SURFACES_KEY: str = "persisted_state_surfaces"
_PAIR_KEY: str = "pair"
_REASON_KEY: str = "reason"
_PAIR_LENGTH: int = 2
_CLONE_ALLOWLIST_KEY: str = "clone_allowlist"
_PATHS_KEY: str = "paths"
_CLONE_ALLOWLIST_KEYS: frozenset[str] = frozenset({_PATHS_KEY, _REASON_KEY})
_CONTRACT_EXEMPTION_KEY: str = "contract_exemption"
_CONTRACT_KEY: str = "contract"
_FORBIDDEN_OWNERS_KEY: str = "forbidden_owners"
_CONTRACT_EXEMPTION_KEYS: frozenset[str] = frozenset(
    {_CONTRACT_KEY, _FORBIDDEN_OWNERS_KEY, _PATHS_KEY, _REASON_KEY}
)
_CLASS_SPEC_SEPARATOR: str = ":"
_CLASS_SPEC_PARTS: int = 2
_CLASS_SPEC_FORMAT: str = "'relative/path.py:ClassName'"
_PYTHON_SUFFIX: str = ".py"
_ABSOLUTE_PATH_PREFIX: str = "/"


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
        clone_allowlist=_load_clone_allowlist(raw.get(_CLONE_ALLOWLIST_KEY, [])),
        contract_exemptions=_load_contract_exemptions(raw.get(_CONTRACT_EXEMPTION_KEY, [])),
    )


def _load_clone_allowlist(raw: object) -> tuple[CloneAllowlistEntry, ...]:
    return tuple(
        CloneAllowlistEntry(
            paths=_glob_list(item=item, label=label), reason=_reason(item=item, label=label)
        )
        for label, item in _table_entries(
            raw=raw, key=_CLONE_ALLOWLIST_KEY, allowed=_CLONE_ALLOWLIST_KEYS
        )
    )


def _load_contract_exemptions(raw: object) -> tuple[ContractExemptionEntry, ...]:
    entries: list[ContractExemptionEntry] = []
    for label, item in _table_entries(
        raw=raw, key=_CONTRACT_EXEMPTION_KEY, allowed=_CONTRACT_EXEMPTION_KEYS
    ):
        contract_path, contract_class = _class_spec(
            raw=item.get(_CONTRACT_KEY), label=f"{label} {_CONTRACT_KEY}"
        )
        owners_raw: object = item.get(_FORBIDDEN_OWNERS_KEY, [])
        if not isinstance(owners_raw, list):
            raise DupscoreConfigError(
                f"{label} {_FORBIDDEN_OWNERS_KEY} must be a list of {_CLASS_SPEC_FORMAT} strings"
            )
        entries.append(
            ContractExemptionEntry(
                contract_path=contract_path,
                contract_class=contract_class,
                paths=_glob_list(item=item, label=label),
                reason=_reason(item=item, label=label),
                forbidden_owners=tuple(
                    _class_spec(raw=owner, label=f"{label} {_FORBIDDEN_OWNERS_KEY}")
                    for owner in owners_raw
                ),
            )
        )
    return tuple(entries)


def _table_entries(
    *, raw: object, key: str, allowed: frozenset[str]
) -> list[tuple[str, dict[str, object]]]:
    if not isinstance(raw, list):
        raise DupscoreConfigError(f"{key} must be an array of tables")
    entries: list[tuple[str, dict[str, object]]] = []
    for position, raw_item in enumerate(raw, start=1):
        label: str = f"{key} entry {position}"
        if not isinstance(raw_item, dict):
            raise DupscoreConfigError(f"{label} must be a table")
        item: dict[str, object] = {str(name): value for name, value in raw_item.items()}
        unknown: set[str] = set(item) - allowed
        if unknown:
            raise DupscoreConfigError(f"{label} has unknown keys: {', '.join(sorted(unknown))}")
        entries.append((label, item))
    return entries


def _glob_list(*, item: dict[str, object], label: str) -> tuple[str, ...]:
    paths_raw: object = item.get(_PATHS_KEY)
    if (
        not isinstance(paths_raw, list)
        or not paths_raw
        or not all(isinstance(path, str) and path.strip() for path in paths_raw)
    ):
        raise DupscoreConfigError(
            f"{label} needs a non-empty {_PATHS_KEY} list of non-empty glob strings"
        )
    return tuple(str(path) for path in paths_raw)


def _reason(*, item: dict[str, object], label: str) -> str:
    reason_raw: object = item.get(_REASON_KEY)
    if not isinstance(reason_raw, str) or not reason_raw.strip():
        raise DupscoreConfigError(f"{label} needs a non-empty {_REASON_KEY}")
    return reason_raw.strip()


def _class_spec(*, raw: object, label: str) -> tuple[str, str]:
    parts: list[str] = raw.split(_CLASS_SPEC_SEPARATOR) if isinstance(raw, str) else []
    if (
        len(parts) != _CLASS_SPEC_PARTS
        or not parts[0].endswith(_PYTHON_SUFFIX)
        or parts[0].startswith(_ABSOLUTE_PATH_PREFIX)
        or not parts[1].isidentifier()
    ):
        raise DupscoreConfigError(f"{label} must be {_CLASS_SPEC_FORMAT}")
    return parts[0], parts[1]
