"""CLI dispatch error projection and post-dispatch maintenance."""

import logging
import sys
from pathlib import Path

from sqlbuild.cli.commands._helpers.entry.errors import format_expected_error
from sqlbuild.cli.commands._helpers.skills.update import maintain_sqlbuild_skills
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.exceptions import CliUserError, QueryDiffExecutionError
from sqlbuild.cli.commands.main.entrypoint._dispatch_with_observability import (
    dispatch_with_observability,
)
from sqlbuild.cli.commands.models import (
    CliEntrypointHandlers,
    ParsedCliInvocation,
    SkillMaintenanceResult,
)
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.executor.pipeline.exceptions import AuditExecutionError
from sqlbuild.lint.exceptions import LintError
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.runtime.execution_limits.exceptions import ExecutionDurationLimitError
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.virtual.state.exceptions import StateBackendError


def dispatch_and_handle_errors(
    *,
    args: CliNamespace,
    invocation: ParsedCliInvocation,
    handlers: CliEntrypointHandlers,
    use_color: bool,
) -> int:
    """Dispatch once and preserve the CLI's established error projection."""

    _report_skill_freshness(invocation=invocation)
    try:
        return dispatch_with_observability(args=args, handlers=handlers)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    except (CliUserError, RulesError) as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        effective_error: CliUserError | RulesError = error
        if isinstance(error, CliUserError):
            output_error: QueryDiffExecutionError | None = _write_diff_machine_error(
                args=args, error=error
            )
            if output_error is not None:
                effective_error = output_error
        outcome_status: object | None = getattr(effective_error, "status", None)
        if outcome_status is not None:
            print(f"Query diff outcome  {outcome_status}", file=sys.stderr)
        print(
            format_expected_error(error=effective_error, fallback_code="C000", use_color=use_color),
            file=sys.stderr,
        )
        if isinstance(effective_error, CliUserError):
            return int(getattr(effective_error, "exit_code", 1))
        return 1
    except LintError as error:
        logging.getLogger("sqlbuild.cli").exception("lint failed")
        print(
            format_expected_error(error=error, fallback_code="L001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except (
        AuditExecutionError,
        DiscoveryError,
        ExecutionDurationLimitError,
        SpecConfigError,
        StateBackendError,
        ValueError,
    ) as error:
        logging.getLogger("sqlbuild.cli").exception("command failed")
        print(
            format_expected_error(error=error, fallback_code="E001", use_color=use_color),
            file=sys.stderr,
        )
        return 1


def _report_skill_freshness(*, invocation: ParsedCliInvocation) -> None:
    args: CliNamespace | None = invocation.args
    if args is None or args.command in {
        CliCommand.INIT,
        CliCommand.PLAYGROUND,
        CliCommand.SKILLS,
    }:
        return
    if args.command == CliCommand.DIFF and any(
        value is not None
        for value in (
            args.left_query,
            args.left_query_file,
            args.right_query,
            args.right_query_file,
        )
    ):
        return
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    try:
        result: SkillMaintenanceResult = maintain_sqlbuild_skills(project_dir=project_dir)
    except (CliUserError, OSError, UnicodeError):
        return
    if result.message:
        print(result.message, file=sys.stderr, end="")


def _write_diff_machine_error(
    *, args: CliNamespace, error: CliUserError
) -> QueryDiffExecutionError | None:
    if args.command != CliCommand.DIFF:
        return None
    json_stdout: bool = bool(getattr(args, "json", False))
    json_path: Path | None = getattr(args, "json_output", None)
    if not json_stdout and json_path is None:
        return None
    from sqlbuild.cli.commands._helpers.diff.json_output import render_diff_error_json

    payload: str = render_diff_error_json(
        status=str(getattr(error, "status", "execution_failed")),
        code=error.code,
        message=error.message,
    )
    if json_path is not None:
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(payload + "\n", encoding="utf-8")
        except (OSError, UnicodeError) as output_error:
            publication_error: QueryDiffExecutionError = QueryDiffExecutionError(
                f"failed to publish query diff output: {output_error}", code="C257"
            )
            if json_stdout:
                print(
                    render_diff_error_json(
                        status=publication_error.status,
                        code=publication_error.code,
                        message=publication_error.message,
                    )
                )
            return publication_error
    if json_stdout:
        print(payload)
    return None
