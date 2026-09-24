"""Shared SQL for relational virtual-state backends."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, ClassVar

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.virtual.state._helpers.state_storage.datetime import (
    from_naive_utc_wall_clock,
)
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import (
    FUNCTION_VERSION_TABLE,
    LOCK_TABLE,
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
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    PythonNodeVersionRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    StateLockRecord,
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
    VirtualEnvironmentRetentionRecord,
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

    @abstractmethod
    def _write_transaction(self, *, connection: Any) -> AbstractContextManager[Any]:
        """Open a write transaction and yield the executor that runs its statements."""
        ...

    @abstractmethod
    def _execute_in(self, *, executor: Any, sql: str, params: Sequence[object]) -> None:
        """Run one statement on a transaction executor."""
        ...

    @abstractmethod
    def _fetch_one_in(
        self, *, executor: Any, sql: str, params: Sequence[object]
    ) -> tuple[Any, ...] | None:
        """Run one read statement on a transaction executor and return its first row."""
        ...

    def upsert_model_version(
        self, *, connection: Any, schema: str, record: ModelVersionRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=MODEL_VERSION_TABLE,
                key_values={"model_name": record.model_name, "version_hash": record.version_hash},
                row_values={
                    "definition_identity_hash": record.definition_identity_hash,
                    "identity_metadata_hash": record.identity_metadata_hash,
                    "definition_text_b64": record.definition_text_b64,
                    "identity_metadata_json_b64": record.identity_metadata_json_b64,
                    "compiled_sql_b64": record.compiled_sql_b64,
                    "status": record.status.value,
                },
            )

    def upsert_function_version(
        self, *, connection: Any, schema: str, record: FunctionVersionRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=FUNCTION_VERSION_TABLE,
                key_values={
                    "function_name": record.function_name,
                    "version_hash": record.version_hash,
                },
                row_values={
                    "language": record.language,
                    "returns": record.returns,
                    "arguments_json_b64": record.arguments_json_b64,
                    "return_columns_json_b64": record.return_columns_json_b64,
                    "packages_json_b64": record.packages_json_b64,
                    "runtime_version": record.runtime_version,
                    "entry_point": record.entry_point,
                    "body_sql_b64": record.body_sql_b64,
                    "definition_text_b64": record.definition_text_b64,
                    "status": record.status.value,
                },
            )

    def upsert_seed_version(
        self, *, connection: Any, schema: str, record: SeedVersionRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=SEED_VERSION_TABLE,
                key_values={"seed_name": record.seed_name, "version_hash": record.version_hash},
                row_values={
                    "identity_metadata_hash": record.identity_metadata_hash,
                    "identity_metadata_json_b64": record.identity_metadata_json_b64,
                    "status": record.status.value,
                },
            )

    def upsert_python_node_version(
        self, *, connection: Any, schema: str, record: PythonNodeVersionRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=PYTHON_NODE_VERSION_TABLE,
                key_values={
                    "node_type": record.node_type,
                    "node_name": record.node_name,
                    "version_hash": record.version_hash,
                },
                row_values={
                    "definition_hash": record.definition_hash,
                    "identity_metadata_hash": record.identity_metadata_hash,
                    "definition_json_b64": record.definition_json_b64,
                    "identity_metadata_json_b64": record.identity_metadata_json_b64,
                    "status": record.status.value,
                },
            )

    def upsert_physical_relation(
        self, *, connection: Any, schema: str, record: PhysicalRelationRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=PHYSICAL_RELATION_TABLE,
                key_values={
                    "artifact_type": record.artifact_type.value,
                    "artifact_name": record.artifact_name,
                    "version_hash": record.version_hash,
                },
                row_values={
                    "database_name": record.database_name,
                    "schema_name": record.schema_name,
                    "relation_name": record.relation_name,
                    "relation_type": record.relation_type,
                },
            )

    def upsert_physical_relation_ancestry(
        self, *, connection: Any, schema: str, record: PhysicalRelationAncestryRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=PHYSICAL_RELATION_ANCESTRY_TABLE,
                key_values={"model_name": record.model_name, "version_hash": record.version_hash},
                row_values={
                    "parent_model_name": record.parent_model_name,
                    "parent_version_hash": record.parent_version_hash,
                    "seed_strategy": record.seed_strategy,
                },
            )

    def upsert_virtual_environment(
        self, *, connection: Any, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._upsert_virtual_environment_record(executor=executor, schema=schema, record=record)

    def upsert_state_operation(
        self, *, connection: Any, schema: str, record: StateOperationRecord
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_row_preserving_created_at(
                executor=executor,
                schema=schema,
                table_name=STATE_OPERATION_TABLE,
                key_values={"operation_id": record.operation_id},
                row_values={
                    "operation_type": record.operation_type.value,
                    "status": record.status.value,
                    "virtual_environment_name": record.virtual_environment_name,
                },
            )

    def _upsert_virtual_environment_record(
        self, *, executor: Any, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        self._replace_row_preserving_created_at(
            executor=executor,
            schema=schema,
            table_name=VIRTUAL_ENVIRONMENT_TABLE,
            key_values={"virtual_environment_name": record.virtual_environment_name},
            row_values={
                "status": record.status.value,
                "baseline_virtual_environment_name": record.baseline_virtual_environment_name,
                "finalized_at": record.finalized_at,
            },
        )

    def list_virtual_environments(
        self, *, connection: Any, schema: str
    ) -> tuple[VirtualEnvironmentRetentionRecord, ...]:
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT virtual_environment_name, status, updated_at "
            f"FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
            "ORDER BY updated_at DESC, virtual_environment_name DESC",
        )
        return tuple(
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name=row[0],
                status=VirtualEnvironmentStatus(row[1]),
                updated_at=row[2],
            )
            for row in rows
        )

    def renew_lock(
        self,
        *,
        connection: Any,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        p: str = self._placeholder
        row: tuple[Any, ...] | None = self._fetch_one(
            connection=connection,
            sql=f"UPDATE {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
            f"SET expires_at = {p}, updated_at = CURRENT_TIMESTAMP "
            f"WHERE lock_key = {p} AND owner_id = {p} AND expires_at > CURRENT_TIMESTAMP "
            "RETURNING lock_key",
            params=[expires_at, lock_key, owner_id],
        )
        return row is not None

    def list_active_locks(self, *, connection: Any, schema: str) -> tuple[StateLockRecord, ...]:
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT lock_key, owner_id, expires_at FROM "
            f"{self._qualified_name(schema=schema, table=LOCK_TABLE)} "
            "WHERE expires_at > CURRENT_TIMESTAMP ORDER BY lock_key",
        )
        return tuple(
            StateLockRecord(lock_key=row[0], owner_id=row[1], expires_at=row[2]) for row in rows
        )

    def list_expired_locks(self, *, connection: Any, schema: str) -> tuple[StateLockRecord, ...]:
        rows: list[tuple[Any, ...]] = self._fetch_all(
            connection=connection,
            sql="SELECT lock_key, owner_id, expires_at FROM "
            f"{self._qualified_name(schema=schema, table=LOCK_TABLE)} "
            "WHERE expires_at <= CURRENT_TIMESTAMP ORDER BY lock_key",
        )
        return tuple(
            StateLockRecord(lock_key=row[0], owner_id=row[1], expires_at=row[2]) for row in rows
        )

    @abstractmethod
    def _replace_virtual_environment_node_ref_groups(
        self,
        *,
        executor: Any,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        """Replace node refs per node type inside an open write transaction."""
        ...

    def replace_virtual_environment_node_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_ref_groups(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            refs_by_node_type={node_type: refs},
        )

    def replace_virtual_environment_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._replace_virtual_environment_node_ref_groups(
                executor=executor,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                refs_by_node_type=refs_by_node_type,
            )

    def upsert_virtual_environment_and_replace_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        with self._write_transaction(connection=connection) as executor:
            self._upsert_virtual_environment_record(executor=executor, schema=schema, record=record)
            self._replace_virtual_environment_node_ref_groups(
                executor=executor,
                schema=schema,
                virtual_environment_name=record.virtual_environment_name,
                refs_by_node_type=refs_by_node_type,
            )

    def replace_virtual_environment_model_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="model",
            refs=tuple(
                VirtualEnvironmentNodeRefRecord(
                    virtual_environment_name=ref.virtual_environment_name,
                    node_type="model",
                    node_name=ref.model_name,
                    version_hash=ref.version_hash,
                )
                for ref in refs
            ),
        )

    def replace_virtual_environment_function_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        ref: VirtualEnvironmentFunctionRefRecord
        for ref in refs:
            if ref.node_type not in {
                CompiledResourceType.UDF,
                CompiledResourceType.TABLE_FN,
            }:
                raise StateBackendConfigError("Function ref node_type must be 'udf' or 'table_fn'")
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]] = {}
        for node_type in ("udf", "table_fn"):
            node_refs: list[VirtualEnvironmentNodeRefRecord] = []
            for ref in refs:
                if ref.node_type == node_type:
                    node_refs.append(
                        VirtualEnvironmentNodeRefRecord(
                            virtual_environment_name=ref.virtual_environment_name,
                            node_type=ref.node_type,
                            node_name=ref.function_name,
                            version_hash=ref.version_hash,
                        )
                    )
            refs_by_node_type[node_type] = tuple(node_refs)
        self.replace_virtual_environment_node_ref_groups(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            refs_by_node_type=refs_by_node_type,
        )

    def replace_virtual_environment_seed_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="seed",
            refs=tuple(
                VirtualEnvironmentNodeRefRecord(
                    virtual_environment_name=ref.virtual_environment_name,
                    node_type="seed",
                    node_name=ref.seed_name,
                    version_hash=ref.version_hash,
                )
                for ref in refs
            ),
        )

    def upsert_virtual_environment_python_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentPythonNodeRefRecord,
    ) -> None:
        self.upsert_virtual_environment_node_ref(
            connection=connection,
            schema=schema,
            ref=VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.node_name,
                version_hash=ref.version_hash,
            ),
        )

    def _validate_node_ref_replacement(
        self,
        *,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        seen_node_names: set[str] = set()
        ref: VirtualEnvironmentNodeRefRecord
        for ref in refs:
            if ref.virtual_environment_name != virtual_environment_name:
                raise StateBackendConfigError(
                    "Node ref virtual_environment_name must match replacement "
                    "virtual_environment_name"
                )
            if ref.node_type != node_type:
                raise StateBackendConfigError("Node ref node_type must match replacement node_type")
            if ref.node_name in seen_node_names:
                raise StateBackendConfigError(
                    f"Duplicate node ref for node type '{node_type}' and name '{ref.node_name}'"
                )
            seen_node_names.add(ref.node_name)

    def _replace_row_preserving_created_at(
        self,
        *,
        executor: Any,
        schema: str,
        table_name: str,
        key_values: dict[str, object],
        row_values: dict[str, object],
    ) -> None:
        p: str = self._placeholder
        table: str = self._qualified_name(schema=schema, table=table_name)
        where_sql: str = " AND ".join(f"{column} = {p}" for column in key_values)
        key_params: list[object] = list(key_values.values())
        existing_created_at: datetime | None = self._created_at_for_key(
            executor=executor,
            schema=schema,
            table_name=table_name,
            where_sql=where_sql,
            params=key_params,
        )
        self._execute_in(
            executor=executor, sql=f"DELETE FROM {table} WHERE {where_sql}", params=key_params
        )
        columns: tuple[str, ...] = (*key_values, *row_values)
        value_placeholders: str = ", ".join(p for _ in columns)
        self._execute_in(
            executor=executor,
            sql=(
                f"INSERT INTO {table} ({', '.join(columns)}, created_at, updated_at) "
                f"VALUES ({value_placeholders}, COALESCE({p}, CURRENT_TIMESTAMP), "
                "CURRENT_TIMESTAMP)"
            ),
            params=[*key_params, *row_values.values(), existing_created_at],
        )

    def _created_at_for_key(
        self,
        *,
        executor: Any,
        schema: str,
        table_name: str,
        where_sql: str,
        params: list[object],
    ) -> datetime | None:
        row: tuple[Any, ...] | None = self._fetch_one_in(
            executor=executor,
            sql=(
                f"SELECT created_at FROM {self._qualified_name(schema=schema, table=table_name)} "
                f"WHERE {where_sql}"
            ),
            params=params,
        )
        if row is None:
            return None
        return row[0]

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
