"""Prepare compile artifacts in the background and publish them only at the normal write phase."""

from __future__ import annotations

import logging
import shutil
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import Context, copy_context
from pathlib import Path
from types import TracebackType

from filelock import FileLock, Timeout

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.compile.target_writer import (
    plan_static_sql_tests,
    publish_static_compile_target,
    staged_artifact_files,
    static_sql_test_planning_diagnostics,
    write_static_compile_target,
)
from sqlbuild.cli.commands.exceptions import StagedArtifactsChangedError
from sqlbuild.cli.compile.models import PlannedStaticSqlTests
from sqlbuild.cli.output.models import WrittenTarget
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic

_MIN_PREPARED_ARTIFACT_MODELS: int = 128
_MAX_PREPARED_ARTIFACT_MODELS: int = 5000
_STAGING_PREFIX: str = ".sqlbuild-staging-"
_LOCK_SUFFIX: str = ".lock"
_OWNER_MARKER: str = ".owner"
_LOGGER: logging.Logger = logging.getLogger(__name__)
type _PreparedResult = tuple[WrittenTarget, frozenset[str]]


class PreparedCompileArtifacts:
    """Own one background preparation task, either staged artifacts or planned SQL tests only."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled: bool = enabled
        self._staging_dir: Path | None = None
        self._owner_lock: FileLock | None = None
        self._created_target_dir: Path | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._future: Future[_PreparedResult] | None = None
        self._planned_tests: Future[PlannedStaticSqlTests] | None = None
        self._planning_inputs: tuple[CompiledProject, BaseAdapter, Path] | None = None

    def __enter__(self) -> PreparedCompileArtifacts:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self._executor is not None:
                self._executor.shutdown(wait=True, cancel_futures=True)
        finally:
            if self._staging_dir is not None:
                shutil.rmtree(self._staging_dir, ignore_errors=True)
            if self._owner_lock is not None:
                _release_and_unlink(self._owner_lock)
            if self._created_target_dir is not None:
                _remove_if_empty(self._created_target_dir)

    def remove_abandoned_staging(self, *, target_dir: Path) -> None:
        """Delete staging directories whose owner lock this compile can hold for the removal."""

        if not self.enabled:
            return
        for directory in sorted(target_dir.glob(f"{_STAGING_PREFIX}*")):
            if directory.suffix == _LOCK_SUFFIX:
                continue
            if not _remove_abandoned_directory(directory):
                return

    def start(
        self,
        *,
        project: CompiledProject,
        adapter: BaseAdapter,
        target_dir: Path,
        stage_artifacts: bool,
    ) -> None:
        """Stage artifacts beside target_dir when worthwhile, otherwise plan SQL tests ahead."""

        if not self.enabled:
            return
        if (
            stage_artifacts
            and _stages_artifacts(project)
            and self._start_staging(project=project, adapter=adapter, target_dir=target_dir)
        ):
            return
        if project.sql_tests:
            self._start_test_planning(project=project, adapter=adapter, target_dir=target_dir)

    def _start_test_planning(
        self, *, project: CompiledProject, adapter: BaseAdapter, target_dir: Path
    ) -> None:
        """Plan SQL tests against the published target while the compile continues."""

        self._planning_inputs = (project, adapter, target_dir)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-tests")
        context: Context = copy_context()

        def plan() -> PlannedStaticSqlTests:
            return context.run(
                plan_static_sql_tests, target_dir=target_dir, adapter=adapter, project=project
            )

        self._planned_tests = self._executor.submit(plan)

    def _start_staging(
        self, *, project: CompiledProject, adapter: BaseAdapter, target_dir: Path
    ) -> bool:
        """Stage artifacts beside target_dir so publication can move them instead of copying."""

        staging_dir: Path = target_dir / f"{_STAGING_PREFIX}{uuid.uuid4().hex}"
        try:
            if not target_dir.is_dir():
                target_dir.mkdir(parents=True)
                self._created_target_dir = target_dir
            self._owner_lock = FileLock(_owner_lock_path(staging_dir))
            self._owner_lock.acquire()
            _create_staging_directory(staging_dir)
        except OSError:
            return False
        self._staging_dir = staging_dir
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-artifacts")
        context: Context = copy_context()

        def prepare() -> _PreparedResult:
            written: WrittenTarget = context.run(
                write_static_compile_target,
                target_dir=staging_dir,
                adapter=adapter,
                project=project,
            )
            return written, staged_artifact_files(target_dir=staging_dir)

        self._future = self._executor.submit(prepare)
        return True

    def publish(
        self, *, target_dir: Path, manifest: dict[str, object] | None
    ) -> WrittenTarget | None:
        if self._planned_tests is not None and self._planning_inputs is not None:
            project, adapter, _ = self._planning_inputs
            return write_static_compile_target(
                target_dir=target_dir,
                adapter=adapter,
                project=project,
                manifest=manifest,
                planned_tests=self._planned_tests.result,
            )
        if self._future is None or self._staging_dir is None:
            return None
        try:
            prepared, expected_files = self._future.result()
        except OSError:
            return None
        if not _owns_staging_directory(self._staging_dir):
            raise StagedArtifactsChangedError(
                f"staging directory '{self._staging_dir.name}' was removed or replaced before "
                "publication; no artifact was published",
                help="Rerun the compile; avoid deleting target/ while a compile is running.",
            )
        return publish_static_compile_target(
            prepared=prepared,
            target_dir=target_dir,
            manifest=manifest,
            expected_files=expected_files,
        )

    def planning_diagnostics(self) -> tuple[CompilerDiagnostic, ...] | None:
        """Return background SQL test planning diagnostics without publishing any artifact."""

        if self._planned_tests is not None and self._planning_inputs is not None:
            project, adapter, target_dir = self._planning_inputs
            return static_sql_test_planning_diagnostics(
                target_dir=target_dir,
                adapter=adapter,
                project=project,
                planned_tests=self._planned_tests.result,
            )
        if self._future is None:
            return None
        try:
            return self._future.result()[0].diagnostics
        except OSError:
            return None


def _stages_artifacts(project: CompiledProject) -> bool:
    """Staging pays off for uncached, mid-sized projects whose memory stays within budget."""

    return (
        project.compile_cache_dir is None
        and _MIN_PREPARED_ARTIFACT_MODELS <= len(project.models) <= _MAX_PREPARED_ARTIFACT_MODELS
    )


def _owner_lock_path(staging_dir: Path) -> Path:
    return staging_dir.with_name(f"{staging_dir.name}{_LOCK_SUFFIX}")


def _create_staging_directory(staging_dir: Path) -> None:
    staging_dir.mkdir()
    (staging_dir / _OWNER_MARKER).write_text(staging_dir.name, encoding="utf-8")


def _owns_staging_directory(staging_dir: Path) -> bool:
    try:
        return (staging_dir / _OWNER_MARKER).read_text(encoding="utf-8") == staging_dir.name
    except OSError:
        return False


def _remove_abandoned_directory(directory: Path) -> bool:
    """Remove one ownerless staging directory while holding its lock; False stops cleanup."""

    lock: FileLock = FileLock(_owner_lock_path(directory), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        return True
    except OSError as error:
        _LOGGER.warning("skipped abandoned staging cleanup in %s: %s", directory.parent, error)
        return False
    try:
        if directory.is_dir():
            shutil.rmtree(directory)
    except OSError as error:
        lock.release()
        _LOGGER.warning("stopped abandoned staging cleanup at %s: %s", directory, error)
        return False
    _release_and_unlink(lock)
    return True


def _release_and_unlink(lock: FileLock) -> None:
    try:
        Path(lock.lock_file).unlink(missing_ok=True)
    except OSError:
        pass
    lock.release()


def _remove_if_empty(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        pass
