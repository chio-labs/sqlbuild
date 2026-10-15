//! The compiler, rule, lint and config string enums hosted natively.

use crate::bindings::_helpers::records::models::EnumSpec;

const E_CONTRACT_FINDING_KIND: EnumSpec = EnumSpec {
    name: "ContractFindingKind",
    doc: "Stable physical-to-authored contract difference categories.",
    members: &[
        ("MISSING_DECLARATION", "missing_declaration"),
        ("MISSING_PHYSICAL_COLUMN", "missing_physical_column"),
        ("TYPE_MISMATCH", "type_mismatch"),
        ("RELATION_MISSING", "relation_missing"),
        ("INSPECTION_UNAVAILABLE", "inspection_unavailable"),
        ("OWNERSHIP_CONFLICT", "ownership_conflict"),
    ],
};
const E_COMPILER_STAGE: EnumSpec = EnumSpec {
    name: "CompilerStage",
    doc: "Frontier objects handed from one compiler stage to the next, in pipeline order.",
    members: &[
        ("DISCOVERED_PROJECT_INPUTS", "discovered_project_inputs"),
        ("COMPILE_PROJECT_INPUTS", "compile_project_inputs"),
        ("COMPILED_PROJECT", "compiled_project"),
    ],
};
const E_HOOK_READ_TYPE: EnumSpec = EnumSpec {
    name: "HookReadType",
    doc: "Kind of model hook that declares or writes a read.",
    members: &[
        ("PYTHON", "Python"),
        ("SQL", "SQL"),
        ("INLINE_SQL", "inline SQL"),
    ],
};
const E_LINT_SEVERITY: EnumSpec = EnumSpec {
    name: "LintSeverity",
    doc: "Severity assigned to one lint violation.",
    members: &[("FAULT", "fault"), ("WARNING", "warning")],
};
const E_DIAGNOSTIC_PHASE: EnumSpec = EnumSpec {
    name: "DiagnosticPhase",
    doc: "Phase that produced a compiler diagnostic.",
    members: &[
        ("COMPILE", "compile"),
        ("CONTRACT", "contract"),
        ("RULE", "rule"),
        ("PLAN", "plan"),
        ("BUILD", "build"),
        ("AUDIT", "audit"),
        ("TEST", "test"),
        ("CONNECTION", "connection"),
    ],
};
const E_DIAGNOSTIC_SEVERITY: EnumSpec = EnumSpec {
    name: "DiagnosticSeverity",
    doc: "Severity for a compiler diagnostic.",
    members: &[("ERROR", "error"), ("WARNING", "warning"), ("INFO", "info")],
};
const E_COLUMN_TRANSFORM_KIND: EnumSpec = EnumSpec {
    name: "ColumnTransformKind",
    doc: "High-level transform classification for one output column.",
    members: &[
        ("DIRECT", "direct"),
        ("CAST", "cast"),
        ("EXPRESSION", "expression"),
        ("AGGREGATION", "aggregation"),
        ("STAR", "star"),
        ("CONSTANT", "constant"),
        ("UNKNOWN", "unknown"),
    ],
};
const E_COLUMN_LINEAGE_CONFIDENCE: EnumSpec = EnumSpec {
    name: "ColumnLineageConfidence",
    doc: "Coarse confidence that a lineage edge is fully understood.",
    members: &[
        ("HIGH", "high"),
        ("MEDIUM", "medium"),
        ("LOW", "low"),
        ("UNKNOWN", "unknown"),
    ],
};
const E_COLUMN_LINEAGE_MODE: EnumSpec = EnumSpec {
    name: "ColumnLineageMode",
    doc: "Column lineage analyzer mode.",
    members: &[("RICH", "rich"), ("FAST", "fast")],
};
const E_POLYGLOT_ANALYSIS_DIALECT: EnumSpec = EnumSpec {
    name: "PolyglotAnalysisDialect",
    doc: "Dialect names accepted by Polyglot analyze_query.",
    members: &[
        ("GENERIC", "generic"),
        ("POSTGRESQL", "postgresql"),
        ("MYSQL", "mysql"),
        ("BIGQUERY", "bigquery"),
        ("SNOWFLAKE", "snowflake"),
        ("DUCKDB", "duckdb"),
        ("SQLITE", "sqlite"),
        ("HIVE", "hive"),
        ("SPARK", "spark"),
        ("TRINO", "trino"),
        ("PRESTO", "presto"),
        ("REDSHIFT", "redshift"),
        ("TSQL", "tsql"),
        ("ORACLE", "oracle"),
        ("CLICKHOUSE", "clickhouse"),
        ("DATABRICKS", "databricks"),
        ("ATHENA", "athena"),
        ("TERADATA", "teradata"),
        ("DORIS", "doris"),
        ("STARROCKS", "starrocks"),
        ("MATERIALIZE", "materialize"),
        ("RISINGWAVE", "risingwave"),
        ("SINGLESTORE", "singlestore"),
        ("COCKROACHDB", "cockroachdb"),
        ("TIDB", "tidb"),
        ("DRUID", "druid"),
        ("SOLR", "solr"),
        ("TABLEAU", "tableau"),
        ("DUNE", "dune"),
        ("FABRIC", "fabric"),
        ("DRILL", "drill"),
        ("DREMIO", "dremio"),
        ("EXASOL", "exasol"),
        ("DATAFUSION", "datafusion"),
    ],
};
const E_MIGRATION_DISCOVERY: EnumSpec = EnumSpec {
    name: "MigrationDiscovery",
    doc: "How a migration was requested.",
    members: &[("MANUAL", "manual"), ("AUTOMATIC", "automatic")],
};
const E_MIGRATION_COMPATIBILITY: EnumSpec = EnumSpec {
    name: "MigrationCompatibility",
    doc: "Outcome of checking the origin relation against the destination model.",
    members: &[
        ("COMPATIBLE", "compatible"),
        ("INCOMPATIBLE", "incompatible"),
        ("NOT_CHECKED", "not_checked"),
    ],
};
const E_OLD_NAME_VIEW_ACTION: EnumSpec = EnumSpec {
    name: "OldNameViewAction",
    doc: "What a build does at a migrated model's old name.",
    members: &[
        ("ARCHIVE_AND_VIEW", "archive_and_view"),
        ("VIEW_ONLY", "view_only"),
        ("LIVE", "live"),
        ("NONE", "none"),
    ],
};
const E_SELECTOR_KIND: EnumSpec = EnumSpec {
    name: "SelectorKind",
    doc: "",
    members: &[
        ("NAME", "name"),
        ("SEED", "seed"),
        ("SOURCE", "source"),
        ("TASK", "task"),
        ("ASSET", "asset"),
        ("LOADER", "loader"),
        ("CHECK", "check"),
        ("TAG", "tag"),
        ("PATH", "path"),
        ("TEST", "test"),
    ],
};
const E_PYTHON_RUN_PHASE: EnumSpec = EnumSpec {
    name: "PythonRunPhase",
    doc: "Lifecycle-aware Python execution phase.",
    members: &[
        ("PRE_SQL_INGRESS", "pre_sql_ingress"),
        ("READ_SIDE", "read_side"),
    ],
};
const E_PYTHON_IDENTITY_STATUS: EnumSpec = EnumSpec {
    name: "PythonIdentityStatus",
    doc: "Read-only identity diff status for Python plan display.",
    members: &[
        ("NEW", "new"),
        ("CHANGED", "changed"),
        ("UNCHANGED", "unchanged"),
        ("UNKNOWN", "unknown"),
    ],
};
const E_COLLECTION_RENDERING: EnumSpec = EnumSpec {
    name: "CollectionRendering",
    doc: "Physical rendering choices for homogeneous SQL collections.",
    members: &[("VALUE_LIST", "value_list"), ("ARRAY", "array")],
};
const E_RESOURCE_KIND: EnumSpec = EnumSpec {
    name: "ResourceKind",
    doc: "Kinds of authored resources represented in a scope index.",
    members: &[
        ("MODEL", "model"),
        ("TEST", "test"),
        ("SCENARIO", "scenario"),
        ("FUNCTION", "function"),
        ("SOURCE", "source"),
        ("SEED", "seed"),
    ],
};
const E_DECLARATION_KIND: EnumSpec = EnumSpec {
    name: "DeclarationKind",
    doc: "Independent public declaration namespaces.",
    members: &[
        ("MACRO", "macro"),
        ("ENUM", "enum"),
        ("CONSTANT", "constant"),
        ("AUDIT", "audit"),
        ("SINGULAR_AUDIT", "singular_audit"),
        ("SCHEMA", "schema"),
        ("SQL_HOOK", "sql_hook"),
        ("PYTHON_HOOK", "python_hook"),
    ],
};
const E_SCOPE_KIND: EnumSpec = EnumSpec {
    name: "ScopeKind",
    doc: "Compiler-enforced declaration visibility tiers.",
    members: &[
        ("GLOBAL", "global"),
        ("INHERITED", "inherited"),
        ("LOCAL", "local"),
        ("PRIVATE", "private"),
    ],
};
const E_OWNERSHIP_ROOT_KIND: EnumSpec = EnumSpec {
    name: "OwnershipRootKind",
    doc: "How an ownership root participates in authored resource scope.",
    members: &[("RESOURCE", "resource"), ("GLOBAL", "global")],
};
const E_USAGE_KIND: EnumSpec = EnumSpec {
    name: "UsageKind",
    doc: "Why one indexed identity consumes a declaration.",
    members: &[
        ("RUNTIME", "runtime"),
        ("GENERATED", "generated"),
        ("DECLARATION_DEPENDENCY", "declaration_dependency"),
    ],
};
const E_GRANT_KIND: EnumSpec = EnumSpec {
    name: "GrantKind",
    doc: "Compiler relationships that grant additional public vocabulary.",
    members: &[
        ("EXPECTED_MODEL", "expected_model"),
        ("TESTED_MACRO", "tested_macro"),
    ],
};
const E_VISIBILITY_REASON: EnumSpec = EnumSpec {
    name: "VisibilityReason",
    doc: "Positive explanations emitted by the canonical resolver.",
    members: &[
        ("GLOBAL", "global"),
        ("INHERITED_ANCESTOR", "inherited_ancestor"),
        ("LOCAL_OWNER", "local_owner"),
        ("PRIVATE_OWNER", "private_owner"),
        ("EXPECTED_MODEL", "expected_model"),
        ("TESTED_MACRO", "tested_macro"),
    ],
};
const E_INACCESSIBLE_REASON: EnumSpec = EnumSpec {
    name: "InaccessibleReason",
    doc: "Stable explanations for declarations outside effective scope.",
    members: &[
        ("LOCAL_BOUNDARY", "local_boundary"),
        ("SIBLING_SCOPE", "sibling_scope"),
        ("DESCENDANT_SCOPE", "descendant_scope"),
        ("UNRELATED_SCOPE", "unrelated_scope"),
        ("PRIVATE_OWNER", "private_owner"),
        ("UNSUPPORTED_RESOURCE_KIND", "unsupported_resource_kind"),
    ],
};
const E_SCOPE_DIAGNOSTIC_SEVERITY: EnumSpec = EnumSpec {
    name: "ScopeDiagnosticSeverity",
    doc: "Severity of a stable scope diagnostic.",
    members: &[("ERROR", "error"), ("WARNING", "warning")],
};
const E_SCOPE_DIAGNOSTIC_CODE: EnumSpec = EnumSpec {
    name: "ScopeDiagnosticCode",
    doc: "Stable diagnostic identities shared by future scope consumers.",
    members: &[
        ("UNKNOWN_TARGET", "S001"),
        ("UNQUALIFIED_TARGET", "S002"),
        ("DUPLICATE_DECLARATION", "S003"),
        ("INVALID_DECLARATION_NAME", "S004"),
        ("RESERVED_DECLARATION_NAME", "S005"),
        ("INACCESSIBLE_DECLARATION", "S006"),
        ("LOCAL_NEEDED_BY_DESCENDANT", "S007"),
        ("OVER_BROAD_INHERITED", "S008"),
        ("REQUIRES_GLOBAL_PLACEMENT", "S009"),
        ("UNUSED_DECLARATION", "S010"),
        ("INVALID_PROSPECTIVE_PATH", "S011"),
        ("NESTED_DECLARATION_ROOT", "S012"),
        ("INCOMPLETE_USAGE", "S013"),
        ("INVALID_CURSOR", "S014"),
        ("MACRO_MODULE_IMPORT", "S015"),
        ("INVALID_MACRO_DEPENDENCY", "S016"),
        ("MACRO_DEPENDENCY_CYCLE", "S017"),
        ("DUPLICATE_RESOURCE", "S018"),
        ("RESOURCE_PARSE_ERROR", "S019"),
        ("DECLARATION_PARSE_ERROR", "S020"),
        ("MACRO_PARSE_ERROR", "S021"),
        ("RELATIONSHIP_PARSE_ERROR", "S022"),
        ("CONFIG_PARSE_ERROR", "S023"),
        ("OVER_BROAD_GLOBAL", "S024"),
    ],
};
const E_EVENT_EXPORT_SEVERITY: EnumSpec = EnumSpec {
    name: "EventExportSeverity",
    doc: "Severity used to filter exported lifecycle events.",
    members: &[
        ("DEBUG", "debug"),
        ("INFO", "info"),
        ("WARNING", "warning"),
        ("ERROR", "error"),
    ],
};
const E_WAREHOUSE_GROUP: EnumSpec = EnumSpec {
    name: "WarehouseGroup",
    doc: "Command group that selects a target's default warehouse.",
    members: &[("BUILD", "build"), ("QUERY", "query")],
};
const E_SOURCE_WRITE_STRATEGY: EnumSpec = EnumSpec {
    name: "SourceWriteStrategy",
    doc: "",
    members: &[
        ("APPEND", "append"),
        ("DELETE_INSERT", "delete_insert"),
        ("MERGE", "merge"),
        ("TABLE", "table"),
    ],
};
const E_FUTURE_CURSOR_ACTION: EnumSpec = EnumSpec {
    name: "FutureCursorAction",
    doc: "Response when an effective cursor lies beyond the future horizon.",
    members: &[("CAP", "cap"), ("ERROR", "error")],
};
const E_MICROBATCH_LIMIT_ACTION: EnumSpec = EnumSpec {
    name: "MicrobatchLimitAction",
    doc: "Response when one model plans more than the configured batch limit.",
    members: &[
        ("CAP_FROM_END", "cap_from_end"),
        ("CAP_FROM_START", "cap_from_start"),
        ("ERROR", "error"),
        ("WARN", "warn"),
    ],
};
const E_COLUMN_CONTRACT_MODE: EnumSpec = EnumSpec {
    name: "ColumnContractMode",
    doc: "Default contract behavior for model column declarations.",
    members: &[("IMPLICIT", "implicit"), ("EXPLICIT", "explicit")],
};
const E_SOURCE_FRESHNESS_STRATEGY: EnumSpec = EnumSpec {
    name: "SourceFreshnessStrategy",
    doc: "",
    members: &[("ADAPTER", "adapter"), ("COLUMN", "column"), ("SQL", "sql")],
};
const E_SOURCE_FRESHNESS_VALUE_KIND: EnumSpec = EnumSpec {
    name: "SourceFreshnessValueKind",
    doc: "",
    members: &[
        ("TIMESTAMP", "timestamp"),
        ("INTEGER", "integer"),
        ("STRING", "string"),
    ],
};
const E_TIME_TRAVEL_RETENTION_SOURCE: EnumSpec = EnumSpec {
    name: "TimeTravelRetentionSource",
    doc: "Authored layer that supplied the effective retention policy.",
    members: &[
        ("TARGET", "target"),
        ("MATERIALIZATION", "materialization"),
        ("MODEL", "model"),
    ],
};
const E_TABLE_TYPE: EnumSpec = EnumSpec {
    name: "TableType",
    doc: "Snowflake managed table type.",
    members: &[("PERMANENT", "permanent"), ("TRANSIENT", "transient")],
};
const E_TABLE_TYPE_SOURCE: EnumSpec = EnumSpec {
    name: "TableTypeSource",
    doc: "Authored layer that supplied the effective table type.",
    members: &[
        ("DEFAULT", "default"),
        ("TARGET", "target"),
        ("MATERIALIZATION", "materialization"),
        ("MODEL", "model"),
    ],
};
const E_TABLE_TYPE_DOWNGRADE_POLICY: EnumSpec = EnumSpec {
    name: "TableTypeDowngradePolicy",
    doc: "Permanent-to-transient conversion policy.",
    members: &[
        ("DENY", "deny"),
        ("REQUIRE_CONFIRMATION", "require_confirmation"),
        ("ALLOW", "allow"),
    ],
};
const E_MISSING_MIGRATION_ORIGIN_POLICY: EnumSpec = EnumSpec {
    name: "MissingMigrationOriginPolicy",
    doc: "Policy for a declared migrate_from whose origin does not exist in a target.",
    members: &[
        ("DENY", "deny"),
        ("REQUIRE_CONFIRMATION", "require_confirmation"),
        ("ALLOW", "allow"),
    ],
};
const E_RETENTION_DECREASE_POLICY: EnumSpec = EnumSpec {
    name: "RetentionDecreasePolicy",
    doc: "Policy for lowering live time-travel retention.",
    members: &[
        ("DENY", "deny"),
        ("REQUIRE_CONFIRMATION", "require_confirmation"),
        ("ALLOW", "allow"),
    ],
};
const E_SQL_VALUE_KIND: EnumSpec = EnumSpec {
    name: "SqlValueKind",
    doc: "Closed logical kinds accepted by the typed SQL value boundary.",
    members: &[
        ("STRING", "string"),
        ("INTEGER", "integer"),
        ("BOOLEAN", "boolean"),
        ("FLOAT", "float"),
        ("DECIMAL", "decimal"),
        ("NULL", "null"),
        ("LIST", "list"),
        ("SET", "set"),
        ("OBJECT", "object"),
    ],
};
const E_STATE_SQL_VALUE_TYPE: EnumSpec = EnumSpec {
    name: "StateSqlValueType",
    doc: "Closed physical value kinds used by warehouse state columns.",
    members: &[
        ("STRING", "string"),
        ("INTEGER", "integer"),
        ("BOOLEAN", "boolean"),
        ("TIMESTAMP", "timestamp"),
        ("TEXT_TIMESTAMP", "text_timestamp"),
        ("DATE", "date"),
        ("JSON", "json"),
    ],
};

/// Compiler, rule, lint and config string enums.
pub(crate) const COMPILER_ENUMS: &[EnumSpec] = &[
    E_CONTRACT_FINDING_KIND,
    E_COMPILER_STAGE,
    E_HOOK_READ_TYPE,
    E_LINT_SEVERITY,
    E_DIAGNOSTIC_PHASE,
    E_DIAGNOSTIC_SEVERITY,
    E_COLUMN_TRANSFORM_KIND,
    E_COLUMN_LINEAGE_CONFIDENCE,
    E_COLUMN_LINEAGE_MODE,
    E_POLYGLOT_ANALYSIS_DIALECT,
    E_MIGRATION_DISCOVERY,
    E_MIGRATION_COMPATIBILITY,
    E_OLD_NAME_VIEW_ACTION,
    E_SELECTOR_KIND,
    E_PYTHON_RUN_PHASE,
    E_PYTHON_IDENTITY_STATUS,
    E_COLLECTION_RENDERING,
    E_RESOURCE_KIND,
    E_DECLARATION_KIND,
    E_SCOPE_KIND,
    E_OWNERSHIP_ROOT_KIND,
    E_USAGE_KIND,
    E_GRANT_KIND,
    E_VISIBILITY_REASON,
    E_INACCESSIBLE_REASON,
    E_SCOPE_DIAGNOSTIC_SEVERITY,
    E_SCOPE_DIAGNOSTIC_CODE,
    E_EVENT_EXPORT_SEVERITY,
    E_WAREHOUSE_GROUP,
    E_SOURCE_WRITE_STRATEGY,
    E_FUTURE_CURSOR_ACTION,
    E_MICROBATCH_LIMIT_ACTION,
    E_COLUMN_CONTRACT_MODE,
    E_SOURCE_FRESHNESS_STRATEGY,
    E_SOURCE_FRESHNESS_VALUE_KIND,
    E_TIME_TRAVEL_RETENTION_SOURCE,
    E_TABLE_TYPE,
    E_TABLE_TYPE_SOURCE,
    E_TABLE_TYPE_DOWNGRADE_POLICY,
    E_MISSING_MIGRATION_ORIGIN_POLICY,
    E_RETENTION_DECREASE_POLICY,
    E_SQL_VALUE_KIND,
    E_STATE_SQL_VALUE_TYPE,
];
