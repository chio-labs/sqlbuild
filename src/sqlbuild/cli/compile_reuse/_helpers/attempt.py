"""Decide whether a compile can replay the stored result, and replay it on a hit."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.compile_reuse._helpers.entry_file import (
    entry_render_state_path,
    read_entry_header,
    read_entry_stdout,
    rewrite_entry_inputs,
)
from sqlbuild.cli.compile_reuse._helpers.project_files import (
    carried_forward_digests,
    changed_project_paths,
    compare_project_files,
    needs_refresh,
    restamped_paths,
    snapshot_project_files,
    stored_project_files,
    with_missing_digests,
)
from sqlbuild.cli.compile_reuse._helpers.runtime_identity import (
    entry_slot_name,
    environment_digest,
    invocation_digest,
    module_stamps_unchanged,
    runtime_identity,
    search_path_stamps,
    settings_inputs_digest,
    tracked_environment_names,
)
from sqlbuild.cli.compile_reuse._helpers.target_files import target_files_unchanged
from sqlbuild.cli.compile_reuse._helpers.timings import (
    elapsed_ms,
    replace_compile_timings,
    reuse_timings,
)
from sqlbuild.cli.compile_reuse.constants import (
    MILLISECONDS_PER_SECOND,
    PROJECT_CONFIG_FILENAMES,
    REUSE_DISABLE_ENV_VAR,
    REUSE_DISABLE_VALUE,
    REUSE_ENTRY_DIRECTORY_PARTS,
    REUSE_ENTRY_SUFFIX,
    REUSE_HIT_MESSAGE,
    TOTAL_TIMING,
)
from sqlbuild.cli.compile_reuse.models import (
    CompileReuseAttempt,
    CompileReuseRequest,
    ProjectFilesComparison,
    StoredCompileHeader,
    StoredCompileInputs,
)
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.compiler.compile.constants import (
    COMPILE_CACHE_DISABLE_ENV_VAR,
    COMPILE_CACHE_DISABLE_VALUE,
)
from sqlbuild.presentation.main.supports_color import supports_color


def attempt_reuse(*, request: CompileReuseRequest) -> CompileReuseAttempt:
    """Replay a stored compile when every input matches, otherwise prepare to store one."""

    started: float = time.monotonic()
    project_dir: str = os.path.abspath(
        os.getcwd() if request.project_dir is None else request.project_dir
    )
    bypass: CompileReuseAttempt = CompileReuseAttempt(
        outcome=CompileReuseOutcome.BYPASS, project_dir=Path(project_dir), started=started
    )
    if _bypasses_reuse(request=request, project_dir=project_dir):
        return bypass
    snapshot_ns: int = time.time_ns()
    attempt: CompileReuseAttempt = replace(
        bypass,
        outcome=CompileReuseOutcome.MISS,
        entry_path=Path(project_dir, *REUSE_ENTRY_DIRECTORY_PARTS)
        / f"{entry_slot_name(selected_target=request.selected_target)}{REUSE_ENTRY_SUFFIX}",
        runtime=runtime_identity(),
        search_path=search_path_stamps(project_dir=project_dir),
        invocation_digest=invocation_digest(
            request=request,
            project_dir=project_dir,
            use_color=(not request.no_color) and supports_color(),
        ),
        snapshot=snapshot_project_files(project_dir=project_dir),
        snapshot_ns=snapshot_ns,
    )
    header: StoredCompileHeader | None = (
        None if attempt.entry_path is None else read_entry_header(path=attempt.entry_path)
    )
    if header is not None:
        attempt = _checked_attempt(attempt=attempt, inputs=header.inputs)
        if attempt.outcome is CompileReuseOutcome.HIT:
            return _replayed_attempt(
                attempt=attempt, header=header, json_output=request.json_output
            )
        attempt = replace(
            attempt,
            restamped=restamped_paths(stored=header.inputs.project_files, current=attempt.snapshot),
            render_state_path=(
                None
                if attempt.changed_paths is None or attempt.entry_path is None
                else entry_render_state_path(path=attempt.entry_path, header=header)
            ),
        )
    return replace(
        attempt,
        digests=with_missing_digests(
            project_dir=project_dir,
            snapshot=attempt.snapshot,
            digests=attempt.digests,
            paths=frozenset(),
            snapshot_ns=snapshot_ns,
        ),
        check_ms=elapsed_ms(started=started),
    )


def _bypasses_reuse(*, request: CompileReuseRequest, project_dir: str) -> bool:
    return (
        request.no_cache
        or request.manifest
        or request.profiling
        or request.debug
        or os.environ.get(COMPILE_CACHE_DISABLE_ENV_VAR) == COMPILE_CACHE_DISABLE_VALUE
        or os.environ.get(REUSE_DISABLE_ENV_VAR) == REUSE_DISABLE_VALUE
        or not any(
            os.path.isfile(os.path.join(project_dir, name)) for name in PROJECT_CONFIG_FILENAMES
        )
    )


def _checked_attempt(
    *, attempt: CompileReuseAttempt, inputs: StoredCompileInputs
) -> CompileReuseAttempt:
    project_dir: str = str(attempt.project_dir)
    identity_unchanged: bool = (
        inputs.invocation_digest == attempt.invocation_digest
        and inputs.runtime == attempt.runtime
        and inputs.search_path == attempt.search_path
        and tracked_environment_names(template_names=inputs.environment_names)
        == inputs.environment_names
        and environment_digest(names=inputs.environment_names) == inputs.environment_digest
        and settings_inputs_digest(inputs=inputs.settings_inputs) == inputs.settings_digest
        and module_stamps_unchanged(stamps=inputs.modules)
    )
    comparison: ProjectFilesComparison = (
        compare_project_files(
            project_dir=project_dir, stored=inputs.project_files, current=attempt.snapshot
        )
        if identity_unchanged
        else ProjectFilesComparison(unchanged=False, verified={})
    )
    unchanged: bool = comparison.unchanged and target_files_unchanged(
        stored=inputs.target_files, project_dir=project_dir, tree=inputs.target_tree
    )
    changed_paths: frozenset[str] | None = None
    verified: dict[str, str] = comparison.verified
    if identity_unchanged and not unchanged:
        changed_paths, verified = changed_project_paths(
            project_dir=project_dir,
            stored=inputs.project_files,
            current=attempt.snapshot,
            verified=comparison.verified,
        )
    return replace(
        attempt,
        outcome=CompileReuseOutcome.HIT if unchanged else CompileReuseOutcome.MISS,
        digests=carried_forward_digests(
            stored=inputs.project_files, current=attempt.snapshot, verified=verified
        ),
        changed_paths=changed_paths,
    )


def _replayed_attempt(
    *, attempt: CompileReuseAttempt, header: StoredCompileHeader, json_output: bool
) -> CompileReuseAttempt:
    stdout: str | None = (
        None
        if attempt.entry_path is None
        else read_entry_stdout(path=attempt.entry_path, header=header)
    )
    span: tuple[int, int] | None = header.output.timings_span
    if stdout is None or (json_output and span is None):
        return replace(attempt, outcome=CompileReuseOutcome.MISS)
    check_ms: int = elapsed_ms(started=attempt.started)
    if span is not None:
        stdout = replace_compile_timings(
            stdout=stdout,
            span=span,
            timings={
                **reuse_timings(outcome=CompileReuseOutcome.HIT, check_ms=check_ms),
                TOTAL_TIMING: elapsed_ms(started=attempt.started),
            },
        )
    print(REUSE_HIT_MESSAGE.format(seconds=check_ms / MILLISECONDS_PER_SECOND), file=sys.stderr)
    for line in header.output.stderr_lines:
        print(line, file=sys.stderr)
    _ = sys.stdout.write(stdout)
    sys.stdout.flush()
    if attempt.entry_path is not None and needs_refresh(
        stored=header.inputs.project_files, current=attempt.snapshot
    ):
        rewrite_entry_inputs(
            path=attempt.entry_path,
            header=header,
            inputs=replace(
                header.inputs,
                project_files=stored_project_files(
                    snapshot=attempt.snapshot,
                    digests=attempt.digests,
                    snapshot_ns=attempt.snapshot_ns,
                ),
            ),
        )
    return replace(attempt, check_ms=check_ms, exit_code=header.output.exit_code)
