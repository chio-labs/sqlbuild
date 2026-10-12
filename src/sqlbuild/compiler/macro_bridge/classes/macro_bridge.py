"""Per-compile state of the native macro bridge: call-site scans, call classes and the memo."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.macro_bridge._helpers.store_environment import (
    digest_module_files,
    module_digests_metadata,
    module_sources,
    project_fingerprint,
    store_environment,
    unchanged_module_digests,
)
from sqlbuild.compiler.macro_bridge.constants import MACRO_CALL_STORE_FILE_NAME
from sqlbuild.compiler.macro_bridge.models import (
    ModuleSources,
)


class MacroBridge:
    """Scan, memoize and splice macro calls for one compile; Python still runs every macro."""

    def __init__(self) -> None:
        self.memo: _native.MacroCallMemo = _native.MacroCallMemo()
        self._store_path: Path | None = None
        self._store_trusted: bool = False
        self._module_digests: dict[str, str] = {}
        self._observed_modules: dict[str, object] = {}
        self._project_inputs: tuple[Path, list[str], str] = (Path(), [], "")

    def attach_store(self, *, cache_dir: Path, project_dir: Path, model_paths: list[str]) -> None:
        """Reuse call results stored by earlier compiles of the same code and project files."""

        if self._store_path is not None:
            return
        path: Path = cache_dir / MACRO_CALL_STORE_FILE_NAME
        metadata: bytes
        loaded: int
        try:
            if not self.observe_modules():
                logging.getLogger(__name__).debug("Macro call store not used: unknown module code")
                return
            fingerprint: str = project_fingerprint(project_dir=project_dir, model_paths=model_paths)
            environment: str = store_environment(project_dir=project_dir, fingerprint=fingerprint)
            metadata, loaded = self.memo.attach_store(str(path), environment)
        except (OSError, RuntimeError) as error:
            logging.getLogger(__name__).debug("Macro call store not loaded: %s", error)
            return
        carried: dict[str, str] | None = (
            unchanged_module_digests(metadata=metadata, known=self._module_digests)
            if loaded
            else {}
        )
        if carried is None:
            self.memo.discard_store()
            carried = {}
        self._store_path = path
        self._store_trusted = True
        self._module_digests = {**carried, **self._module_digests}
        self._project_inputs = (project_dir, model_paths, fingerprint)
        self.memo.reset_call_classes(True)
        self._share_observed_modules()

    def save_store(self) -> None:
        """Save the results this compile used or recorded, unless code or files it read changed."""

        if self._store_path is None or not self._store_trusted:
            return
        project_dir, model_paths, fingerprint = self._project_inputs
        try:
            if (
                not self.observe_modules()
                or digest_module_files(self._module_digests) != self._module_digests
                or project_fingerprint(project_dir=project_dir, model_paths=model_paths)
                != fingerprint
            ):
                logging.getLogger(__name__).debug(
                    "Macro call store not saved: code or files changed"
                )
                return
            _ = self.memo.save_store(
                str(self._store_path), module_digests_metadata(self._module_digests)
            )
        except (OSError, RuntimeError) as error:
            logging.getLogger(__name__).debug("Macro call store not saved: %s", error)

    def observe_modules(self) -> bool:
        """Digest the files of modules loaded since the last look; False when one is unknown."""

        loaded: dict[str, object] = dict(sys.modules)
        added: list[object] = [
            module
            for name, module in loaded.items()
            if self._observed_modules.get(name) is not module
        ]
        self._observed_modules = loaded
        sources: ModuleSources = module_sources(added)
        digests: dict[str, str] | None = (
            digest_module_files(sources.paths) if sources.complete else None
        )
        if digests is None or any(
            self._module_digests.get(path, digest) != digest for path, digest in digests.items()
        ):
            self._store_trusted = False
            self._share_observed_modules()
            return False
        self._module_digests.update(digests)
        self._share_observed_modules()
        return True

    def _share_observed_modules(self) -> None:
        """Tell the memo how many modules a trusted store has seen, so it notices new imports."""

        self.memo.observe_modules(len(self._observed_modules) if self._store_trusted else None)

    def stats(self) -> tuple[int, int, int]:
        """Memo hits, misses and recorded results so far."""

        return self.memo.stats()

    def store_module_paths(self) -> tuple[str, ...]:
        """Module files the stored call results depend on, imported this compile or not."""

        return tuple(self._module_digests) if self._store_path is not None else ()

    def store_stats(self) -> tuple[int, int]:
        """Calls found in the store and calls recorded into it."""

        return self.memo.store_stats()
