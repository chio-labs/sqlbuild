from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualBuildPipelineTestCase:
    description: str
    expected_schema: str
    expected_model_names: tuple[str, ...]
    expected_target: str


@dataclass(frozen=True)
class VirtualLeaseAcquireBoundaryTestCase:
    """Expected cleanup when interruption happens immediately after lease acquisition."""

    description: str
    expected_error_type: type[BaseException]
    expected_active_lock_count: int
