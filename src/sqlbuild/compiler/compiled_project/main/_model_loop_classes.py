"""The Python classes and project inputs the native model loop builds models with."""

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery.models import DiscoveredAuditFactory, SqlHookEntry
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.scopes.models import UsageRecord
from sqlbuild.compiler.scopes.types import UsageKind


def model_loop_classes(*, audit_factories: tuple[DiscoveredAuditFactory, ...]) -> dict[str, object]:
    """Return the classes, error factories and audit factories the model loop reads."""

    return {
        "usage_record": UsageRecord,
        "compile_error": CompileInputError,
        "sql_hook_entry": SqlHookEntry,
        "config_error": native_config_error,
        "audit_factories": {factory.name: factory for factory in audit_factories},
        "generated_usage": UsageKind.GENERATED,
        "contract_enforced": ContractPolicy.ENFORCED,
    }
