//! Layouts of the compiler, rule, lint and config value records hosted natively.

use crate::bindings::_helpers::records::constants::{EXCEPTION_PARENT, VALUE_ERROR_PARENT};
use crate::bindings::_helpers::records::models::{
    ClassValue, EnumSpec, ErrorSpec, FieldDefault, FieldSpec, RecordSpec,
};

const R_NATIVE_MODEL_ANALYSIS_REQUEST: RecordSpec = RecordSpec {
    name: "NativeModelAnalysisRequest",
    doc: "The Python model analysis's arguments plus the facts dynamic pivot proofs need.",
    fields: &[
        FieldSpec::required("known_functions"),
        FieldSpec::required("known_types"),
        FieldSpec::required("model_inputs"),
        FieldSpec::required("column_nullability_by_table"),
        FieldSpec::required("column_types_by_table"),
        FieldSpec::required("inference_profile"),
        FieldSpec::required("allow_compact_analysis"),
        FieldSpec::required("rich_type_inference"),
        FieldSpec::required("analysis_cache"),
        FieldSpec::required("complete_binding_schemas"),
        FieldSpec::required("dynamic_families_by_table"),
    ],
};
const R_NATIVE_MODEL_ANALYSES: RecordSpec = RecordSpec {
    name: "NativeModelAnalyses",
    doc: "Each analysed model's position in the finished session that keeps its outcome.",
    fields: &[
        FieldSpec::required("positions"),
        FieldSpec::required("succeeded"),
        FieldSpec::required("session"),
    ],
};
const R_NATIVE_PIVOT_TABLES: RecordSpec = RecordSpec {
    name: "NativePivotTables",
    doc: "The relation facts Python's dynamic pivot proofs read, for proofs outside a session.",
    fields: &[
        FieldSpec::required("dialect"),
        FieldSpec::required("column_types_by_table"),
        FieldSpec::required("authoritative_column_types_by_table"),
        FieldSpec::required("column_nullability_by_table"),
        FieldSpec::required("dynamic_families_by_table"),
    ],
};
const R_NATIVE_COLUMN_QUERY: RecordSpec = RecordSpec {
    name: "NativeColumnQuery",
    doc: "One query outside the session whose output columns Python's analysis inferred.",
    fields: &[
        FieldSpec::required("sql"),
        FieldSpec::required("mode"),
        FieldSpec::new("placeholders", FieldDefault::None),
        FieldSpec::new("references", FieldDefault::EmptyTuple),
        FieldSpec::new("recover_cte_facts", FieldDefault::True),
    ],
};
const R_NATIVE_QUERY_COLUMNS: RecordSpec = RecordSpec {
    name: "NativeQueryColumns",
    doc: "One query's analysis: whether it succeeded, its columns and whether it projects a star.",
    fields: &[
        FieldSpec::required("succeeded"),
        FieldSpec::required("columns"),
        FieldSpec::required("has_star"),
    ],
};
const R_CONTRACT_FINDING: RecordSpec = RecordSpec {
    name: "ContractFinding",
    doc: "",
    fields: &[
        FieldSpec::required("resource_type"),
        FieldSpec::required("resource_name"),
        FieldSpec::required("kind"),
        FieldSpec::required("message"),
        FieldSpec::new("column_name", FieldDefault::None),
        FieldSpec::new("declared_type", FieldDefault::None),
        FieldSpec::new("physical_type", FieldDefault::None),
    ],
};
const R_CONTRACT_EVIDENCE: RecordSpec = RecordSpec {
    name: "ContractEvidence",
    doc: "",
    fields: &[
        FieldSpec::required("resource_type"),
        FieldSpec::required("resource_name"),
        FieldSpec::required("database"),
        FieldSpec::required("schema"),
        FieldSpec::required("relation"),
        FieldSpec::required("declared_columns"),
        FieldSpec::required("physical_columns"),
        FieldSpec::required("source_path"),
        FieldSpec::new("dynamic_columns", FieldDefault::EmptyTuple),
        FieldSpec::new("findings", FieldDefault::EmptyTuple),
    ],
};
const R_CONTRACT_ADOPTION_RESULT: RecordSpec = RecordSpec {
    name: "ContractAdoptionResult",
    doc: "",
    fields: &[
        FieldSpec::required("from_target"),
        FieldSpec::required("evidence"),
        FieldSpec::new("written_paths", FieldDefault::EmptyTuple),
    ],
};
const R_CONTRACT_VALIDATION_RESULT: RecordSpec = RecordSpec {
    name: "ContractValidationResult",
    doc: "Diagnostics emitted by model contract validation.",
    fields: &[FieldSpec::new("diagnostics", FieldDefault::EmptyTuple)],
};
const R_LINEAGE_GRAPH_VIEWS: RecordSpec = RecordSpec {
    name: "LineageGraphViews",
    doc: "A native project graph's lineage edges and selector indexes as Python dicts.",
    fields: &[
        FieldSpec::required("upstream_deps"),
        FieldSpec::required("downstream_deps"),
        FieldSpec::required("tag_index"),
        FieldSpec::required("path_index"),
        FieldSpec::required("all_keys"),
    ],
};
const R_ATTACHED_AUDIT_GATE_EDGE: RecordSpec = RecordSpec {
    name: "AttachedAuditGateEdge",
    doc: "One ordering edge: the gated node waits for a resource its attached audit reads.",
    fields: &[
        FieldSpec::required("audit_name"),
        FieldSpec::required("target"),
        FieldSpec::required("gated"),
        FieldSpec::required("read"),
    ],
};
const R_HOOK_READ_EDGE: RecordSpec = RecordSpec {
    name: "HookReadEdge",
    doc: "One ordering edge: a model waits for a resource one of its hooks reads.",
    fields: &[
        FieldSpec::required("hook_name"),
        FieldSpec::required("gated"),
        FieldSpec::required("read"),
        FieldSpec::new(
            "hook_type",
            FieldDefault::Member("sqlbuild._native", "HookReadType", "PYTHON"),
        ),
        FieldSpec::new("hook_path", FieldDefault::None),
    ],
};
const R_QUALIFIED_LINEAGE_COLUMN: RecordSpec = RecordSpec {
    name: "QualifiedLineageColumn",
    doc: "A resource-qualified column in the collapsed SQLBuild lineage graph.",
    fields: &[
        FieldSpec::required("resource_type"),
        FieldSpec::required("resource_name"),
        FieldSpec::required("column_name"),
    ],
};
const R_COLUMN_LINEAGE_SOURCE: RecordSpec = RecordSpec {
    name: "ColumnLineageSource",
    doc: "One upstream column dependency for an output column.",
    fields: &[
        FieldSpec::required("resource_type"),
        FieldSpec::required("resource_name"),
        FieldSpec::required("column_name"),
    ],
};
const R_COLUMN_LINEAGE_EDGE: RecordSpec = RecordSpec {
    name: "ColumnLineageEdge",
    doc: "One collapsed SQLBuild lineage graph edge.",
    fields: &[
        FieldSpec::required("source"),
        FieldSpec::required("target"),
        FieldSpec::new(
            "transform_kind",
            FieldDefault::Member(
                "sqlbuild.compiler.lineage.types",
                "ColumnTransformKind",
                "UNKNOWN",
            ),
        ),
        FieldSpec::new(
            "confidence",
            FieldDefault::Member(
                "sqlbuild.compiler.lineage.types",
                "ColumnLineageConfidence",
                "UNKNOWN",
            ),
        ),
    ],
};
const R_DIRECT_SEMANTIC_COLUMN_USE: RecordSpec = RecordSpec {
    name: "DirectSemanticColumnUse",
    doc: "One direct non-projection use of a resolved resource column.",
    fields: &[
        FieldSpec::required("consumer_model"),
        FieldSpec::required("context"),
        FieldSpec::required("expression_sql"),
        FieldSpec::required("source"),
        FieldSpec::new(
            "confidence",
            FieldDefault::Member(
                "sqlbuild.compiler.lineage.types",
                "ColumnLineageConfidence",
                "UNKNOWN",
            ),
        ),
        FieldSpec::new("line", FieldDefault::None),
        FieldSpec::new("column", FieldDefault::None),
    ],
};
const R_COLUMN_LINEAGE: RecordSpec = RecordSpec {
    name: "ColumnLineage",
    doc: "Lineage for one output column in one model.",
    fields: &[
        FieldSpec::required("output_column"),
        FieldSpec::required("transform_kind"),
        FieldSpec::required("expression_sql"),
        FieldSpec::required("upstream_columns"),
        FieldSpec::new(
            "nullability",
            FieldDefault::Member(
                "sqlbuild.compiler.lineage.types",
                "InferredNullability",
                "UNKNOWN",
            ),
        ),
        FieldSpec::new(
            "confidence",
            FieldDefault::Member(
                "sqlbuild.compiler.lineage.types",
                "ColumnLineageConfidence",
                "UNKNOWN",
            ),
        ),
    ],
};
const R_MODEL_COLUMN_LINEAGE: RecordSpec = RecordSpec {
    name: "ModelColumnLineage",
    doc: "Column lineage extracted for one compiled model.",
    fields: &[
        FieldSpec::required("model_name"),
        FieldSpec::required("columns"),
        FieldSpec::new("has_star", FieldDefault::False),
    ],
};
const R_REFACTOR_PROJECT: RecordSpec = RecordSpec {
    name: "RefactorProject",
    doc: "Compiler facts of one project, as the refactoring planner reads them.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("graph"),
        FieldSpec::required("discovered"),
    ],
};
const R_MANUAL_LOCATION: RecordSpec = RecordSpec {
    name: "ManualLocation",
    doc: "A location a refactoring cannot rewrite safely.",
    fields: &[
        FieldSpec::required("path"),
        FieldSpec::required("line"),
        FieldSpec::required("column"),
        FieldSpec::required("reason"),
    ],
};
const R_NATIVE_SQL_TEST_PLANNING_REQUEST: RecordSpec = RecordSpec {
    name: "NativeSqlTestPlanningRequest",
    doc: "Compiled models and tests to plan, with the adapter facts native planning cannot derive.",
    fields: &[
        FieldSpec::required("models"),
        FieldSpec::required("rendered_model_sql"),
        FieldSpec::required("functions"),
        FieldSpec::required("tests"),
        FieldSpec::required("rendered_test_overrides"),
        FieldSpec::required("sql_analysis_enabled"),
        FieldSpec::required("sql_analysis_dialect"),
        FieldSpec::required("set_difference_operator"),
        FieldSpec::required("requires_derived_table_aliases"),
        FieldSpec::required("lexical_syntax"),
        FieldSpec::required("render_sql"),
        FieldSpec::required("include_plan"),
    ],
};
const R_NATIVE_SQL_TEST_CHAIN_REQUEST: RecordSpec = RecordSpec {
    name: "NativeSqlTestChainRequest",
    doc: "Compiled models and the tests whose unmocked model chains to resolve.",
    fields: &[
        FieldSpec::required("models"),
        FieldSpec::required("tests"),
        FieldSpec::required("lexical_syntax"),
    ],
};
const R_NATIVE_SQL_TEST_FAILURE: RecordSpec = RecordSpec {
    name: "NativeSqlTestFailure",
    doc: "The error one test's assembly raises: its kind and message.",
    fields: &[FieldSpec::required("kind"), FieldSpec::required("message")],
};
const R_NATIVE_SQL_TEST_ASSEMBLY: RecordSpec = RecordSpec {
    name: "NativeSqlTestAssembly",
    doc: "One natively assembled test, its keyed diagnostics, and the error its assembly raises.",
    fields: &[
        FieldSpec::required("test"),
        FieldSpec::required("diagnostics"),
        FieldSpec::new("failure", FieldDefault::None),
    ],
};
const R_HEADER_SPAN: RecordSpec = RecordSpec {
    name: "HeaderSpan",
    doc: "A located DSL header region inside one file.",
    fields: &[
        FieldSpec::required("kind"),
        FieldSpec::required("start"),
        FieldSpec::required("end"),
    ],
};
const R_LINT_FILE_ROLE: RecordSpec = RecordSpec {
    name: "LintFileRole",
    doc: "Path-derived classification of one lint input, derived once per file.",
    fields: &[
        FieldSpec::new("declaration_kind", FieldDefault::None),
        FieldSpec::new("in_project", FieldDefault::False),
        FieldSpec::new("in_hook_directory", FieldDefault::False),
    ],
};
const R_INTERPOLATION_SITE: RecordSpec = RecordSpec {
    name: "InterpolationSite",
    doc: "One sqlbuild interpolation occurrence replaced by a unique sentinel.",
    fields: &[
        FieldSpec::required("sentinel"),
        FieldSpec::required("neutralized_start"),
        FieldSpec::required("neutralized_end"),
        FieldSpec::required("original_start"),
        FieldSpec::required("original_end"),
        FieldSpec::required("original_text"),
    ],
};
const R_LINT_BODY: RecordSpec = RecordSpec {
    name: "LintBody",
    doc: "One authored SQL body prepared for linting, with its expansion spans.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("body_start"),
        FieldSpec::required("body_end"),
        FieldSpec::required("lint_text"),
        FieldSpec::required("passes"),
        FieldSpec::new("external_identifiers", FieldDefault::EmptyTuple),
        FieldSpec::new("dependency_identifiers", FieldDefault::EmptyTuple),
        FieldSpec::new("externally_referenced_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("allows_ceremonial_select", FieldDefault::False),
        FieldSpec::new("allows_dynamic_output_star", FieldDefault::False),
        FieldSpec::new("allows_empty_fixture_star", FieldDefault::False),
        FieldSpec::new("dependency_relations", FieldDefault::EmptyTuple),
    ],
};
const R_PENDING_LINT_BODY: RecordSpec = RecordSpec {
    name: "PendingLintBody",
    doc: "One expanded authored body awaiting its native lexical preparation.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("body_start"),
        FieldSpec::required("body_end"),
        FieldSpec::required("expansion_input"),
        FieldSpec::required("expanded"),
        FieldSpec::required("expansion_passes"),
        FieldSpec::required("pre_expansion_sites"),
        FieldSpec::required("external_identifiers"),
        FieldSpec::required("allows_ceremonial_select"),
        FieldSpec::required("allows_dynamic_output_star"),
        FieldSpec::required("allows_empty_fixture_star"),
        FieldSpec::required("request"),
    ],
};
const R_EXPANDED_LINT_FILE: RecordSpec = RecordSpec {
    name: "ExpandedLintFile",
    doc: "The expanded bodies of one file, up to the first body that could not be expanded.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("bodies"),
        FieldSpec::required("failure"),
    ],
};
const R_PREPARED_LINT_FILES: RecordSpec = RecordSpec {
    name: "PreparedLintFiles",
    doc: "Lint bodies of every expandable file, and why the skipped files could not expand.",
    fields: &[
        FieldSpec::required("bodies"),
        FieldSpec::required("unexpandable"),
    ],
};
const R_LINT_EDIT: RecordSpec = RecordSpec {
    name: "LintEdit",
    doc: "One deterministic authored-source edit proposed by a lint rule.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("code"),
        FieldSpec::required("start"),
        FieldSpec::required("end"),
        FieldSpec::required("replacement"),
    ],
};
const R_LINT_VIOLATION: RecordSpec = RecordSpec {
    name: "LintViolation",
    doc: "One lint diagnostic reported against an authored file.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("line"),
        FieldSpec::required("column"),
        FieldSpec::required("code"),
        FieldSpec::required("message"),
        FieldSpec::required("severity"),
        FieldSpec::required("engine"),
        FieldSpec::new("end_line", FieldDefault::None),
        FieldSpec::new("end_column", FieldDefault::None),
        FieldSpec::new("remediation", FieldDefault::None),
        FieldSpec::new("fix", FieldDefault::None),
        FieldSpec::new("fix_unavailable_reason", FieldDefault::None),
    ],
};
const R_RULE_FIX_RESULT: RecordSpec = RecordSpec {
    name: "RuleFixResult",
    doc: "One applied, refused, or unavailable semantic Rule fix.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("code"),
        FieldSpec::required("line"),
        FieldSpec::required("status"),
        FieldSpec::required("reason"),
    ],
};
const R_LINT_CONFIG: RecordSpec = RecordSpec {
    name: "LintConfig",
    doc: "Resolved lint and format configuration for one run.",
    fields: &[
        FieldSpec::new("native_enabled", FieldDefault::True),
        FieldSpec::new("max_description_lines", FieldDefault::Int(10)),
        FieldSpec::new("line_width", FieldDefault::Int(100)),
        FieldSpec::new("dialect", FieldDefault::Text("generic")),
        FieldSpec::new("enabled_native_rules", FieldDefault::None),
        FieldSpec::new("ignored_native_rules", FieldDefault::EmptyTuple),
        FieldSpec::new("header_rules_enabled", FieldDefault::True),
        FieldSpec::new("max_literal_length", FieldDefault::Int(100)),
        FieldSpec::new("max_ranking_order_by", FieldDefault::Int(5)),
        FieldSpec::new("allow_suppressions", FieldDefault::True),
        FieldSpec {
            name: "relation_keys",
            default: FieldDefault::EmptyDict,
            compared: false,
        },
    ],
};
const R_LINT_RUN_RESULT: RecordSpec = RecordSpec {
    name: "LintRunResult",
    doc: "Aggregated outcome of one lint or format run.",
    fields: &[
        FieldSpec::required("files_checked"),
        FieldSpec::required("violations"),
        FieldSpec::required("formatted_files"),
        FieldSpec {
            name: "source_texts",
            default: FieldDefault::EmptyDict,
            compared: false,
        },
        FieldSpec::new("unexpandable", FieldDefault::EmptyDict),
    ],
};
const R_COMPILE_FACTS: RecordSpec = RecordSpec {
    name: "CompileFacts",
    doc: "Per-model outputs and per-owner diagnostics of one compilation.",
    fields: &[
        FieldSpec::required("models"),
        FieldSpec::required("model_paths"),
        FieldSpec::required("diagnostics"),
    ],
};
const R_FIX_VERDICT: RecordSpec = RecordSpec {
    name: "FixVerdict",
    doc: "Edited files that fail verification, and whether any change is unattributable.",
    fields: &[
        FieldSpec::required("failing"),
        FieldSpec::required("unattributed"),
    ],
};
const R_DISPLAY_OPTIONS: RecordSpec = RecordSpec {
    name: "DisplayOptions",
    doc: "Options controlling bounded human output.",
    fields: &[
        FieldSpec::new("max_entries_per_section", FieldDefault::Int(20)),
        FieldSpec::new("overflow_flag", FieldDefault::Text("--verbose")),
    ],
};
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

/// Compiler, rule, lint and config value records.
pub(crate) const COMPILER_RECORDS: &[RecordSpec] = &[
    R_NATIVE_MODEL_ANALYSIS_REQUEST,
    R_NATIVE_MODEL_ANALYSES,
    R_NATIVE_PIVOT_TABLES,
    R_NATIVE_COLUMN_QUERY,
    R_NATIVE_QUERY_COLUMNS,
    R_CONTRACT_FINDING,
    R_CONTRACT_EVIDENCE,
    R_CONTRACT_ADOPTION_RESULT,
    R_CONTRACT_VALIDATION_RESULT,
    R_LINEAGE_GRAPH_VIEWS,
    R_ATTACHED_AUDIT_GATE_EDGE,
    R_HOOK_READ_EDGE,
    R_QUALIFIED_LINEAGE_COLUMN,
    R_COLUMN_LINEAGE_SOURCE,
    R_COLUMN_LINEAGE_EDGE,
    R_DIRECT_SEMANTIC_COLUMN_USE,
    R_COLUMN_LINEAGE,
    R_MODEL_COLUMN_LINEAGE,
    R_REFACTOR_PROJECT,
    R_MANUAL_LOCATION,
    R_NATIVE_SQL_TEST_PLANNING_REQUEST,
    R_NATIVE_SQL_TEST_CHAIN_REQUEST,
    R_NATIVE_SQL_TEST_FAILURE,
    R_NATIVE_SQL_TEST_ASSEMBLY,
    R_HEADER_SPAN,
    R_LINT_FILE_ROLE,
    R_INTERPOLATION_SITE,
    R_LINT_BODY,
    R_PENDING_LINT_BODY,
    R_EXPANDED_LINT_FILE,
    R_PREPARED_LINT_FILES,
    R_LINT_EDIT,
    R_LINT_VIOLATION,
    R_RULE_FIX_RESULT,
    R_LINT_CONFIG,
    R_LINT_RUN_RESULT,
    R_COMPILE_FACTS,
    R_FIX_VERDICT,
    R_DISPLAY_OPTIONS,
];
/// Compiler, rule, lint and config string enums.
pub(crate) const COMPILER_ENUMS: &[EnumSpec] = &[
    E_CONTRACT_FINDING_KIND,
    E_COMPILER_STAGE,
    E_HOOK_READ_TYPE,
    E_LINT_SEVERITY,
];
/// Compiler, rule, lint and config expected-error classes, each after its parent.
pub(crate) const COMPILER_ERRORS: &[ErrorSpec] = &[
    ErrorSpec {
        name: "DiscoveryError",
        parent: VALUE_ERROR_PARENT,
        doc: "Base error for expected discovery failures.",
        class_attributes: &[("code", ClassValue::Text("D000"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ProjectConfigError",
        parent: "DiscoveryError",
        doc: "Raised when shared or local project config files are invalid.",
        class_attributes: &[("code", ClassValue::Text("D001"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ModelSqlParseError",
        parent: "DiscoveryError",
        doc: "Raised when an authored SQL model file has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D002"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SqlTestParseError",
        parent: "DiscoveryError",
        doc: "Raised when an authored SQL-native test file has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D003"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SqlAuditParseError",
        parent: "DiscoveryError",
        doc: "Raised when an authored SQL audit file has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D004"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SchemaParseError",
        parent: "DiscoveryError",
        doc: "Raised when a schema.yml file has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D005"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SourceParseError",
        parent: "DiscoveryError",
        doc: "Raised when a sources/*.yml file has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D006"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "DiscoveryConflictError",
        parent: "DiscoveryError",
        doc: "Raised when discovered project inputs conflict across files.",
        class_attributes: &[("code", ClassValue::Text("D007"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SeedDiscoveryError",
        parent: "DiscoveryError",
        doc: "Raised when declared seed metadata does not match local seed files.",
        class_attributes: &[("code", ClassValue::Text("D008"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SqlScenarioParseError",
        parent: "DiscoveryError",
        doc: "Raised when an authored SQL scenario file has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D009"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "PythonNodeDiscoveryError",
        parent: "DiscoveryError",
        doc: "Raised when project Python nodes cannot be discovered.",
        class_attributes: &[("code", ClassValue::Text("D011"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ProviderDiscoveryError",
        parent: "DiscoveryError",
        doc: "Raised when project providers cannot be discovered.",
        class_attributes: &[("code", ClassValue::Text("D012"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "DeclarationParseError",
        parent: "DiscoveryError",
        doc: "Raised when an authored public SQL declaration is invalid.",
        class_attributes: &[("code", ClassValue::Text("D013"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SqlHookParseError",
        parent: "DiscoveryError",
        doc: "Raised when an authored SQL hook resource has an invalid shape.",
        class_attributes: &[("code", ClassValue::Text("D014"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "EventExporterDiscoveryError",
        parent: "DiscoveryError",
        doc: "Raised when project lifecycle event exporters are invalid.",
        class_attributes: &[("code", ClassValue::Text("D015"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ProjectPythonPathError",
        parent: "DiscoveryError",
        doc: "Raised when project-owned Python lives outside a supported extension root.",
        class_attributes: &[("code", ClassValue::Text("D016"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ProjectPathError",
        parent: "DiscoveryError",
        doc: "Raised when an authored project path cannot be read as valid UTF-8.",
        class_attributes: &[("code", ClassValue::Text("D016"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ResourceIdentityError",
        parent: "DiscoveryError",
        doc: "Raised when an authored resource identity is not canonical snake_case.",
        class_attributes: &[("code", ClassValue::Text("D016"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "MeasurementAuditError",
        parent: "builtins.ValueError",
        doc: "Raised when a measurement audit contract or value is invalid.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ContractAdoptionError",
        parent: "builtins.RuntimeError",
        doc: "Raised when safe contract source editing cannot continue.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "FingerprintInputError",
        parent: VALUE_ERROR_PARENT,
        doc: "Raised when fingerprint storage inputs or rows are invalid.",
        class_attributes: &[("code", ClassValue::Text("F000"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "QueryFingerprintError",
        parent: "builtins.ValueError",
        doc: "Raised when SQL cannot be tokenized into a change fingerprint.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "NativeStageMismatchError",
        parent: "builtins.RuntimeError",
        doc: "Raised when native state the compiler replays is inconsistent with its inputs.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "UnknownLineageDialectError",
        parent: "builtins.ValueError",
        doc: "Raised, as Python's parser raised `ValueError`, for a dialect Polyglot does not know.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "RefactorValueError",
        parent: "builtins.ValueError",
        doc: "An unhandled value failure the Python planner also leaves to the caller.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "RefactorIOError",
        parent: "builtins.OSError",
        doc: "A file read or write failure the Python planner also leaves to the caller.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ScopeError",
        parent: VALUE_ERROR_PARENT,
        doc: "Base error for invalid scope-domain input.",
        class_attributes: &[("code", ClassValue::Text("S000"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "InvalidScopePathError",
        parent: "ScopeError",
        doc: "Raised when a project-relative scope path is invalid.",
        class_attributes: &[("code", ClassValue::Text("S011"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "InvalidQualifiedIdentityError",
        parent: "ScopeError",
        doc: "Raised when a qualified scope identity cannot be parsed.",
        class_attributes: &[("code", ClassValue::Text("S002"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "UnindexableScopeError",
        parent: "ScopeError",
        doc: "Raised when the native scope index cannot place a discovered path or resource kind.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ScopeValidationError",
        parent: "ScopeError",
        doc: "Aggregate error raised only when strict scope validation is requested.",
        class_attributes: &[],
        required: &["diagnostics"],
        fixed: &[],
    },
    ErrorSpec {
        name: "UnsupportedLexicalSyntaxError",
        parent: "builtins.ValueError",
        doc: "Raised when an adapter declares lexical rules the native SQL scanners do not support.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "LintError",
        parent: EXCEPTION_PARENT,
        doc: "A lint or format run could not proceed.",
        class_attributes: &[("code", ClassValue::Text("L001"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "NativeLintError",
        parent: "LintError",
        doc: "The SQLBuild-owned native lint engine rejected a request or response.",
        class_attributes: &[("code", ClassValue::Text("L003"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ProjectCompileError",
        parent: "LintError",
        doc: "The project could not be compiled, so its SQL cannot be linted.",
        class_attributes: &[("code", ClassValue::Text("L005"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "LintStoppedError",
        parent: "builtins.Exception",
        doc: "A speculative lint run was stopped because its result is no longer needed.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "SpecConfigError",
        parent: "builtins.RuntimeError",
        doc: "Raised when project specification configuration is invalid.",
        class_attributes: &[],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "ConfigValueTypeError",
        parent: VALUE_ERROR_PARENT,
        doc: "Raised when an authored config value has the wrong runtime type.",
        class_attributes: &[],
        required: &["key", "expected", "actual_type"],
        fixed: &[],
    },
];
