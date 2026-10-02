"""Public entry for help that shows the exact setting to write."""

from __future__ import annotations

from sqlbuild.errors.setting_help._helpers.text import setting_help as _setting_help
from sqlbuild.errors.setting_help.types import SettingValue


def setting_help(
    *, purpose: str, file_name: str, section: str, key: str, value: SettingValue
) -> str:
    """Render `<purpose>, set this in <file>:` followed by the exact TOML section and key."""

    return _setting_help(
        purpose=purpose, file_name=file_name, section=section, key=key, value=value
    )
