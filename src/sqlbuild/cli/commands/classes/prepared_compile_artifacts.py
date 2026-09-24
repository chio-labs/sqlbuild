"""Own staged cold compile artifacts and publish them only at the normal write phase."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import Context, copy_context
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.compile.target_writer import (
    publish_static_compile_target,
    write_static_compile_target,
)
from sqlbuild.cli.output.models import WrittenTarget
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic

_MIN_PREPARED_ARTIFACT_MODELS: int = 128
_MAX_PREPARED_ARTIFACT_MODELS: int = 5000


class PreparedCompileArtifacts:
    """Own one bounded preparation task and its disposable output directory."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled: bool = enabled
        self._directory: TemporaryDirectory[str] | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._future: Future[WrittenTarget] | None = None

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
            if self._directory is not None:
                self._directory.cleanup()

    def start(self, *, project: CompiledProject, adapter: BaseAdapter) -> None:
        if (
            not self.enabled
            or project.compile_cache_dir is not None
            or len(project.models) < _MIN_PREPARED_ARTIFACT_MODELS
            or len(project.models) > _MAX_PREPARED_ARTIFACT_MODELS
        ):
            return
        try:
            self._directory = TemporaryDirectory(prefix="sqlbuild-compile-")
        except OSError:
            return
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-artifacts")
        context: Context = copy_context()
        target_dir: Path = Path(self._directory.name)

        def prepare() -> WrittenTarget:
            return context.run(
                write_static_compile_target,
                target_dir=target_dir,
                adapter=adapter,
                project=project,
            )

        self._future = self._executor.submit(prepare)

    def publish(
        self, *, target_dir: Path, manifest: dict[str, object] | None
    ) -> WrittenTarget | None:
        if self._future is None:
            return None
        try:
            prepared: WrittenTarget = self._future.result()
        except OSError:
            return None
        return publish_static_compile_target(
            prepared=prepared, target_dir=target_dir, manifest=manifest
        )

    def planning_diagnostics(self) -> tuple[CompilerDiagnostic, ...] | None:
        """Return staged SQL test planning diagnostics without publishing any artifact."""

        if self._future is None:
            return None
        try:
            return self._future.result().diagnostics
        except OSError:
            return None
