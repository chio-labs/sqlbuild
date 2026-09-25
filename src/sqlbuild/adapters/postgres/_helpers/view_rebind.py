"""Re-create a dependent PostgreSQL view with its original options."""

from __future__ import annotations

import re

_CHECK_OPTION_KEY: str = "check_option"
_PLAIN_OPTION_VALUE: re.Pattern[str] = re.compile(r"[A-Za-z0-9_.]+")


def render_postgres_view_rebind(*, view: str, definition: str, reloptions: tuple[str, ...]) -> str:
    """Render CREATE OR REPLACE VIEW that keeps security and check options from reloptions."""

    options: list[str] = []
    check_option: str | None = None
    option: str
    for option in reloptions:
        key, _, value = option.partition("=")
        if key == _CHECK_OPTION_KEY:
            check_option = value.upper()
            continue
        options.append(f"{key}={_option_value(value)}")
    with_clause: str = f" WITH ({', '.join(options)})" if options else ""
    check_clause: str = f" WITH {check_option} CHECK OPTION" if check_option else ""
    body: str = definition.strip().rstrip(";").rstrip()
    return f"CREATE OR REPLACE VIEW {view}{with_clause} AS {body}{check_clause}"


def _option_value(value: str) -> str:
    if _PLAIN_OPTION_VALUE.fullmatch(value):
        return value
    return "'" + value.replace("'", "''") + "'"
