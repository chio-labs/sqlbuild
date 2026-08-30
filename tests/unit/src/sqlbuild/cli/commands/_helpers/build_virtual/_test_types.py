from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualCallbackCloseTestCase:
    description: str
    error_type: type[BaseException]
    expected_scheduler_omitted: int
    expected_query_omitted: int
    expected_final_query_id: str
