from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DbtPlanProgressTestCase:
    description: str
    json_output: bool
    expected_stdout_fragments: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionWrapperTestCase:
    description: str
    command_name: str
    args: tuple[str, ...]
    expected_forwarded_args: tuple[str, ...]
    expected_progress_stream_name: str


@dataclass(frozen=True)
class DbtDebugWrapperTestCase:
    description: str
    args: tuple[str, ...]
    expected_dbt_args: tuple[str, ...]
    expected_sqlbuild_no_connection: bool
    expected_exit_code: int
    expected_stderr_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtAutoInitTestCase:
    description: str
    has_current_sqlbuild_project: bool
    has_sibling_sqlbuild_project: bool
    dbt_args: tuple[str, ...]
    expected_init_called: bool
    expected_forwarded_project_dir_name: str
    expected_request_dbt_project_dir_name: str | None
    expected_request_profiles_dir: str | None
    expected_request_target_name: str | None


@dataclass(frozen=True)
class DbtInitOutputTestCase:
    description: str
    dry_run: bool
    expected_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...] = ()
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtInitPromptTestCase:
    description: str
    explicit_git_ref: str | None
    input_text: str
    input_is_tty: bool
    expected_git_ref: str
    expected_output_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtInitProjectDirDefaultTestCase:
    description: str
    dbt_project_text: str
    expected_dbt_project_dir: str


@dataclass(frozen=True)
class DbtInitValidationOrderTestCase:
    description: str
    input_text: str
    expected_error_fragment: str
    unexpected_output_fragments: tuple[str, ...]
