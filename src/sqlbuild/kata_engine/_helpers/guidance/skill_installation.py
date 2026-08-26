"""Atomic generated-skill installation phases."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from stat import S_IMODE
from tempfile import NamedTemporaryFile

from sqlbuild.kata_engine._helpers.engine.native import native_skill_freshness
from sqlbuild.kata_engine.constants import REPLACEABLE_SKILL_STATES
from sqlbuild.kata_engine.exceptions import KataError


def install_rendered_skills(
    *, content: str, input_fingerprint: str, targets: tuple[Path, ...]
) -> None:
    """Validate and atomically replace all generated skill targets."""

    freshness: tuple[str, ...] = tuple(
        native_skill_freshness(
            content=path.read_text(encoding="utf-8") if path.is_file() else None,
            input_fingerprint=input_fingerprint,
        )
        for path in targets
    )
    for path, state in zip(targets, freshness, strict=True):
        if state not in REPLACEABLE_SKILL_STATES:
            raise KataError(f"refusing to overwrite {state} kata skill: {path}")
    staged: tuple[tuple[Path, Path | None, Path], ...] = _stage_skills(
        targets=targets, content=content
    )
    _ = _apply_staged_skills(staged=staged, installed_bytes=content.encode())


def _apply_staged_skills(
    *, staged: tuple[tuple[Path, Path | None, Path], ...], installed_bytes: bytes
) -> None:
    retained_backups: set[Path] = set()
    replaced: list[tuple[Path | None, Path]] = []
    try:
        for temporary, backup, target in staged:
            current: bytes | None = target.read_bytes() if target.is_file() else None
            expected: bytes | None = backup.read_bytes() if backup is not None else None
            if current != expected:
                raise KataError(
                    f"refusing to overwrite kata skill changed during installation: {target}"
                )
            temporary.replace(target)
            replaced.append((backup, target))
    except Exception as error:
        retained_backups = _rollback_replaced_skills(
            replaced=tuple(replaced),
            installed_bytes=installed_bytes,
            error=error,
        )
        raise
    finally:
        _remove_staged(staged=staged, retained_backups=retained_backups)


def _stage_skills(
    *, targets: tuple[Path, ...], content: str
) -> tuple[tuple[Path, Path | None, Path], ...]:
    staged: list[tuple[Path, Path | None, Path]] = []
    with ExitStack() as staging_cleanup:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target_mode: int = S_IMODE(target.stat().st_mode) if target.is_file() else 0o644
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary: Path = Path(temporary_file.name)
                staged.append((temporary, None, target))
                _ = staging_cleanup.callback(temporary.unlink, missing_ok=True)
                _ = temporary_file.write(content)
            temporary.chmod(target_mode)
            if target.is_file():
                with NamedTemporaryFile(
                    mode="wb",
                    dir=target.parent,
                    prefix=f".{target.name}.",
                    suffix=".bak",
                    delete=False,
                ) as backup_file:
                    backup: Path = Path(backup_file.name)
                    staged[-1] = (temporary, backup, target)
                    _ = staging_cleanup.callback(backup.unlink, missing_ok=True)
                    _ = backup_file.write(target.read_bytes())
                backup.chmod(target_mode)
        _ = staging_cleanup.pop_all()
    return tuple(staged)


def _rollback_replaced_skills(
    *,
    replaced: tuple[tuple[Path | None, Path], ...],
    installed_bytes: bytes,
    error: Exception,
) -> set[Path]:
    retained_backups: set[Path] = set()
    for backup, target in reversed(replaced):
        try:
            if not target.is_file() or target.read_bytes() != installed_bytes:
                if backup is not None:
                    retained_backups.add(backup)
                error.add_note(
                    f"rollback preserved concurrently changed target {target}; "
                    f"recovery backup: {backup}"
                )
            elif backup is None:
                target.unlink(missing_ok=True)
            else:
                backup.replace(target)
        except Exception as rollback_error:
            if backup is not None:
                retained_backups.add(backup)
            error.add_note(
                f"rollback failed for {target}: {rollback_error}; recovery backup: {backup}"
            )
    return retained_backups


def _remove_staged(
    *,
    staged: tuple[tuple[Path, Path | None, Path], ...],
    retained_backups: set[Path],
) -> None:
    for temporary, backup, _target in staged:
        temporary.unlink(missing_ok=True)
        if backup is not None and backup not in retained_backups:
            backup.unlink(missing_ok=True)
