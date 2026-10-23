"""Keep every finished janitor action of one chunk, even when reporting it or waiting fails."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from sqlbuild.executor.janitor._helpers.worker_runs import submit_janitor_action
from sqlbuild.executor.janitor.models import JanitorActionOutcome, JanitorChunkOutcome


class JanitorChunkCollector[ResultT]:
    """Record each outcome before reporting it; a report error or interrupt stops new work only."""

    def __init__(self, *, size: int, on_done: Callable[..., None]) -> None:
        self._size: int = size
        self._on_done: Callable[..., None] = on_done
        self._outcomes: dict[int, JanitorActionOutcome[ResultT]] = {}
        self._interruption: BaseException | None = None
        self._report_error: BaseException | None = None

    @property
    def accepting(self) -> bool:
        """Whether more actions may start: nothing failed, raised or interrupted yet."""

        return (
            self._interruption is None
            and self._report_error is None
            and all(outcome.error is None for outcome in self._outcomes.values())
        )

    def record(self, *, index: int, outcome: JanitorActionOutcome[ResultT]) -> None:
        """Keep `outcome`, then report it unless reporting already failed."""

        if index in self._outcomes:
            return
        self._outcomes[index] = outcome
        if self._report_error is not None:
            return
        try:
            self._on_done(index=index, outcome=outcome)
        except BaseException as error:
            self._report_error = error

    def interrupt(self, error: BaseException) -> None:
        """Remember the first interrupt; running actions still finish and are recorded."""

        if self._interruption is None:
            self._interruption = error

    def collect[ItemT](
        self,
        *,
        pool: ThreadPoolExecutor,
        items: Sequence[ItemT],
        attempt: Callable[[ItemT], JanitorActionOutcome[ResultT]],
    ) -> None:
        """Submit items until stopped, then record every submitted action as it finishes."""

        futures: dict[Future[JanitorActionOutcome[ResultT]], int] = {}
        index: int
        item: ItemT
        for index, item in enumerate(items):
            if not self.accepting:
                break
            try:
                futures[submit_janitor_action(pool=pool, item=item, attempt=attempt)] = index
            except BaseException as error:
                self.interrupt(error)
        self.drain(futures=futures)

    def drain(self, *, futures: dict[Future[JanitorActionOutcome[ResultT]], int]) -> None:
        """Record every submitted action as it finishes, cancelling unstarted ones once stopped."""

        pending: set[Future[JanitorActionOutcome[ResultT]]] = set(futures)
        while pending:
            try:
                done: set[Future[JanitorActionOutcome[ResultT]]] = wait(
                    pending, return_when=FIRST_COMPLETED
                ).done
                future: Future[JanitorActionOutcome[ResultT]]
                for future in sorted(done, key=futures.__getitem__):
                    if not future.cancelled():
                        self.record(index=futures[future], outcome=future.result())
                    pending.discard(future)
            except BaseException as error:
                self.interrupt(error)
            if not self.accepting:
                pending = {future for future in pending if not future.cancel()}

    def outcome(self) -> JanitorChunkOutcome[ResultT]:
        """Every recorded outcome by item position, with the interrupt and report error."""

        return JanitorChunkOutcome(
            outcomes=tuple(self._outcomes.get(index) for index in range(self._size)),
            interruption=self._interruption,
            report_error=self._report_error,
        )
