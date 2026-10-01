"""Public entry for the current-value note of a setting."""

from __future__ import annotations

from sqlbuild.errors.setting_help._helpers.text import setting_note as _setting_note
from sqlbuild.errors.setting_help.types import SettingValue


def setting_note(
    *, file_name: str, section: str, key: str, value: SettingValue, explicit: bool | None = True
) -> str:
    """Render a setting's current value; `explicit=None` when its provenance is unknown."""

    return _setting_note(
        file_name=file_name, section=section, key=key, value=value, explicit=explicit
    )
