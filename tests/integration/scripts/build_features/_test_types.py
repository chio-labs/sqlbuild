"""Build feature alignment cases over real Cargo workspaces."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildFeaturesTestCase:
    """A workspace whose sqb and extension crates use a shared crate and a proc-macro."""

    description: str
    extension_shared_features: tuple[str, ...]
    extension_host_features: tuple[str, ...]
    expected_exit_code: int
    expected_drift: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryBuildFeaturesTestCase:
    """The repository's own sqb and extension builds."""

    description: str
    expected_exit_code: int
