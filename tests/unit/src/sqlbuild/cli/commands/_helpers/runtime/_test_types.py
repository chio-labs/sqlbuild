from dataclasses import dataclass, field

from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.spec.contracts.models import LocalTargetConfig, TargetWarehousesConfig


@dataclass(frozen=True)
class ResolveProjectConnectionConfigTestCase:
    description: str
    project_dir_name: str
    expected_connection: dict[str, object]
    expected_warning_fragment: str = ""


@dataclass(frozen=True)
class ResolveEnvironmentConnectionConfigTestCase:
    description: str
    target_name: str
    expected_connection: dict[str, object]


@dataclass(frozen=True)
class ResolveConnectionConfigWarningTestCase:
    description: str
    raw_config: dict[str, object]
    adapter_name: str
    expected_connection: dict[str, object]
    expected_warning: str


@dataclass(frozen=True)
class ResolveDbtProfileConnectionConfigTestCase:
    description: str
    raw_config: dict[str, object]
    profile_connection: dict[str, object]
    expected_connection: dict[str, object]


@dataclass(frozen=True)
class NamedConnectionBehaviorTestCase:
    description: str
    expected_connection: dict[str, object]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CommandWarehouseResolutionTestCase:
    description: str
    command: str | None
    expected_warehouse: str | None
    expected_source: str
    project_warehouses: TargetWarehousesConfig = field(default_factory=TargetWarehousesConfig)
    local_targets: dict[str, LocalTargetConfig] = field(default_factory=dict)
    connection: dict[str, object] = field(
        default_factory=lambda: {"account": "example-account", "warehouse": "ANALYTICS_WH"}
    )
    cli_warehouse: str | None = None
    selected_target: str | None = None
    adapter: str = "snowflake"
    local_adapter: str | None = None
    adapter_file_contents: str = ""


@dataclass(frozen=True)
class CommandWarehouseErrorTestCase:
    description: str
    resolution: CommandWarehouseResolutionTestCase
    expected_code: str
    expected_message_fragment: str


@dataclass(frozen=True)
class WarehouseFlagParseTestCase:
    description: str
    argv: tuple[str, ...]
    expected_warehouse: str


@dataclass(frozen=True)
class WarehouseFlagRejectedTestCase:
    description: str
    argv: tuple[str, ...]
    expected_error_fragment: str = "unrecognized arguments: --warehouse"


@dataclass(frozen=True)
class CommandWarehouseClassificationTestCase:
    description: str
    command: CliCommand
    expected_classified: bool = True
