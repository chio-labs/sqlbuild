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
            FieldDefault::Member("sqlbuild._native", "ColumnTransformKind", "UNKNOWN"),
        ),
        FieldSpec::new(
            "confidence",
            FieldDefault::Member("sqlbuild._native", "ColumnLineageConfidence", "UNKNOWN"),
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
            FieldDefault::Member("sqlbuild._native", "ColumnLineageConfidence", "UNKNOWN"),
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
            FieldDefault::Member("sqlbuild._native", "ColumnLineageConfidence", "UNKNOWN"),
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
const R_COMPILE_PIPELINE_OPTIONS: RecordSpec = RecordSpec {
    name: "CompilePipelineOptions",
    doc: "Selection, deferral, and planning options for one compile pipeline run.",
    fields: &[
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("defer_to", FieldDefault::None),
        FieldSpec::new("defer_sources_to", FieldDefault::None),
        FieldSpec::new("source_deferral_enabled", FieldDefault::True),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cursor_overrides", FieldDefault::None),
        FieldSpec::new("full_refresh", FieldDefault::False),
        FieldSpec::new("auto_load_sources", FieldDefault::False),
        FieldSpec::new("reload_sources", FieldDefault::False),
        FieldSpec::new("connection_config", FieldDefault::None),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("external_sql_reference_resolver", FieldDefault::None),
        FieldSpec::new("resolve_python_run_selectors", FieldDefault::False),
        FieldSpec::new("no_cache", FieldDefault::False),
        FieldSpec::new("max_microbatches", FieldDefault::None),
        FieldSpec::new("selection_diagnostics", FieldDefault::False),
        FieldSpec::new("plan_sql_tests", FieldDefault::True),
        FieldSpec::new("record_migration_fingerprints", FieldDefault::True),
        FieldSpec::new("accepts_unit_test_selectors", FieldDefault::False),
        FieldSpec::new(
            "sql_test_selection",
            FieldDefault::Call("sqlbuild._native", "SqlTestSelection"),
        ),
    ],
};
const R_PYTHON_PLAN_ENTRY: RecordSpec = RecordSpec {
    name: "PythonPlanEntry",
    doc: "Display-ready Python node entry for plan output.",
    fields: &[
        FieldSpec::required("name"),
        FieldSpec::required("kind"),
        FieldSpec::required("phase"),
        FieldSpec::new(
            "identity_status",
            FieldDefault::Member("sqlbuild._native", "PythonIdentityStatus", "UNKNOWN"),
        ),
        FieldSpec::new("current_definition_json", FieldDefault::None),
        FieldSpec::new("previous_definition_json", FieldDefault::None),
        FieldSpec::new("current_metadata_json", FieldDefault::None),
        FieldSpec::new("previous_metadata_json", FieldDefault::None),
        FieldSpec::new("provider_usages", FieldDefault::EmptyTuple),
    ],
};
const R_PYTHON_RUN_PLAN_OUTPUTS: RecordSpec = RecordSpec {
    name: "PythonRunPlanOutputs",
    doc: "Plan output and Python entries after python-aware run selection.",
    fields: &[
        FieldSpec::required("plan_output"),
        FieldSpec::required("python_plan_entries"),
        FieldSpec::required("selected_python_node_names"),
    ],
};
const R_COMPILED_PROJECT_PHASE_RESULT: RecordSpec = RecordSpec {
    name: "CompiledProjectPhaseResult",
    doc: "Canonical project compilation output before command-specific planning.",
    fields: &[
        FieldSpec::required("project"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("compile_seconds"),
    ],
};
const R_STATIC_COMMAND_CONTEXT: RecordSpec = RecordSpec {
    name: "StaticCommandContext",
    doc: "Shared compile, selection, and relation phases for focused commands.",
    fields: &[
        FieldSpec::required("project"),
        FieldSpec::required("scope"),
        FieldSpec::required("relations"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("compile_seconds"),
    ],
};
const R_CLONE_PIPELINE_OPTIONS: RecordSpec = RecordSpec {
    name: "ClonePipelineOptions",
    doc: "Compilation and selection options for one clone pipeline.",
    fields: &[
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("no_cache", FieldDefault::False),
    ],
};
const R_CLONE_PIPELINE_CONNECTION: RecordSpec = RecordSpec {
    name: "ClonePipelineConnection",
    doc: "Resolved destination connection used throughout clone compilation and planning.",
    fields: &[FieldSpec::required("config"), FieldSpec::required("handle")],
};
const R_CLONE_PIPELINE_RESULT: RecordSpec = RecordSpec {
    name: "ClonePipelineResult",
    doc: "Prepared clone inputs for origin and destination target environments.",
    fields: &[
        FieldSpec::required("origin_project"),
        FieldSpec::required("destination_project"),
        FieldSpec::required("clone_plan"),
        FieldSpec::new("destination_source_entries", FieldDefault::EmptyTuple),
        FieldSpec::new("destination_model_entries", FieldDefault::EmptyTuple),
        FieldSpec::new("destination_seed_entries", FieldDefault::EmptyTuple),
        FieldSpec::new("destination_function_entries", FieldDefault::EmptyTuple),
        FieldSpec::new("origin_model_entries", FieldDefault::EmptyTuple),
        FieldSpec::new("origin_seed_entries", FieldDefault::EmptyTuple),
        FieldSpec::new("origin_source_entries", FieldDefault::EmptyTuple),
    ],
};
const R_PARSED_SELECTOR: RecordSpec = RecordSpec {
    name: "ParsedSelector",
    doc: "One parsed selector token before graph resolution.",
    fields: &[
        FieldSpec::required("kind"),
        FieldSpec::required("value"),
        FieldSpec::new("upstream", FieldDefault::False),
        FieldSpec::new("downstream", FieldDefault::False),
    ],
};
const R_PATH_SELECTOR: RecordSpec = RecordSpec {
    name: "PathSelector",
    doc: "A directed path selector between two model names with optional endpoint expansion.",
    fields: &[
        FieldSpec::required("start_name"),
        FieldSpec::required("end_name"),
        FieldSpec::new("upstream", FieldDefault::False),
        FieldSpec::new("downstream", FieldDefault::False),
    ],
};
const R_SQL_TEST_SELECTION: RecordSpec = RecordSpec {
    name: "SqlTestSelection",
    doc: "Unit tests selected or excluded by name, beside the tests of the selected resources.",
    fields: &[
        FieldSpec::new("names", FieldDefault::EmptyFrozenset),
        FieldSpec::new("excluded_names", FieldDefault::EmptyFrozenset),
        FieldSpec::new("models_selected", FieldDefault::True),
    ],
};
const R_PLANNER_SCOPE: RecordSpec = RecordSpec {
    name: "PlannerScope",
    doc: "Resolved graph scope for one planner invocation.",
    fields: &[
        FieldSpec::required("upstream_deps"),
        FieldSpec::required("downstream_deps"),
        FieldSpec::required("all_keys"),
        FieldSpec::required("models_by_name"),
        FieldSpec::required("selected_keys"),
        FieldSpec::required("execution_order"),
        FieldSpec::new("user_selected_keys", FieldDefault::EmptyFrozenset),
        FieldSpec::new("python_read_source_names", FieldDefault::EmptyFrozenset),
        FieldSpec::new(
            "sql_test_selection",
            FieldDefault::Call("sqlbuild._native", "SqlTestSelection"),
        ),
    ],
};
const R_PLANNER_RELATIONS_CONTEXT: RecordSpec = RecordSpec {
    name: "PlannerRelationsContext",
    doc: "Resolved relation and source inputs for plan entry construction.",
    fields: &[
        FieldSpec::required("model_locations"),
        FieldSpec::required("seed_locations"),
        FieldSpec::required("function_locations"),
        FieldSpec::required("source_map"),
        FieldSpec::required("source_read_map"),
        FieldSpec::required("python_source_read_map"),
        FieldSpec::required("source_warehouse_columns"),
        FieldSpec::required("star_exclude_keyword"),
        FieldSpec::new("listed_source_names", FieldDefault::EmptyFrozenset),
    ],
};
const R_SQL_TEST_ASSERTION_STEP: RecordSpec = RecordSpec {
    name: "SqlTestAssertionStep",
    doc: "One zero-row assertion step in a SQL-native unit test.",
    fields: &[
        FieldSpec::required("name"),
        FieldSpec::required("resolved_sql"),
        FieldSpec::new("lifted_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("comparison_body_sql", FieldDefault::None),
    ],
};
const R_PLANNER_SELECTION: RecordSpec = RecordSpec {
    name: "PlannerSelection",
    doc: "User-facing selection inputs for one planner invocation.",
    fields: &[
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("selected_keys", FieldDefault::None),
        FieldSpec::new("python_read_source_names", FieldDefault::EmptyFrozenset),
        FieldSpec::new(
            "sql_test_selection",
            FieldDefault::Call("sqlbuild._native", "SqlTestSelection"),
        ),
    ],
};
const R_PLANNER_OVERRIDES: RecordSpec = RecordSpec {
    name: "PlannerOverrides",
    doc: "Explicit user overrides that force or bound planner decisions.",
    fields: &[
        FieldSpec::new("cursor_overrides", FieldDefault::None),
        FieldSpec::new("full_refresh", FieldDefault::False),
        FieldSpec::new("reload_sources", FieldDefault::False),
        FieldSpec::new("forced_stale_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("external_blocked_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("max_microbatches", FieldDefault::None),
    ],
};
const R_DEFERRAL_INPUTS: RecordSpec = RecordSpec {
    name: "DeferralInputs",
    doc: "Deferred relation and source-deferral inputs for planning.",
    fields: &[
        FieldSpec::new("deferred_locations", FieldDefault::None),
        FieldSpec::new("deferred_relations", FieldDefault::None),
        FieldSpec::new("defer_sources_to", FieldDefault::None),
        FieldSpec::new("source_deferral_enabled", FieldDefault::True),
    ],
};
const R_PLANNER_POLICIES: RecordSpec = RecordSpec {
    name: "PlannerPolicies",
    doc: "Behavior policies selected by the caller for one planner invocation.",
    fields: &[
        FieldSpec::new("auto_load_sources", FieldDefault::False),
        FieldSpec::new("selection_diagnostics", FieldDefault::False),
        FieldSpec::new("plan_sql_tests", FieldDefault::True),
        FieldSpec::new("record_migration_fingerprints", FieldDefault::True),
    ],
};
const R_DISCOVERED_PYTHON_LOADER_METADATA: RecordSpec = RecordSpec {
    name: "DiscoveredPythonLoaderMetadata",
    doc: "Loader-specific metadata carried by an internal Python loader node.",
    fields: &[
        FieldSpec::new("destination", FieldDefault::None),
        FieldSpec::new("write_strategy", FieldDefault::None),
        FieldSpec::new("cursor_column", FieldDefault::None),
        FieldSpec::new("unique_key", FieldDefault::EmptyTuple),
        FieldSpec::new("columns", FieldDefault::EmptyTuple),
        FieldSpec::new("contract", FieldDefault::None),
        FieldSpec::new(
            "connection_mode",
            FieldDefault::Member(
                "sqlbuild.compiler.discovery.types",
                "LoaderConnectionMode",
                "SQLBUILD",
            ),
        ),
    ],
};
const R_DISCOVERED_PYTHON_TASK_METADATA: RecordSpec = RecordSpec {
    name: "DiscoveredPythonTaskMetadata",
    doc: "Task-specific metadata carried by an internal Python task node.",
    fields: &[FieldSpec::new("retry", FieldDefault::None)],
};
const R_DISCOVERED_PYTHON_ASSET_METADATA: RecordSpec = RecordSpec {
    name: "DiscoveredPythonAssetMetadata",
    doc: "Asset-specific metadata carried by an internal Python asset node.",
    fields: &[
        FieldSpec::new("columns", FieldDefault::EmptyTuple),
        FieldSpec::new("column_lineage", FieldDefault::None),
        FieldSpec::new("retry", FieldDefault::None),
    ],
};
const R_DISCOVERED_PYTHON_CHECK_METADATA: RecordSpec = RecordSpec {
    name: "DiscoveredPythonCheckMetadata",
    doc: "Check-specific metadata carried by an internal Python check node.",
    fields: &[FieldSpec::new(
        "severity",
        FieldDefault::Member(
            "sqlbuild.python_nodes.types",
            "PythonCheckSeverity",
            "ERROR",
        ),
    )],
};
const R_PYTHON_NODE_DEPENDENCY_EDGE: RecordSpec = RecordSpec {
    name: "PythonNodeDependencyEdge",
    doc: "Internal dependency edge between two discovered Python nodes.",
    fields: &[
        FieldSpec::required("upstream_name"),
        FieldSpec::required("downstream_name"),
    ],
};
const R_PYTHON_SQL_RUN_SELECTION: RecordSpec = RecordSpec {
    name: "PythonSqlRunSelection",
    doc: "Unified run-command selection excluding Python checks.",
    fields: &[
        FieldSpec::required("sql_keys"),
        FieldSpec::required("python_node_names"),
    ],
};
const R_LITERAL_SQL_RELATION: RecordSpec = RecordSpec {
    name: "LiteralSqlRelation",
    doc: "A relation named in literal SQL in Python code that matched no project relation.",
    fields: &[
        FieldSpec::required("owner_label"),
        FieldSpec::required("owner_kind"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("line"),
        FieldSpec::required("method"),
        FieldSpec::required("relation"),
    ],
};
const R_DIRECT_SOURCE_FRESHNESS_PLANNING_RESULT: RecordSpec = RecordSpec {
    name: "DirectSourceFreshnessPlanningResult",
    doc: "Direct planning-time source freshness observations and comparisons.",
    fields: &[
        FieldSpec::new("observed_records", FieldDefault::EmptyTuple),
        FieldSpec::new("previous_records", FieldDefault::EmptyTuple),
        FieldSpec::new("changed_identities", FieldDefault::EmptyFrozenset),
        FieldSpec::new("unchanged_identities", FieldDefault::EmptyFrozenset),
        FieldSpec::new("unknown_source_names", FieldDefault::EmptyTuple),
        FieldSpec::new("unknown_sources", FieldDefault::EmptyDict),
        FieldSpec::new("age_statuses", FieldDefault::EmptyDict),
        FieldSpec::new("propagation", FieldDefault::None),
    ],
};
const R_SQL_BINDING_DIAGNOSTIC: RecordSpec = RecordSpec {
    name: "SqlBindingDiagnostic",
    doc: "One native binding error or non-blocking runtime-conversion warning.",
    fields: &[
        FieldSpec::required("code"),
        FieldSpec::required("message"),
        FieldSpec::new("line", FieldDefault::None),
        FieldSpec::new("column", FieldDefault::None),
        FieldSpec::new("start", FieldDefault::None),
        FieldSpec::new("end", FieldDefault::None),
        FieldSpec::new("severity", FieldDefault::Text("error")),
    ],
};
const R_SQL_BINDING_RESULT: RecordSpec = RecordSpec {
    name: "SqlBindingResult",
    doc: "Stable result of schema-aware semantic SQL validation.",
    fields: &[FieldSpec::new("diagnostics", FieldDefault::EmptyTuple)],
};
const R_SQL_SCHEMA_VALIDATION_REQUEST: RecordSpec = RecordSpec {
    name: "SqlSchemaValidationRequest",
    doc: "One expanded SQL query and its complete relation schemas.",
    fields: &[
        FieldSpec::required("sql"),
        FieldSpec::required("dialect"),
        FieldSpec::required("schema"),
        FieldSpec::new("known_functions", FieldDefault::EmptyTuple),
        FieldSpec::new("known_types", FieldDefault::EmptyTuple),
        FieldSpec::new("quoted_identifiers_ignore_case", FieldDefault::False),
        FieldSpec {
            name: "catalog",
            default: FieldDefault::None,
            compared: false,
        },
    ],
};
const R_DBT_CLI_OPTIONS: RecordSpec = RecordSpec {
    name: "DbtCliOptions",
    doc: "Resolved dbt CLI options shared by dbt commands.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("profiles_dir", FieldDefault::None),
        FieldSpec::new("target", FieldDefault::None),
        FieldSpec::new("target_path", FieldDefault::None),
        FieldSpec::new("vars", FieldDefault::None),
        FieldSpec::new("state", FieldDefault::None),
        FieldSpec::new("defer", FieldDefault::False),
    ],
};
const R_NORMALIZED_DBT_PROFILE_CONNECTION: RecordSpec = RecordSpec {
    name: "NormalizedDbtProfileConnection",
    doc: "Rendered dbt profile output normalized for SQLBuild.",
    fields: &[
        FieldSpec::required("adapter"),
        FieldSpec::required("connection"),
        FieldSpec::new("target_schema", FieldDefault::None),
        FieldSpec::new("target_database", FieldDefault::None),
        FieldSpec::new("warnings", FieldDefault::EmptyTuple),
    ],
};
const R_DBT_INIT_PROGRESS_CALLBACKS: RecordSpec = RecordSpec {
    name: "DbtInitProgressCallbacks",
    doc: "Optional progress hooks for `sqb dbt init` phases.",
    fields: &[
        FieldSpec::new("start", FieldDefault::None),
        FieldSpec::new("complete", FieldDefault::None),
    ],
};
const R_DBT_INIT_REQUEST: RecordSpec = RecordSpec {
    name: "DbtInitRequest",
    doc: "Request to initialize a SQLBuild project from a dbt project.",
    fields: &[
        FieldSpec::required("cwd"),
        FieldSpec::required("dbt_project_dir"),
        FieldSpec::required("profiles_dir"),
        FieldSpec::required("profile_name"),
        FieldSpec::required("target_name"),
        FieldSpec::required("sqb_output_dir"),
        FieldSpec::new("dry_run", FieldDefault::False),
        FieldSpec::new("overwrite", FieldDefault::False),
        FieldSpec::new("skip_dbt_debug", FieldDefault::False),
        FieldSpec::new(
            "progress_callbacks",
            FieldDefault::Call("sqlbuild._native", "DbtInitProgressCallbacks"),
        ),
    ],
};
const R_DBT_INIT_RESULT: RecordSpec = RecordSpec {
    name: "DbtInitResult",
    doc: "Result from `sqb dbt init`.",
    fields: &[
        FieldSpec::required("output_dir"),
        FieldSpec::required("project_file"),
        FieldSpec::required("project_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("target_name"),
        FieldSpec::required("profile_name"),
        FieldSpec::required("toml"),
        FieldSpec::new("warnings", FieldDefault::EmptyTuple),
        FieldSpec::new("dry_run", FieldDefault::False),
    ],
};
const R_DBT_COMMAND_RESULT: RecordSpec = RecordSpec {
    name: "DbtCommandResult",
    doc: "Completed dbt command output.",
    fields: &[
        FieldSpec::required("argv"),
        FieldSpec::required("returncode"),
        FieldSpec::new("stdout", FieldDefault::Text("")),
        FieldSpec::new("stderr", FieldDefault::Text("")),
    ],
};
const R_DBT_NODE_EXECUTION_RESULT: RecordSpec = RecordSpec {
    name: "DbtNodeExecutionResult",
    doc: "One dbt node execution result parsed from JSON logs.",
    fields: &[
        FieldSpec::required("unique_id"),
        FieldSpec::required("resource_type"),
        FieldSpec::required("node_name"),
        FieldSpec::required("status"),
        FieldSpec::required("index"),
        FieldSpec::required("total"),
        FieldSpec::required("execution_time"),
        FieldSpec::new("materialized", FieldDefault::None),
        FieldSpec::new("relation_name", FieldDefault::None),
        FieldSpec::new("database", FieldDefault::None),
        FieldSpec::new("schema", FieldDefault::None),
        FieldSpec::new("node_checksum", FieldDefault::None),
        FieldSpec::new("messages", FieldDefault::EmptyTuple),
    ],
};
const R_DBT_LS_RESULT: RecordSpec = RecordSpec {
    name: "DbtLsResult",
    doc: "Parsed result from one dbt ls invocation.",
    fields: &[FieldSpec::required("nodes"), FieldSpec::required("command")],
};
const R_RULE_GUIDANCE: RecordSpec = RecordSpec {
    name: "RuleGuidance",
    doc: "Structured authoring guidance shared by diagnostics and generated documentation.",
    fields: &[
        FieldSpec::required("good_example"),
        FieldSpec::required("anti_tautology"),
        FieldSpec::required("mutation_check"),
    ],
};
const R_RULE_EXEMPTION: RecordSpec = RecordSpec {
    name: "RuleExemption",
    doc: "",
    fields: &[
        FieldSpec::required("rule"),
        FieldSpec::required("path"),
        FieldSpec::required("reason"),
    ],
};
const R_GRAPH_EDGE_EXCLUSION: RecordSpec = RecordSpec {
    name: "GraphEdgeExclusion",
    doc: "One exact, temporary internal-layer dependency exception.",
    fields: &[
        FieldSpec::required("consumer"),
        FieldSpec::required("dependency"),
        FieldSpec::required("reason"),
    ],
};
const R_RULE_IGNORE: RecordSpec = RecordSpec {
    name: "RuleIgnore",
    doc: "",
    fields: &[
        FieldSpec::required("rules"),
        FieldSpec::required("paths"),
        FieldSpec::required("reason"),
        FieldSpec::new("selectors", FieldDefault::EmptyTuple),
    ],
};
const R_SELECT_STAR_ALLOW: RecordSpec = RecordSpec {
    name: "SelectStarAllow",
    doc: "",
    fields: &[FieldSpec::required("paths"), FieldSpec::required("reason")],
};
const R_THRESHOLD_OVERRIDE: RecordSpec = RecordSpec {
    name: "ThresholdOverride",
    doc: "",
    fields: &[
        FieldSpec::required("paths"),
        FieldSpec::required("thresholds"),
        FieldSpec::required("reason"),
    ],
};
const R_RULES_CACHE_CONFIG: RecordSpec = RecordSpec {
    name: "RulesCacheConfig",
    doc: "",
    fields: &[FieldSpec::new("enabled", FieldDefault::True)],
};
const R_SQL_TEST_RULES_CONFIG: RecordSpec = RecordSpec {
    name: "SqlTestRulesConfig",
    doc: "",
    fields: &[FieldSpec::new(
        "pipeline_directory",
        FieldDefault::Text("pipelines"),
    )],
};
const R_PREPARED_SQL_LINT_RESULT: RecordSpec = RecordSpec {
    name: "PreparedSqlLintResult",
    doc: "Reusable expansion context and completed preliminary SQL checks.",
    fields: &[
        FieldSpec::required("result"),
        FieldSpec::required("context"),
    ],
};
const R_SQL_EXPANSION_REUSE: RecordSpec = RecordSpec {
    name: "SqlExpansionReuse",
    doc: "Compiler declaration scope for post-assembly SQL checks; assembly still runs its macros.",
    fields: &[
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("declaration_scope"),
    ],
};
const R_PREPARED_SQL_LINT: RecordSpec = RecordSpec {
    name: "PreparedSqlLint",
    doc: "Process-local SQL checks started after compiler expansion has completed.",
    fields: &[
        FieldSpec::required("codes"),
        FieldSpec::required("future"),
        FieldSpec::new("project_dir", FieldDefault::None),
    ],
};
const R_SQL_RULES_EVALUATION: RecordSpec = RecordSpec {
    name: "SqlRulesEvaluation",
    doc: "SQL rule findings of one run, their cache accounting and elapsed time.",
    fields: &[
        FieldSpec::required("findings"),
        FieldSpec::required("cache_hits"),
        FieldSpec::required("cache_misses"),
        FieldSpec::new("sql_ms", FieldDefault::Int(0)),
    ],
};
const R_RULE_RUN_PLAN: RecordSpec = RecordSpec {
    name: "RuleRunPlan",
    doc: "The catalogue, selected rules, project slice and settings one rules run evaluates.",
    fields: &[
        FieldSpec::required("effective_config"),
        FieldSpec::required("project_dir"),
        FieldSpec::required("catalogue"),
        FieldSpec::required("custom_payloads"),
        FieldSpec::required("selected"),
        FieldSpec::required("skipped_type_proof_rules"),
        FieldSpec::required("model_paths"),
        FieldSpec::required("project"),
        FieldSpec::required("config"),
    ],
};
const R_RULES_RUN_RESULT: RecordSpec = RecordSpec {
    name: "RulesRunResult",
    doc: "Unified findings and phase measurements for configured rules.",
    fields: &[
        FieldSpec::required("findings"),
        FieldSpec::required("evaluated_models"),
        FieldSpec::required("built_in_ms"),
        FieldSpec::required("custom_ms"),
        FieldSpec::new("custom_cpu_ms", FieldDefault::Int(0)),
        FieldSpec::new("unevaluated_resources", FieldDefault::Int(0)),
        FieldSpec::new("cache_hits", FieldDefault::Int(0)),
        FieldSpec::new("cache_misses", FieldDefault::Int(0)),
        FieldSpec::new("skipped_type_proof_rules", FieldDefault::EmptyTuple),
    ],
};
const R_NATIVE_RULES_EVALUATION: RecordSpec = RecordSpec {
    name: "NativeRulesEvaluation",
    doc: "The built-in rules response, decoded natively.",
    fields: &[
        FieldSpec::required("findings"),
        FieldSpec::required("selected_codes"),
        FieldSpec::required("evaluated_models"),
        FieldSpec::required("cache_hits"),
        FieldSpec::required("cache_misses"),
        FieldSpec::required("built_in_ms"),
        FieldSpec::required("reused"),
    ],
};
const R_CUSTOM_RULES_OUTCOME: RecordSpec = RecordSpec {
    name: "CustomRulesOutcome",
    doc: "Custom-rule findings in canonical order and their cache accounting.",
    fields: &[
        FieldSpec::required("findings"),
        FieldSpec::required("cache_hits"),
        FieldSpec::required("cache_misses"),
        FieldSpec::required("custom_ms"),
        FieldSpec::new("custom_cpu_ms", FieldDefault::Int(0)),
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
    R_COMPILE_PIPELINE_OPTIONS,
    R_PYTHON_PLAN_ENTRY,
    R_PYTHON_RUN_PLAN_OUTPUTS,
    R_COMPILED_PROJECT_PHASE_RESULT,
    R_STATIC_COMMAND_CONTEXT,
    R_CLONE_PIPELINE_OPTIONS,
    R_CLONE_PIPELINE_CONNECTION,
    R_CLONE_PIPELINE_RESULT,
    R_PARSED_SELECTOR,
    R_PATH_SELECTOR,
    R_SQL_TEST_SELECTION,
    R_PLANNER_SCOPE,
    R_PLANNER_RELATIONS_CONTEXT,
    R_SQL_TEST_ASSERTION_STEP,
    R_PLANNER_SELECTION,
    R_PLANNER_OVERRIDES,
    R_DEFERRAL_INPUTS,
    R_PLANNER_POLICIES,
    R_DISCOVERED_PYTHON_LOADER_METADATA,
    R_DISCOVERED_PYTHON_TASK_METADATA,
    R_DISCOVERED_PYTHON_ASSET_METADATA,
    R_DISCOVERED_PYTHON_CHECK_METADATA,
    R_PYTHON_NODE_DEPENDENCY_EDGE,
    R_PYTHON_SQL_RUN_SELECTION,
    R_LITERAL_SQL_RELATION,
    R_DIRECT_SOURCE_FRESHNESS_PLANNING_RESULT,
    R_SQL_BINDING_DIAGNOSTIC,
    R_SQL_BINDING_RESULT,
    R_SQL_SCHEMA_VALIDATION_REQUEST,
    R_DBT_CLI_OPTIONS,
    R_NORMALIZED_DBT_PROFILE_CONNECTION,
    R_DBT_INIT_PROGRESS_CALLBACKS,
    R_DBT_INIT_REQUEST,
    R_DBT_INIT_RESULT,
    R_DBT_COMMAND_RESULT,
    R_DBT_NODE_EXECUTION_RESULT,
    R_DBT_LS_RESULT,
    R_RULE_GUIDANCE,
    R_RULE_EXEMPTION,
    R_GRAPH_EDGE_EXCLUSION,
    R_RULE_IGNORE,
    R_SELECT_STAR_ALLOW,
    R_THRESHOLD_OVERRIDE,
    R_RULES_CACHE_CONFIG,
    R_SQL_TEST_RULES_CONFIG,
    R_PREPARED_SQL_LINT_RESULT,
    R_SQL_EXPANSION_REUSE,
    R_PREPARED_SQL_LINT,
    R_SQL_RULES_EVALUATION,
    R_RULE_RUN_PLAN,
    R_RULES_RUN_RESULT,
    R_NATIVE_RULES_EVALUATION,
    R_CUSTOM_RULES_OUTCOME,
];
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
    ErrorSpec {
        name: "DbtInteropError",
        parent: VALUE_ERROR_PARENT,
        doc: "Base class for expected dbt interop errors.",
        class_attributes: &[("code", ClassValue::Text("C240"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "DbtInteropConfigError",
        parent: "DbtInteropError",
        doc: "Raised when dbt project configuration is missing or invalid.",
        class_attributes: &[("code", ClassValue::Text("C240"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "DbtInteropRuntimeError",
        parent: "DbtInteropError",
        doc: "Raised when dbt command execution fails.",
        class_attributes: &[("code", ClassValue::Text("C241"))],
        required: &[],
        fixed: &[],
    },
    ErrorSpec {
        name: "DbtInteropArgumentError",
        parent: "DbtInteropError",
        doc: "Raised when `sqb dbt` arguments cannot be routed safely.",
        class_attributes: &[("code", ClassValue::Text("C230"))],
        required: &[],
        fixed: &[],
    },
];
