"""CLI dispatch error projection and post-dispatch maintenance."""

import logging
import sys
from pathlib import Path

from sqlbuild.cli.commands._helpers.entry.errors import format_expected_error
from sqlbuild.cli.commands._helpers.skills.update import maintain_sqlbuild_skills
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.exceptions import CliUserError
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
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.lint.exceptions import LintError
from sqlbuild.virtual.state.exceptions import StateBackendError


def dispatch_and_handle_errors(
    *,
    args: CliNamespace,
    invocation: ParsedCliInvocation,
    handlers: CliEntrypointHandlers,
    use_color: bool,
) -> int:
    """Dispatch once and preserve the CLI's established error projection."""

    try:
        return dispatch_with_observability(args=args, handlers=handlers)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    except (CliUserError, KataError) as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        print(
            format_expected_error(error=error, fallback_code="C000", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except LintError as error:
        logging.getLogger("sqlbuild.cli").exception("lint failed")
        print(
            format_expected_error(error=error, fallback_code="L001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except (DiscoveryError, StateBackendError, ValueError) as error:
        logging.getLogger("sqlbuild.cli").exception("command failed")
        print(
            format_expected_error(error=error, fallback_code="E001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    finally:
        _report_skill_freshness(invocation=invocation)


def _report_skill_freshness(*, invocation: ParsedCliInvocation) -> None:
    args: CliNamespace | None = invocation.args
    if args is None or args.command in {
        CliCommand.INIT,
        CliCommand.PLAYGROUND,
        CliCommand.SKILLS,
    }:
        return
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    try:
        result: SkillMaintenanceResult = maintain_sqlbuild_skills(project_dir=project_dir)
    except (CliUserError, OSError):
        return
    if result.message:
        print(result.message, file=sys.stderr, end="")
