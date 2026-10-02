"""Memoized digests of recorded custom-rule facts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from typing import Any

import orjson

from sqlbuild.rule_engine._helpers.engine.fact_replay import fact_outcome_digest
from sqlbuild.rule_engine.models import RuleFactViews
from sqlbuild.rule_engine.types import FactKey


class FactDigests:
    """Memoized digests of recorded fact keys against one compiled project snapshot."""

    def __init__(self, *, views: Callable[[], RuleFactViews]) -> None:
        self._views_factory: Callable[[], RuleFactViews] = views
        self._views: RuleFactViews | None = None
        self._digests: dict[FactKey, str] = {}

    @property
    def views(self) -> RuleFactViews:
        if self._views is None:
            self._views = self._views_factory()
        return self._views

    def digest(self, key: FactKey) -> str:
        """Return one fact digest, raising FactDigestError when it cannot be reproduced."""

        cached: str | None = self._digests.get(key)
        if cached is not None:
            return cached
        digest: str = fact_outcome_digest(views=self.views, key=key)
        self._digests[key] = digest
        return digest

    def combined(self, keys: Iterable[FactKey]) -> str:
        """Digest one read set in canonical key order."""

        combined: Any = hashlib.sha256()
        for key in sorted(keys):
            combined.update(orjson.dumps(key))
            combined.update(self.digest(key).encode())
        return combined.hexdigest()
