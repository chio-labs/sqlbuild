"""Test case types for compute log storage integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageLockTestCase:
    """A Python program making concurrent storage calls from two threads, and what it prints."""

    description: str
    script: str
    expected_stdout: str
