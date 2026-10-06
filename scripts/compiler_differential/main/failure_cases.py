"""The failure corpus: one minimal failing project per diagnostic family member."""

from scripts.compiler_differential._helpers.failure_cases import all_failure_cases
from scripts.compiler_differential.models import FailureCase


def failure_cases() -> tuple[FailureCase, ...]:
    """Return every failure case in a stable order."""

    return all_failure_cases()
