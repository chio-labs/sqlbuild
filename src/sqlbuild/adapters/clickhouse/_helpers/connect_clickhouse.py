"""Open a ClickHouse client with SQLBuild's session settings, without loading the full adapter."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.clickhouse.classes.clickhouse_connection import _ClickHouseConnection
from sqlbuild.adapters.clickhouse.constants import (
    CONNECTION_OPTION_KEYS,
    DEFAULT_DATABASE,
    DEFAULT_HTTP_PORT,
    DEFAULT_HTTPS_PORT,
    DSN_OPTION,
    MINIMUM_SERVER_VERSION,
    SESSION_SETTINGS,
    SETTING_CONFLICT_CODE,
    TIMEOUT_OPTIONS,
    VERIFY_OPTION,
)


def connect_clickhouse(config: dict[str, Any]) -> _ClickHouseConnection:
    """A connection for `config`: validated options, required session settings, supported server."""

    try:
        import clickhouse_connect
    except ImportError as error:
        raise AdapterUserError(
            message="ClickHouse adapter requires optional dependency clickhouse-connect. "
            "Install with: pip install 'sqlbuild[clickhouse]'",
            code="A701",
        ) from error
    unknown: tuple[str, ...] = tuple(sorted(set(config) - CONNECTION_OPTION_KEYS))
    if unknown:
        raise AdapterUserError(
            message=f"ClickHouse connection has unsupported options: {', '.join(unknown)}",
            code="A702",
            help="Supported options: " + ", ".join(sorted(CONNECTION_OPTION_KEYS)),
        )
    secure: bool = bool(config.get("secure", False))
    settings: dict[str, object] = _session_settings(dict(config.get("settings") or {}))
    client_options: dict[str, Any] = {
        "host": str(config.get("host", "localhost")),
        "port": int(config.get("port", DEFAULT_HTTPS_PORT if secure else DEFAULT_HTTP_PORT)),
        "username": str(config.get("username", config.get("user", "default"))),
        "password": str(config.get("password", "")),
        "database": str(config.get("database", DEFAULT_DATABASE)),
        "secure": secure,
        "settings": settings,
        "autogenerate_session_id": False,
    }
    if VERIFY_OPTION in config:
        client_options[VERIFY_OPTION] = bool(config[VERIFY_OPTION])
    if DSN_OPTION in config:
        client_options[DSN_OPTION] = str(config[DSN_OPTION])
    for timeout_key in TIMEOUT_OPTIONS:
        if timeout_key in config:
            client_options[timeout_key] = int(config[timeout_key])

    def create_client() -> Any:
        return clickhouse_connect.get_client(**client_options)

    client: Any = create_client()
    version: str = str(client.server_version)
    if _version_tuple(version) < MINIMUM_SERVER_VERSION:
        client.close()
        minimum: str = ".".join(str(part) for part in MINIMUM_SERVER_VERSION)
        raise AdapterUserError(
            message=f"ClickHouse server {version} is older than the supported {minimum}",
            code="A703",
            help=f"Upgrade the server to ClickHouse {minimum} or newer.",
        )
    return _ClickHouseConnection(client=client, interrupt_client_factory=create_client)


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split(".")[:2]:
        digits: str = "".join(character for character in part if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _session_settings(user_settings: dict[str, object]) -> dict[str, object]:
    """Merge user settings under the required ones, refusing a user value that differs."""

    conflicts: tuple[str, ...] = tuple(
        sorted(
            name
            for name, value in user_settings.items()
            if name in SESSION_SETTINGS
            and _setting_text(value) != _setting_text(SESSION_SETTINGS[name])
        )
    )
    if conflicts:
        required: str = ", ".join(f"{name} = {SESSION_SETTINGS[name]!r}" for name in conflicts)
        raise AdapterUserError(
            message=(
                "ClickHouse connection settings override settings SQLBuild requires: "
                + ", ".join(conflicts)
            ),
            code=SETTING_CONFLICT_CODE,
            help=f"Remove them from [connection.settings]; SQLBuild runs with {required}.",
        )
    return {**user_settings, **SESSION_SETTINGS}


def _setting_text(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip().lower()
