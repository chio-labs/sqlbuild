"""Runtime hermeticity audit hook for the custom-rule host."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import CodeType, FrameType

from sqlbuild.rule_engine._helpers.engine.hermeticity import allowed_custom_rule_import
from sqlbuild.rule_engine.classes.project_tree import ProjectTree
from sqlbuild.rule_engine.exceptions import NonHermeticRuleError

_IMPORT_EVENT: str = "import"
_OPEN_EVENT: str = "open"
_IMPORT_ENTRY_FUNCTION: str = "_find_and_load"
_FROZEN_IMPORT_PREFIX: str = "<frozen importlib."
_FILESYSTEM_EVENTS: dict[str, str] = {
    _OPEN_EVENT: "opening a file",
    "os.listdir": "listing a directory",
    "os.scandir": "listing a directory",
    "glob.glob": "listing a directory",
    "glob.glob/2": "listing a directory",
}
_PROCESS_EVENTS: dict[str, str] = {
    "os.exec": "running a command",
    "os.fork": "forking the process",
    "os.forkpty": "forking the process",
    "os.posix_spawn": "running a command",
    "os.spawn": "running a command",
    "os.startfile": "running a command",
    "os.system": "running a command",
    "subprocess.Popen": "running a command",
}
_PREFIX_EVENTS: tuple[tuple[str, str], ...] = (
    ("socket.", "network access"),
    ("ctypes.", "foreign function access"),
)
_GUARDED_EVENTS: frozenset[str] = frozenset({_IMPORT_EVENT, *_FILESYSTEM_EVENTS, *_PROCESS_EVENTS})
_GUARDED_PREFIXES: tuple[str, ...] = tuple(prefix for prefix, _ in _PREFIX_EVENTS)
_REMEDIATION: str = "read project inputs through ctx.project.tree and compiler facts"


class RuntimeGuard:
    """Audit hook rejecting untracked observations made while Rule code is on the stack."""

    def __init__(self, *, project_dir: Path) -> None:
        self._project_dir: Path = project_dir.resolve()
        self._rules_prefix: str = f"{self._project_dir / 'rules'}{os.sep}"
        self._importlib_prefix: str = f"{Path(importlib.__file__).resolve().parent}{os.sep}"
        self._mediated_codes: frozenset[CodeType] = frozenset({ProjectTree.read_text.__code__})
        self._rule_files: dict[str, bool] = {}
        self.active_rule: str | None = None
        self.violation: NonHermeticRuleError | None = None

    def __call__(self, event: str, arguments: tuple[object, ...]) -> None:
        if event not in _GUARDED_EVENTS and not event.startswith(_GUARDED_PREFIXES):
            return
        frame: FrameType = sys._getframe(1)
        rule_frame: FrameType | None = (
            self._importing_rule_frame(frame)
            if event == _IMPORT_EVENT
            else self._responsible_rule_frame(frame)
        )
        if rule_frame is None:
            return
        if event == _IMPORT_EVENT and allowed_custom_rule_import(str(arguments[0])):
            return
        self._reject(rule_frame=rule_frame, action=_action(event=event, arguments=arguments))

    @contextmanager
    def rule(self, code: str) -> Iterator[None]:
        """Attribute violations to one Rule and surface them even when Rule code catches them."""

        self.active_rule = code
        try:
            yield
        except Exception:
            self.raise_violation()
            raise
        finally:
            self.active_rule = None
        self.raise_violation()

    def raise_violation(self) -> None:
        """Raise the first recorded violation, if any."""

        if self.violation is not None:
            raise self.violation

    def _reject(self, *, rule_frame: FrameType, action: str) -> None:
        filename: Path = Path(rule_frame.f_code.co_filename)
        location: str = (
            filename.relative_to(self._project_dir).as_posix()
            if filename.is_relative_to(self._project_dir)
            else filename.as_posix()
        )
        owner: str = "" if self.active_rule is None else f" {self.active_rule}"
        error: NonHermeticRuleError = NonHermeticRuleError(
            f"non-hermetic custom rule{owner} at {location}:{rule_frame.f_lineno}: "
            f"{action} is not allowed; {_REMEDIATION}"
        )
        if self.violation is None:
            self.violation = error
        raise error

    def _responsible_rule_frame(self, frame: FrameType | None) -> FrameType | None:
        """Return the innermost Rule frame not shielded by module import or a mediated read."""

        while frame is not None:
            code: CodeType = frame.f_code
            if self._is_rule_file(code.co_filename):
                return frame
            if code in self._mediated_codes or (
                code.co_name == _IMPORT_ENTRY_FUNCTION
                and self._is_import_machinery(code.co_filename)
            ):
                return None
            frame = frame.f_back
        return None

    def _importing_rule_frame(self, frame: FrameType | None) -> FrameType | None:
        while frame is not None and self._is_import_machinery(frame.f_code.co_filename):
            frame = frame.f_back
        if frame is None or not self._is_rule_file(frame.f_code.co_filename):
            return None
        return frame

    def _is_rule_file(self, filename: str) -> bool:
        cached: bool | None = self._rule_files.get(filename)
        if cached is None:
            cached = filename.startswith(self._rules_prefix)
            self._rule_files[filename] = cached
        return cached

    def _is_import_machinery(self, filename: str) -> bool:
        return filename.startswith((_FROZEN_IMPORT_PREFIX, self._importlib_prefix))


def _action(*, event: str, arguments: tuple[object, ...]) -> str:
    if event == _OPEN_EVENT and arguments:
        return f"opening {arguments[0]!r}"
    if event == _IMPORT_EVENT and arguments:
        return f"import {arguments[0]!r}"
    action: str | None = _FILESYSTEM_EVENTS.get(event) or _PROCESS_EVENTS.get(event)
    if action is not None:
        return action
    return next(
        (prefix_action for prefix, prefix_action in _PREFIX_EVENTS if event.startswith(prefix)),
        event,
    )
