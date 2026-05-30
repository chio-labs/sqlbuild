from dataclasses import dataclass

from sqlbuild.shared.models import ColumnLineageRef, RetryPolicy
from sqlbuild.shared.types import PythonCheckSeverity


@dataclass(frozen=True)
class TaskDecoratorMetadataTestCase:
    description: str
    expected_name: str
    expected_dep_count: int
    expected_tags: tuple[str, ...]
    expected_group: str | None
    expected_description: str | None
    expected_meta: dict[str, object] | None
    expected_retry: RetryPolicy | None = None


@dataclass(frozen=True)
class AssetDecoratorMetadataTestCase:
    description: str
    expected_name: str
    expected_dep_count: int
    expected_tags: tuple[str, ...]
    expected_group: str | None
    expected_description: str | None
    expected_meta: dict[str, object] | None
    expected_column_names: tuple[str, ...]
    expected_column_types: tuple[str | None, ...]
    expected_column_descriptions: tuple[str | None, ...]
    expected_column_lineage: dict[str, tuple[ColumnLineageRef, ...]]
    expected_retry: RetryPolicy | None = None


@dataclass(frozen=True)
class CheckDecoratorMetadataTestCase:
    description: str
    expected_name: str
    expected_dep_count: int
    expected_severity: PythonCheckSeverity
    expected_tags: tuple[str, ...]
    expected_group: str | None
    expected_description: str | None
    expected_meta: dict[str, object] | None
