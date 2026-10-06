"""Process-wide ordering of stage captures."""

import itertools
import threading
from typing import ClassVar


class StageCaptureSequence:
    """Number stage captures in the order this process produced them."""

    _counter: ClassVar[itertools.count[int]] = itertools.count(1)
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def next_value(cls) -> int:
        """Return the next capture number."""

        with cls._lock:
            return next(cls._counter)
