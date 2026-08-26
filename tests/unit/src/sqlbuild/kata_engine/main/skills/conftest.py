"""Process and failure orchestration for kata skill installation tests."""

from collections.abc import Callable
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlbuild.kata_engine._helpers.guidance import skill_installation
from sqlbuild.kata_engine.main import skills as skills_module
from sqlbuild.kata_engine.models import KataConfig


class FailingReplacement:
    def __init__(self, *, original_replace: Callable[..., Path]) -> None:
        self._original_replace = original_replace
        self._temporary_replacements = 0

    def __call__(self, path: Path, target: Path) -> Path:
        if path.suffix == ".tmp":
            self._temporary_replacements += 1
            if self._temporary_replacements == 2:
                raise OSError("replacement failed")
        if path.suffix == ".bak":
            raise OSError("rollback failed")
        return self._original_replace(path, target)


class ReplacementFailure:
    def __init__(self, *, original_replace: Callable[..., Path]) -> None:
        self._original_replace = original_replace
        self._temporary_replacements = 0

    def __call__(self, path: Path, target: Path) -> Path:
        if path.suffix == ".tmp":
            self._temporary_replacements += 1
            if self._temporary_replacements == 2:
                raise OSError("replacement failed")
        return self._original_replace(path, target)


class CoordinatedReplacementFailure:
    def __init__(
        self,
        *,
        original_replace: Callable[..., Path],
        failure_reached: Event,
        other_writer_attempting: Event,
    ) -> None:
        self._original_replace = original_replace
        self._failure_reached = failure_reached
        self._other_writer_attempting = other_writer_attempting
        self._temporary_replacements = 0

    def __call__(self, path: Path, target: Path) -> Path:
        if path.suffix == ".tmp":
            self._temporary_replacements += 1
            if self._temporary_replacements == 2:
                self._failure_reached.set()
                if not self._other_writer_attempting.wait(timeout=20):
                    raise TimeoutError("timed out waiting for the other skill writer")
                raise OSError("replacement failed")
        return self._original_replace(path, target)


class EditAfterBackupRead:
    def __init__(self, *, original_read: Callable[..., bytes], target: Path) -> None:
        self._original_read = original_read
        self._target = target
        self._edited = False

    def __call__(self, path: Path) -> bytes:
        content: bytes = self._original_read(path)
        if path == self._target and not self._edited:
            self._edited = True
            path.write_text("concurrent local edit\n", encoding="utf-8")
        return content


def install_skills_in_process(
    *,
    root: str,
    selected_rule: str,
    result_queue: Queue[Any],
    attempting: Event,
    staged: Event | None = None,
    release: Event | None = None,
) -> None:
    original_stage: Callable[..., tuple[tuple[Path, Path | None, Path], ...]] = (
        skill_installation._stage_skills
    )

    def wait_and_stage(
        *, targets: tuple[Path, ...], content: str
    ) -> tuple[tuple[Path, Path | None, Path], ...]:
        if staged is not None:
            staged.set()
        if release is not None and not release.wait(timeout=20):
            raise TimeoutError("timed out waiting to release staged skill installation")
        return original_stage(targets=targets, content=content)

    attempting.set()
    try:
        with patch.object(skill_installation, "_stage_skills", side_effect=wait_and_stage):
            _ = skills_module.install_skills(
                config=KataConfig(select=(selected_rule,)),
                project_dir=Path(root),
                check=False,
            )
    except Exception as error:
        result_queue.put((selected_rule, type(error).__name__, str(error)))
    else:
        result_queue.put((selected_rule, "ok", ""))


def install_failing_skills_in_process(
    *,
    root: str,
    selected_rule: str,
    result_queue: Queue[Any],
    failure_reached: Event,
    other_writer_attempting: Event,
) -> None:
    replacement: CoordinatedReplacementFailure = CoordinatedReplacementFailure(
        original_replace=Path.replace,
        failure_reached=failure_reached,
        other_writer_attempting=other_writer_attempting,
    )
    try:
        with patch.object(Path, "replace", autospec=True, side_effect=replacement):
            _ = skills_module.install_skills(
                config=KataConfig(select=(selected_rule,)),
                project_dir=Path(root),
                check=False,
            )
    except Exception as error:
        result_queue.put((selected_rule, type(error).__name__, str(error)))
    else:
        result_queue.put((selected_rule, "ok", ""))
