from dataclasses import dataclass

from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


@dataclass(frozen=True)
class ExecutionJsonTestCase:
    description: str
    result: BuildExecutionResult
    python_node_results: tuple[PythonNodeExecutionResult, ...]
    expected_status: str
    expected_summary: dict[str, object]
    expected_asset_name: str
    expected_asset_status: str


@dataclass(frozen=True)
class ExecutionJsonRelationReuseTestCase:
    description: str
    expected_asset_name: str
    expected_relation_reuse: dict[str, object]


@dataclass(frozen=True)
class ExecutionJsonSeedReasonTestCase:
    description: str
    expected_asset_name: str
    expected_reason: str


@dataclass(frozen=True)
class ExecutionJsonCostTestCase:
    description: str
    expected_run_id: str
    expected_cost: dict[str, object]
