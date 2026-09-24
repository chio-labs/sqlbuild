"""Shared SQL for relational virtual-state backends."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

from sqlbuild.virtual.state._helpers.state_storage.datetime import (
    from_naive_utc_wall_clock,
)
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import (
    FUNCTION_VERSION_TABLE,
    MODEL_VERSION_TABLE,
    PHYSICAL_RELATION_ANCESTRY_TABLE,
    PHYSICAL_RELATION_TABLE,
    PYTHON_NODE_VERSION_TABLE,
    SEED_VERSION_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_OPERATION_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
    VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
    VIRTUAL_ENVIRONMENT_TABLE,
)
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    PythonNodeVersionRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    StateOperationRecord,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentPythonNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    PhysicalArtifactType,
    StateOperationStatus,
    StateOperationType,
    VirtualEnvironmentStatus,
)


class SqlStateBackend(StateBackend):
    """Relational state backend owning SQL shared by DuckDB and Postgres."""

    _placeholder: ClassVar[str]

    @abstractmethod
    def _fetch_one(
        self, *, connection: Any, sql: str, params: Sequence[object] | None = None
    ) -> tuple[Any, ...] | None:
        """Run one read statement and return its first row."""
        ...

    @abstractmethod
    def _fetch_all(
        self, *, connection: Any, sql: str, params: Sequence[object] | None = None
    ) -> list[tuple[Any, ...]]:
        """Run one read statement and return all rows."""
        ...

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _qualified_name(self, *, schema: str, table: str) -> str:
        return f"{self._quote_identifier(schema)}.{self._quote_identifier(table)}"

    def get_model_version(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT model_name, version_hash, definition_identity_hash, "
            "identity_metadata_hash, definition_text_b64, identity_metadata_json_b64, "
            "compiled_sql_b64, status "
            f"FROM {self._qualified_name(schema=schema, table=MODEL_VERSION_TABLE)} "
            f"WHERE model_name = {p} AND version_hash = {p}",
            params=[model_name, version_hash],
        )
        if row is None:
            return None
        return ModelVersionRecord(
            model_name=row[0],
            version_hash=row[1],
            definition_identity_hash=row[2],
            identity_metadata_hash=row[3],
            definition_text_b64=row[4],
            identity_metadata_json_b64=row[5],
            compiled_sql_b64=row[6],
            status=ModelVersionStatus(row[7]),
        )

    def get_function_version(
        self, *, connection: Any, schema: str, function_name: str, version_hash: str
    ) -> FunctionVersionRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT function_name, version_hash, language, returns, arguments_json_b64, "
            "return_columns_json_b64, packages_json_b64, runtime_version, entry_point, "
            "body_sql_b64, definition_text_b64, status "
            f"FROM {self._qualified_name(schema=schema, table=FUNCTION_VERSION_TABLE)} "
            f"WHERE function_name = {p} AND version_hash = {p}",
            params=[function_name, version_hash],
        )
        if row is None:
            return None
        return FunctionVersionRecord(
            function_name=row[0],
            version_hash=row[1],
            language=row[2],
            returns=row[3],
            arguments_json_b64=row[4],
            return_columns_json_b64=row[5],
            packages_json_b64=row[6],
            runtime_version=row[7],
            entry_point=row[8],
            body_sql_b64=row[9],
            definition_text_b64=row[10],
            status=ModelVersionStatus(row[11]),
        )

    def get_seed_version(
        self, *, connection: Any, schema: str, seed_name: str, version_hash: str
    ) -> SeedVersionRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT seed_name, version_hash, identity_metadata_hash, "
            "identity_metadata_json_b64, status "
            f"FROM {self._qualified_name(schema=schema, table=SEED_VERSION_TABLE)} "
            f"WHERE seed_name = {p} AND version_hash = {p}",
            params=[seed_name, version_hash],
        )
        if row is None:
            return None
        return SeedVersionRecord(
            seed_name=row[0],
            version_hash=row[1],
            identity_metadata_hash=row[2],
            identity_metadata_json_b64=row[3],
            status=ModelVersionStatus(row[4]),
        )

    def get_python_node_version(
        self,
        *,
        connection: Any,
        schema: str,
        node_type: str,
        node_name: str,
        version_hash: str,
    ) -> PythonNodeVersionRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT node_type, node_name, version_hash, definition_hash, "
            "identity_metadata_hash, definition_json_b64, identity_metadata_json_b64, status "
            f"FROM {self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} "
            f"WHERE node_type = {p} AND node_name = {p} AND version_hash = {p}",
            params=[node_type, node_name, version_hash],
        )
        if row is None:
            return None
        return PythonNodeVersionRecord(
            node_type=row[0],
            node_name=row[1],
            version_hash=row[2],
            definition_hash=row[3],
            identity_metadata_hash=row[4],
            definition_json_b64=row[5],
            identity_metadata_json_b64=row[6],
            status=ModelVersionStatus(row[7]),
        )

    def get_physical_relation_for_artifact(
        self,
        *,
        connection: Any,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
        version_hash: str,
    ) -> PhysicalRelationRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT artifact_type, artifact_name, version_hash, database_name, schema_name, "
            "relation_name, relation_type "
            f"FROM {self._qualified_name(schema=schema, table=PHYSICAL_RELATION_TABLE)} "
            f"WHERE artifact_type = {p} AND artifact_name = {p} AND version_hash = {p}",
            params=[artifact_type.value, artifact_name, version_hash],
        )
        if row is None:
            return None
        return PhysicalRelationRecord(
            artifact_type=PhysicalArtifactType(row[0]),
            artifact_name=row[1],
            version_hash=row[2],
            database_name=row[3],
            schema_name=row[4],
            relation_name=row[5],
            relation_type=row[6],
        )

    def list_physical_relations_for_artifact(
        self,
        *,
        connection: Any,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
    ) -> tuple[PhysicalRelationRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT artifact_type, artifact_name, version_hash, database_name, schema_name, "
            "relation_name, relation_type "
            f"FROM {self._qualified_name(schema=schema, table=PHYSICAL_RELATION_TABLE)} "
            f"WHERE artifact_type = {p} AND artifact_name = {p} "
            "ORDER BY updated_at DESC, version_hash DESC",
            params=[artifact_type.value, artifact_name],
        )
        return tuple(
            PhysicalRelationRecord(
                artifact_type=PhysicalArtifactType(row[0]),
                artifact_name=row[1],
                version_hash=row[2],
                database_name=row[3],
                schema_name=row[4],
                relation_name=row[5],
                relation_type=row[6],
            )
            for row in rows
        )

    def get_physical_relation_ancestry(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationAncestryRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT model_name, version_hash, parent_model_name, parent_version_hash, "
            "seed_strategy "
            f"FROM {self._qualified_name(schema=schema, table=PHYSICAL_RELATION_ANCESTRY_TABLE)} "
            f"WHERE model_name = {p} AND version_hash = {p}",
            params=[model_name, version_hash],
        )
        if row is None:
            return None
        return PhysicalRelationAncestryRecord(
            model_name=row[0],
            version_hash=row[1],
            parent_model_name=row[2],
            parent_version_hash=row[3],
            seed_strategy=row[4],
        )

    def get_virtual_environment(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT virtual_environment_name, status, baseline_virtual_environment_name, "
            "finalized_at "
            f"FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
            f"WHERE virtual_environment_name = {p}",
            params=[virtual_environment_name],
        )
        if row is None:
            return None
        return VirtualEnvironmentRecord(
            virtual_environment_name=row[0],
            status=VirtualEnvironmentStatus(row[1]),
            baseline_virtual_environment_name=row[2],
            finalized_at=row[3],
        )

    def get_virtual_environment_node_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
    ) -> tuple[VirtualEnvironmentNodeRefRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT virtual_environment_name, node_type, node_name, version_hash "
            f"FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            f"WHERE virtual_environment_name = {p} AND node_type = {p} ORDER BY node_name",
            params=[virtual_environment_name, node_type],
        )
        return tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=row[0],
                node_type=row[1],
                node_name=row[2],
                version_hash=row[3],
            )
            for row in rows
        )

    def get_virtual_environment_model_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = self.get_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="model",
        )
        return tuple(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                model_name=ref.node_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        )

    def get_virtual_environment_function_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = (
            *self.get_virtual_environment_node_refs(
                connection=connection,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                node_type="udf",
            ),
            *self.get_virtual_environment_node_refs(
                connection=connection,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                node_type="table_fn",
            ),
        )
        return tuple(
            VirtualEnvironmentFunctionRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                function_name=ref.node_name,
                version_hash=ref.version_hash,
            )
            for ref in sorted(refs, key=lambda item: (item.node_type, item.node_name))
        )

    def get_virtual_environment_seed_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentSeedRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = self.get_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="seed",
        )
        return tuple(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                seed_name=ref.node_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        )

    def get_virtual_environment_python_node_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentPythonNodeRefRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT virtual_environment_name, node_type, node_name, version_hash "
            f"FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            f"WHERE virtual_environment_name = {p} "
            "AND node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
            "ORDER BY node_type, node_name",
            params=[virtual_environment_name],
        )
        return tuple(
            VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=row[0],
                node_type=row[1],
                node_name=row[2],
                version_hash=row[3],
            )
            for row in rows
        )

    def get_virtual_environment_source_freshness(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[SourceFreshnessRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT virtual_environment_name, source_name, strategy, value_kind, "
            "data_version, data_version_hash, observed_at "
            f"FROM {self._qualified_name(schema=schema, table=SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
            f"WHERE virtual_environment_name = {p} ORDER BY source_name",
            params=[virtual_environment_name],
        )
        return tuple(
            SourceFreshnessRecord(
                virtual_environment_name=row[0],
                source_name=row[1],
                strategy=row[2],
                value_kind=row[3],
                data_version=row[4],
                data_version_hash=row[5],
                observed_at=from_naive_utc_wall_clock(row[6]),
            )
            for row in rows
        )

    def list_virtual_environment_checkpoints(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT checkpoint_id, virtual_environment_name, created_at "
            "FROM "
            f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE)} "
            f"WHERE virtual_environment_name = {p} ORDER BY created_at DESC, checkpoint_id DESC",
            params=[virtual_environment_name],
        )
        return tuple(
            VirtualEnvironmentCheckpointRecord(
                checkpoint_id=row[0],
                virtual_environment_name=row[1],
                created_at=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_model_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT checkpoint_id, model_name, version_hash FROM "
            + self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
            )
            + " "
            f"WHERE checkpoint_id = {p} ORDER BY model_name",
            params=[checkpoint_id],
        )
        return tuple(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id=row[0],
                model_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_function_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        p: str = self._placeholder
        checkpoint_function_ref_table: str = self._qualified_name(
            schema=schema,
            table=VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
        )
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql=f"SELECT checkpoint_id, function_name, version_hash "
            f"FROM {checkpoint_function_ref_table} "
            f"WHERE checkpoint_id = {p} ORDER BY function_name",
            params=[checkpoint_id],
        )
        return tuple(
            VirtualEnvironmentCheckpointFunctionRefRecord(
                checkpoint_id=row[0],
                function_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_seed_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]:
        p: str = self._placeholder
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT checkpoint_id, seed_name, version_hash FROM "
            + self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
            )
            + " "
            f"WHERE checkpoint_id = {p} ORDER BY seed_name",
            params=[checkpoint_id],
        )
        return tuple(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id=row[0],
                seed_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_state_operation(
        self, *, connection: Any, schema: str, operation_id: str
    ) -> StateOperationRecord | None:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql="SELECT operation_id, operation_type, status, virtual_environment_name "
            f"FROM {self._qualified_name(schema=schema, table=STATE_OPERATION_TABLE)} "
            f"WHERE operation_id = {p}",
            params=[operation_id],
        )
        if row is None:
            return None
        return StateOperationRecord(
            operation_id=row[0],
            operation_type=StateOperationType(row[1]),
            status=StateOperationStatus(row[2]),
            virtual_environment_name=row[3],
        )
