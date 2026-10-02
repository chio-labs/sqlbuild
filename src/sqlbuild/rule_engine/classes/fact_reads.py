"""Recorder for the compiler facts one custom-rule evaluation observes."""

from __future__ import annotations

import os

from sqlbuild.rule_engine.models import Model


class FactReads:
    """Collect the fact keys one custom-rule evaluation observes."""

    __slots__ = ("current", "observed", "uncacheable", "untracked")

    def __init__(self) -> None:
        self.current: set[tuple[object, ...]] | None = None
        self.untracked: bool = False
        self.uncacheable: bool = False
        self.observed: dict[tuple[str, ...], str | None] = {}

    def record(self, *, key: tuple[object, ...]) -> None:
        current: set[tuple[object, ...]] | None = self.current
        if current is not None:
            current.add(key)

    def record_model_path(self, *, fact: str, model: object) -> None:
        self._record_model(fact=fact, model=model, by_name=False)

    def record_model_name(self, *, fact: str, model: object) -> None:
        self._record_model(fact=fact, model=model, by_name=True)

    def _record_model(self, *, fact: str, model: object, by_name: bool) -> None:
        current: set[tuple[object, ...]] | None = self.current
        if current is None:
            return
        if type(model) is Model:
            current.add((fact, model.name if by_name else model.path))
        else:
            self.untracked = True

    def record_text(self, *, fact: str, values: tuple[object, ...]) -> tuple[str, ...] | None:
        current: set[tuple[object, ...]] | None = self.current
        if current is None:
            return None
        texts: list[str] = []
        for value in values:
            if isinstance(value, (str, os.PathLike)):
                texts.append(os.fspath(value))
            else:
                self.untracked = True
                return None
        key: tuple[str, ...] = (fact, *texts)
        current.add(key)
        return key

    def observe(self, *, key: tuple[str, ...], digest: str | None) -> None:
        """Remember the digest a live filesystem fact had when the rule read it."""

        if key in self.observed and self.observed[key] != digest:
            self.observed[key] = None
        else:
            self.observed.setdefault(key, digest)
