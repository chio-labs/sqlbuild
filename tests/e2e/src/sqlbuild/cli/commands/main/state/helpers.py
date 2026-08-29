from __future__ import annotations

import subprocess


def assert_state_cli_error(
    *,
    result: subprocess.CompletedProcess[str],
    expected_exit_code: int,
    expected_error_fragment: str,
) -> None:
    assert result.returncode == expected_exit_code
    assert "error[E001]" in result.stderr
    assert expected_error_fragment in result.stderr
    assert "Traceback" not in result.stderr


def build_postgres_state_project_toml(
    *,
    project_name: str,
    config: dict[str, object],
    state_schema: str,
    allow_reset: bool = False,
    state_config: dict[str, object] | None = None,
) -> str:
    allow_reset_value: str = str(allow_reset).lower()
    effective_state_config: dict[str, object] = state_config or config
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n"
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        'schema = "preserve"\n\n'
        "[targets.dev.state]\n"
        'backend = "postgres"\n'
        f'schema = "{state_schema}"\n'
        f"allow_reset = {allow_reset_value}\n\n"
        "[targets.dev.state.connection]\n"
        f'host = "{effective_state_config["host"]}"\n'
        f"port = {effective_state_config['port']}\n"
        f'dbname = "{effective_state_config["dbname"]}"\n'
        f'user = "{effective_state_config["user"]}"\n'
        f'password = "{effective_state_config["password"]}"\n'
    )


def build_postgres_local_state_connection_toml(*, config: dict[str, object]) -> str:
    return (
        "[targets.dev.state.connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n'
    )
