"""Runtime provider lifecycle session."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from threading import RLock

from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.exceptions import (
    ProviderLookupError,
    ProviderSetupError,
    ProviderTeardownError,
)
from sqlbuild.providers import Provider


class ProviderSession:
    """Command-scoped provider lifecycle manager."""

    def __init__(
        self,
        providers: Mapping[str, Provider] | Iterable[tuple[str, Provider]],
        *,
        setup_context: object | None = None,
    ) -> None:
        self._providers: dict[str, Provider] = dict(providers)
        self._setup_context: object | None = setup_context
        self._container: ProviderContainer = ProviderContainer(self)
        self._setup_names: list[str] = []
        self._is_closed: bool = False
        self._lifecycle_lock: RLock = RLock()
        self._close_holds: int = 0
        self._close_requested: bool = False
        self.teardown_error: ProviderTeardownError | None = None

    @property
    def providers(self) -> ProviderContainer:
        return self._container

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._providers

    def __enter__(self) -> ProviderSession:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            self.close()
        except ProviderTeardownError as error:
            self.teardown_error = error
            if exc is None:
                raise
        return False

    def keys(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def get(self, name: str) -> Provider:
        with self._lifecycle_lock:
            if self._is_closed:
                raise ProviderLookupError(f"Provider session is closed; cannot access '{name}'")
            provider: Provider | None = self._providers.get(name)
            if provider is None:
                available: str = ", ".join(self.keys()) or "none"
                raise ProviderLookupError(
                    f"Provider '{name}' was not found. Available providers: {available}"
                )
            if name not in self._setup_names:
                self._setup_provider(name=name, provider=provider)
            return provider

    def hold_open(self) -> None:
        """Defer nested close requests while an outer command owner is active."""

        with self._lifecycle_lock:
            self._close_holds += 1

    def release(self) -> None:
        """Release an outer ownership hold and honor any deferred close request."""

        should_close = False
        with self._lifecycle_lock:
            if self._close_holds < 1:
                return
            self._close_holds -= 1
            should_close = self._close_holds == 0 and self._close_requested
        if should_close:
            self.close()

    def close(self, *, force: bool = False) -> None:
        with self._lifecycle_lock:
            if self._is_closed:
                return
            if self._close_holds and not force:
                self._close_requested = True
                return
            self._is_closed = True
            errors: list[str] = []
            for name in reversed(self._setup_names):
                provider: Provider = self._providers[name]
                try:
                    provider.teardown()
                except Exception as error:
                    errors.append(
                        f"Provider '{name}' ({provider.__class__.__name__}) failed during "
                        f"teardown: {error}"
                    )
            if errors:
                raise ProviderTeardownError("\n".join(errors))

    def _setup_provider(self, *, name: str, provider: Provider) -> None:
        try:
            provider.setup(self._setup_context)
        except Exception as error:
            raise ProviderSetupError(
                f"Provider '{name}' ({provider.__class__.__name__}) failed during setup: {error}"
            ) from error
        self._setup_names.append(name)
