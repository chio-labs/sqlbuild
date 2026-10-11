"""The builder, storage defaults and classes a model's `CompileModelConfig` is made of."""

from sqlbuild.compiler.compile.models import CompileModelConfig, NativeModelConfigSession
from sqlbuild.compiler.compiled_project.constants import TABLE_BACKED_MATERIALIZATIONS
from sqlbuild.spec.contracts.models import ResolvedTableType, ResolvedTimeTravelRetention
from sqlbuild.spec.contracts.types import TableType, TableTypeSource, TimeTravelRetentionSource


def native_config_classes(
    *, session: NativeModelConfigSession, record_template_reads: object
) -> dict[str, object]:
    """The builder, storage defaults and classes a model's `CompileModelConfig` is made of."""

    return {
        "builder": session.builder,
        "inherited_storage": session.inherited_storage,
        "table_backed": tuple(
            str(materialization) for materialization in TABLE_BACKED_MATERIALIZATIONS
        ),
        "compile_model_config": CompileModelConfig,
        "resolved_retention": ResolvedTimeTravelRetention,
        "retention_source": TimeTravelRetentionSource.MODEL,
        "resolved_table_type": ResolvedTableType,
        "table_type": TableType,
        "table_type_source": TableTypeSource.MODEL,
        "record_template_reads": record_template_reads,
    }
