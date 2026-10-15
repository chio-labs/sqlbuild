//! Layouts of the compile and discovery value records hosted natively.

use crate::bindings::_helpers::records::models::{FieldDefault, FieldSpec, RecordSpec};

const R_RELATED_LOCATION: RecordSpec = RecordSpec {
    name: "RelatedLocation",
    doc: "A secondary authored location that adds context to a diagnostic.",
    fields: &[
        FieldSpec::required("label"),
        FieldSpec::required("location"),
        FieldSpec::new("message", FieldDefault::None),
    ],
};
const R_FIXTURE_COLUMN_INFERENCE: RecordSpec = RecordSpec {
    name: "FixtureColumnInference",
    doc: "Inferred fixture columns plus outputs that are explicitly bare NULL literals.",
    fields: &[
        FieldSpec::required("columns"),
        FieldSpec::required("null_literal_names"),
        FieldSpec::required("quoted_names"),
    ],
};
const R_DYNAMIC_COLUMN_FAMILY_PROOF: RecordSpec = RecordSpec {
    name: "DynamicColumnFamilyProof",
    doc: "Compiler evidence for one declared runtime-generated column family.",
    fields: &[
        FieldSpec::required("name"),
        FieldSpec::new("inferred_type", FieldDefault::None),
    ],
};
const R_DYNAMIC_COLUMN_CONTRACT_PROOF: RecordSpec = RecordSpec {
    name: "DynamicColumnContractProof",
    doc: "Closed output-shape evidence for a dynamic column contract.",
    fields: &[
        FieldSpec::required("output_proven"),
        FieldSpec::new("fixed_columns", FieldDefault::EmptyTuple),
        FieldSpec::new("families", FieldDefault::EmptyTuple),
        FieldSpec::new("input_relations", FieldDefault::EmptyTuple),
        FieldSpec::new("failure_reason", FieldDefault::None),
        FieldSpec::new("bare_dynamic_pivot", FieldDefault::False),
    ],
};
const R_COMPILE_MODEL_CONFIG: RecordSpec = RecordSpec {
    name: "CompileModelConfig",
    doc: "Pre-semantic effective config layers attached to a model input.",
    fields: &[
        FieldSpec::new("values", FieldDefault::EmptyDict),
        FieldSpec::new("model_header_keys", FieldDefault::EmptyTuple),
        FieldSpec::new("matched_path_default", FieldDefault::None),
        FieldSpec::new("logical_schema", FieldDefault::None),
        FieldSpec::new("layer_schema", FieldDefault::None),
        FieldSpec::new("logical_database", FieldDefault::None),
        FieldSpec::new(
            "time_travel_retention",
            FieldDefault::Call("sqlbuild._native", "ResolvedTimeTravelRetention"),
        ),
        FieldSpec::new(
            "table_type",
            FieldDefault::Call("sqlbuild._native", "ResolvedTableType"),
        ),
    ],
};
const R_CURSOR_INPUT_ROLES: RecordSpec = RecordSpec {
    name: "CursorInputRoles",
    doc: "Effective filter and watermark inputs for one compiled model.",
    fields: &[
        FieldSpec::required("filter_inputs"),
        FieldSpec::required("watermark_inputs"),
    ],
};
const R_DECLARATION_RUNTIME_PROJECTION: RecordSpec = RecordSpec {
    name: "DeclarationRuntimeProjection",
    doc: "Process-only declaration values keyed by canonical static identity.",
    fields: &[FieldSpec::new("declarations", FieldDefault::EmptyDict)],
};
const R_DECLARATION_SCOPE_RESOLVER: RecordSpec = RecordSpec {
    name: "DeclarationScopeResolver",
    doc: "Process-only lookup state used to project visible runtime declarations.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("lookup"),
        FieldSpec::required("projection"),
        FieldSpec {
            name: "native_contexts",
            default: FieldDefault::Required,
            compared: false,
        },
        FieldSpec::new("resource_specific", FieldDefault::None),
        FieldSpec {
            name: "contexts_by_directory",
            default: FieldDefault::EmptyDict,
            compared: false,
        },
    ],
};
const R_DECLARATION_SCOPE_BUILD: RecordSpec = RecordSpec {
    name: "DeclarationScopeBuild",
    doc: "Static artifact and process-local values shared by compile attachment phases.",
    fields: &[
        FieldSpec::required("loaded_macros"),
        FieldSpec::required("index"),
        FieldSpec::required("resolver"),
        FieldSpec::required("sql_test_scans"),
    ],
};
const R_MACRO_EXPANSION_RESULT: RecordSpec = RecordSpec {
    name: "MacroExpansionResult",
    doc: "Expanded SQL and resolved macro usage facts from one authored string.",
    fields: &[
        FieldSpec::required("sql"),
        FieldSpec::new("spans", FieldDefault::EmptyTuple),
        FieldSpec::new("dependencies", FieldDefault::EmptyTuple),
        FieldSpec::new("usages", FieldDefault::EmptyTuple),
        FieldSpec::new("argument_references", FieldDefault::EmptyTuple),
    ],
};
const R_VISIBLE_MODEL_DECLARATIONS: RecordSpec = RecordSpec {
    name: "VisibleModelDeclarations",
    doc: "One model's visible declarations and macros, as the native model loop resolves them.",
    fields: &[
        FieldSpec::required("local_enums"),
        FieldSpec::required("local_constants"),
        FieldSpec::required("enums"),
        FieldSpec::required("constants"),
        FieldSpec::required("inaccessible_enums"),
        FieldSpec::required("inaccessible_constants"),
        FieldSpec::required("enum_visibility"),
        FieldSpec::required("constant_visibility"),
        FieldSpec::required("macros"),
        FieldSpec::required("macro_records"),
        FieldSpec::required("inaccessible_macros"),
    ],
};
const R_DECLARATION_EXPANSION_CONTEXT: RecordSpec = RecordSpec {
    name: "DeclarationExpansionContext",
    doc: "Declarations and adapter rendering used by one authored SQL owner.",
    fields: &[
        FieldSpec::required("declarations"),
        FieldSpec::required("value_renderer"),
        FieldSpec::required("collection_rendering"),
        FieldSpec::new("resolver", FieldDefault::None),
    ],
};
const R_COMPILE_ADAPTER_CONTEXT: RecordSpec = RecordSpec {
    name: "CompileAdapterContext",
    doc: "Cycle-free adapter behavior required while building compile inputs.",
    fields: &[
        FieldSpec::required("value_renderer"),
        FieldSpec::required("collection_rendering"),
        FieldSpec::required("python_functions_inherit_default_namespace"),
        FieldSpec::required("sql_lexical_syntax"),
    ],
};
const R_INVALID_SQL_REFERENCE_CALL: RecordSpec = RecordSpec {
    name: "InvalidSqlReferenceCall",
    doc: "One reference call whose arguments compile could not replace with a relation.",
    fields: &[
        FieldSpec::required("ref_kind"),
        FieldSpec::required("call"),
        FieldSpec::required("start"),
        FieldSpec::required("message"),
        FieldSpec::required("help"),
        FieldSpec::required("corrected_call"),
    ],
};
const R_SQL_REFERENCE_SCAN: RecordSpec = RecordSpec {
    name: "SqlReferenceScan",
    doc: "Valid references and rejected reference calls found in one SQL text.",
    fields: &[
        FieldSpec::required("references"),
        FieldSpec::new("invalid_calls", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILED_LINEAGE_COLUMN_FACT: RecordSpec = RecordSpec {
    name: "CompiledLineageColumnFact",
    doc: "Compact output column lineage fact extracted during SQL analysis.",
    fields: &[
        FieldSpec::required("output_column"),
        FieldSpec::new("upstream_columns", FieldDefault::EmptyTuple),
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
const R_POLYGLOT_ANALYSIS_RESULT: RecordSpec = RecordSpec {
    name: "PolyglotAnalysisResult",
    doc: "Outcome of one Polyglot column and lineage analysis pass.",
    fields: &[
        FieldSpec::required("analysis_succeeded"),
        FieldSpec::new("columns", FieldDefault::None),
        FieldSpec::new("lineage_columns", FieldDefault::EmptyTuple),
        FieldSpec::new("has_star", FieldDefault::False),
        FieldSpec::new("star_resolved", FieldDefault::False),
        FieldSpec::new("binding_diagnostics", FieldDefault::EmptyTuple),
        FieldSpec::new("binding_validated", FieldDefault::False),
    ],
};
const R_ANALYSIS_CACHE_CONTEXT: RecordSpec = RecordSpec {
    name: "AnalysisCacheContext",
    doc: "Shared project-local analysis cache identity for one compile invocation.",
    fields: &[
        FieldSpec::required("root"),
        FieldSpec::required("shared_fingerprint"),
        FieldSpec::new("signature_namespace", FieldDefault::Text("default")),
    ],
};
const R_COMPILE_ANALYSIS_SELECTION: RecordSpec = RecordSpec {
    name: "CompileAnalysisSelection",
    doc: "Deep-analysis selection and invocation-local preparation observer.",
    fields: &[
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("auto_load_sources", FieldDefault::False),
        FieldSpec::new("no_cache", FieldDefault::False),
        FieldSpec {
            name: "on_inputs_ready",
            default: FieldDefault::None,
            compared: false,
        },
    ],
};
const R_COMPILE_SQL_SCENARIO_CTE: RecordSpec = RecordSpec {
    name: "CompileSqlScenarioCte",
    doc: "One top-level SQL-native scenario CTE extracted after macro expansion.",
    fields: &[FieldSpec::required("name"), FieldSpec::required("sql_body")],
};
const R_FUNCTION_ARGUMENT: RecordSpec = RecordSpec {
    name: "FunctionArgument",
    doc: "One SQL function argument with an adapter-native type string.",
    fields: &[FieldSpec::required("name"), FieldSpec::required("type")],
};
const R_FUNCTION_RETURN_COLUMN: RecordSpec = RecordSpec {
    name: "FunctionReturnColumn",
    doc: "One named table-function return column with an adapter-native type string.",
    fields: &[FieldSpec::required("name"), FieldSpec::required("type")],
};
const R_HAND_BUILT_ANALYSIS: RecordSpec = RecordSpec {
    name: "HandBuiltAnalysis",
    doc: "A hand-built model input's session position, fallback columns and standalone proof.",
    fields: &[
        FieldSpec::required("session"),
        FieldSpec::required("fallback"),
        FieldSpec::required("standalone_proof"),
    ],
};
const R_MODEL_SQL_ANALYSIS: RecordSpec = RecordSpec {
    name: "ModelSqlAnalysis",
    doc: "Completed model analysis and its in-memory binding proof.",
    fields: &[
        FieldSpec::required("polyglot_analysis"),
        FieldSpec::required("placeholders"),
        FieldSpec::new("cached", FieldDefault::False),
        FieldSpec::new("fused_binding_validated", FieldDefault::False),
        FieldSpec::new("cleaned_sql", FieldDefault::None),
        FieldSpec::new("validated_schema", FieldDefault::None),
        FieldSpec::new("dynamic_column_contract", FieldDefault::None),
    ],
};
const R_COMPILE_SQL_SCENARIO_INPUT: RecordSpec = RecordSpec {
    name: "CompileSqlScenarioInput",
    doc: "One discovered SQL-native scenario with compile-time SQL expansion applied.",
    fields: &[
        FieldSpec::required("scenario_file"),
        FieldSpec::required("sql_body"),
        FieldSpec::new("authored_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("expected_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("source_fixture_names", FieldDefault::EmptyTuple),
        FieldSpec::new("ref_fixture_names", FieldDefault::EmptyTuple),
        FieldSpec::new("seed_fixture_names", FieldDefault::EmptyTuple),
        FieldSpec::new("dbt_ref_fixture_names", FieldDefault::EmptyTuple),
        FieldSpec::new("expected_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_names", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_target_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("target_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("declaration_usages", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILE_PROJECT_INPUTS: RecordSpec = RecordSpec {
    name: "CompileProjectInputs",
    doc: "Attached project view used as the first pre-semantic compile input snapshot.",
    fields: &[
        FieldSpec::required("project_config"),
        FieldSpec::required("local_config"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("sql_lexical_syntax"),
        FieldSpec::new("run_id", FieldDefault::Text("")),
        FieldSpec::new("effective_target_name", FieldDefault::None),
        FieldSpec::new("effective_target", FieldDefault::None),
        FieldSpec::new("compile_cache_dir", FieldDefault::None),
        FieldSpec::new("effective_connection", FieldDefault::EmptyDict),
        FieldSpec::new(
            "effective_settings",
            FieldDefault::Call("sqlbuild._native", "SettingsConfig"),
        ),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("effective_vars", FieldDefault::EmptyDict),
        FieldSpec {
            name: "macro_context",
            default: FieldDefault::None,
            compared: false,
        },
        FieldSpec::new("loaded_macros", FieldDefault::EmptyDict),
        FieldSpec::new("public_enums", FieldDefault::EmptyDict),
        FieldSpec::new("public_constants", FieldDefault::EmptyDict),
        FieldSpec::new("model_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("seed_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("source_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("sql_function_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("test_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("scenario_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("audit_inputs", FieldDefault::EmptyTuple),
        FieldSpec::new("diagnostics", FieldDefault::EmptyTuple),
        FieldSpec::new("external_sql_reference_resolver", FieldDefault::None),
        FieldSpec::new(
            "scope_index",
            FieldDefault::Call("sqlbuild._native", "ScopeIndex"),
        ),
        FieldSpec {
            name: "declaration_scope",
            default: FieldDefault::None,
            compared: false,
        },
        FieldSpec {
            name: "native_project",
            default: FieldDefault::None,
            compared: false,
        },
    ],
};
const R_COMPILED_SOURCE: RecordSpec = RecordSpec {
    name: "CompiledSource",
    doc: "Planner-ready compiled source metadata.",
    fields: &[
        FieldSpec::required("key"),
        FieldSpec::required("deps"),
        FieldSpec::required("name"),
        FieldSpec::required("source_entry"),
        FieldSpec::required("source_file"),
    ],
};
const R_COMPILED_SEED: RecordSpec = RecordSpec {
    name: "CompiledSeed",
    doc: "Planner-ready compiled seed metadata.",
    fields: &[
        FieldSpec::required("key"),
        FieldSpec::required("deps"),
        FieldSpec::required("name"),
        FieldSpec::required("seed_file"),
        FieldSpec::required("schema_entry"),
        FieldSpec::required("schema_file"),
        FieldSpec::required("destination"),
        FieldSpec::new("external", FieldDefault::False),
    ],
};
const R_COMPILED_FUNCTION: RecordSpec = RecordSpec {
    name: "CompiledFunction",
    doc: "Planner-ready compiled SQL function metadata.",
    fields: &[
        FieldSpec::required("key"),
        FieldSpec::required("deps"),
        FieldSpec::required("name"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("arguments"),
        FieldSpec::required("returns"),
        FieldSpec::required("body_sql"),
        FieldSpec::required("destination"),
        FieldSpec::required("fingerprint_destination"),
        FieldSpec::new("return_columns", FieldDefault::EmptyTuple),
        FieldSpec::new("references", FieldDefault::EmptyTuple),
        FieldSpec::new(
            "language",
            FieldDefault::Member("sqlbuild.compiler.compile.types", "FunctionLanguage", "SQL"),
        ),
        FieldSpec::new("source_file_path", FieldDefault::None),
        FieldSpec::new("runtime_version", FieldDefault::None),
        FieldSpec::new("entry_point", FieldDefault::None),
        FieldSpec::new("packages", FieldDefault::EmptyTuple),
        FieldSpec::new("tags", FieldDefault::EmptyTuple),
        FieldSpec::new("description", FieldDefault::None),
    ],
};
const R_PYTHON_SQL_REFERENCE_REPORT: RecordSpec = RecordSpec {
    name: "PythonSqlReferenceReport",
    doc: "P008 diagnostics plus literal SQL relations that named no project relation.",
    fields: &[
        FieldSpec::new("diagnostics", FieldDefault::EmptyTuple),
        FieldSpec::new("unmatched", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILE_SQL_TEST_CTE: RecordSpec = RecordSpec {
    name: "CompileSqlTestCte",
    doc: "One top-level SQL-native test CTE extracted after macro expansion.",
    fields: &[FieldSpec::required("name"), FieldSpec::required("sql_body")],
};
const R_COMPILE_MODEL_SQL_TEST_INPUT_PAYLOAD: RecordSpec = RecordSpec {
    name: "CompileModelSqlTestInputPayload",
    doc: "Model-mode SQL test compile payload.",
    fields: &[
        FieldSpec::new("authored_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("macro_mocks", FieldDefault::EmptyDict),
        FieldSpec::new("mock_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_source_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_seed_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_dbt_ref_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_table_function_names", FieldDefault::EmptyTuple),
        FieldSpec::new("expected_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("expected_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_names", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_target_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("read_helper_names", FieldDefault::EmptyTuple),
        FieldSpec::new("reference_target_model_names", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILE_DIRECT_LOGIC_SQL_TEST_INPUT_PAYLOAD: RecordSpec = RecordSpec {
    name: "CompileDirectLogicSqlTestInputPayload",
    doc: "Direct-logic SQL test compile payload.",
    fields: &[
        FieldSpec::required("actual_cte"),
        FieldSpec::required("expected_cte"),
        FieldSpec::required("mode"),
        FieldSpec::new("helper_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("tested_resource_names", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILE_SQL_TEST_INPUT: RecordSpec = RecordSpec {
    name: "CompileSqlTestInput",
    doc: "One discovered SQL-native test block with compile-time SQL expansion applied.",
    fields: &[
        FieldSpec::required("test_file"),
        FieldSpec::required("test_block"),
        FieldSpec::required("sql_body"),
        FieldSpec::new(
            "mode",
            FieldDefault::Member("sqlbuild.compiler.compile.types", "SqlTestMode", "MODEL"),
        ),
        FieldSpec::new(
            "payload",
            FieldDefault::Call("sqlbuild._native", "CompileModelSqlTestInputPayload"),
        ),
        FieldSpec::new("declaration_usages", FieldDefault::EmptyTuple),
        FieldSpec::new("parent_name", FieldDefault::None),
        FieldSpec::new("case_name", FieldDefault::None),
        FieldSpec::new("case_index", FieldDefault::None),
        FieldSpec::new("parameter_schema", FieldDefault::EmptyTuple),
        FieldSpec::new("parameter_values", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILED_MODEL_SQL_TEST_PAYLOAD: RecordSpec = RecordSpec {
    name: "CompiledModelSqlTestPayload",
    doc: "Compiled model-mode SQL test payload.",
    fields: &[
        FieldSpec::new("authored_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("macro_mocks", FieldDefault::EmptyDict),
        FieldSpec::new("model_query_overrides", FieldDefault::EmptyDict),
        FieldSpec::new("mock_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_source_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_seed_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_dbt_ref_names", FieldDefault::EmptyTuple),
        FieldSpec::new("mock_table_function_names", FieldDefault::EmptyTuple),
        FieldSpec::new("expected_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("expected_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("assertion_names", FieldDefault::EmptyTuple),
    ],
};
const R_SQL_EXPANSION_CONTEXT: RecordSpec = RecordSpec {
    name: "SqlExpansionContext",
    doc: "Everything needed to expand one project's authored SQL bodies.",
    fields: &[
        FieldSpec::required("effective_vars"),
        FieldSpec::required("loaded_macros"),
        FieldSpec::required("macro_context"),
        FieldSpec::required("enums"),
        FieldSpec::required("constants"),
        FieldSpec::required("value_renderer"),
        FieldSpec::required("collection_rendering"),
        FieldSpec::new("local_declarations", FieldDefault::EmptyDict),
        FieldSpec::new("declaration_resolver", FieldDefault::None),
    ],
};
const R_EXPANSION_SPAN: RecordSpec = RecordSpec {
    name: "ExpansionSpan",
    doc: "One substituted region, pairing its source range with its rendered range.",
    fields: &[
        FieldSpec::required("source_start"),
        FieldSpec::required("source_end"),
        FieldSpec::required("output_start"),
        FieldSpec::required("output_end"),
    ],
};
const R_COMPILED_SQL_EXPANSION: RecordSpec = RecordSpec {
    name: "CompiledSqlExpansion",
    doc: "Process-local authored-to-expanded SQL evidence shared with compiler checks.",
    fields: &[
        FieldSpec::required("authored_sql"),
        FieldSpec::required("expanded_sql"),
        FieldSpec::required("passes"),
    ],
};
const R_MAPPED_OFFSET: RecordSpec = RecordSpec {
    name: "MappedOffset",
    doc: "An offset in rendered SQL resolved back onto the text that produced it.",
    fields: &[
        FieldSpec::required("offset"),
        FieldSpec::required("generated"),
    ],
};
const R_COMPILED_DIRECT_LOGIC_SQL_TEST_PAYLOAD: RecordSpec = RecordSpec {
    name: "CompiledDirectLogicSqlTestPayload",
    doc: "Compiled direct-logic SQL test payload.",
    fields: &[
        FieldSpec::required("actual_cte"),
        FieldSpec::required("expected_cte"),
        FieldSpec::new(
            "mode",
            FieldDefault::Member("sqlbuild.compiler.compile.types", "SqlTestMode", "MODEL"),
        ),
        FieldSpec::new("helper_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("tested_resource_names", FieldDefault::EmptyTuple),
    ],
};
const R_COMPILED_SQL_TEST_RESOURCE: RecordSpec = RecordSpec {
    name: "CompiledSqlTestResource",
    doc: "One direct SQL test resource with its authored resource kind.",
    fields: &[FieldSpec::required("kind"), FieldSpec::required("name")],
};
const R_NATIVE_MODEL_CONFIG_SESSION: RecordSpec = RecordSpec {
    name: "NativeModelConfigSession",
    doc: "The native config builder, validator, and inherited storage policies for one compile.",
    fields: &[
        FieldSpec::required("path_defaults"),
        FieldSpec::required("builder"),
        FieldSpec::required("validator"),
        FieldSpec::required("inherited_storage"),
    ],
};
const R_NATIVE_MODEL_CONFIG_INPUTS: RecordSpec = RecordSpec {
    name: "NativeModelConfigInputs",
    doc: "The project and run inputs every model's native config build reads.",
    fields: &[
        FieldSpec::required("project_config"),
        FieldSpec::required("target_config"),
        FieldSpec::required("effective_vars"),
        FieldSpec::required("effective_target_name"),
        FieldSpec::required("run_id"),
        FieldSpec::required("microbatch_concurrency"),
    ],
};
const R_MODEL_VALIDATION_REQUEST: RecordSpec = RecordSpec {
    name: "ModelValidationRequest",
    doc: "One model's effective config and the facts its validators read.",
    fields: &[
        FieldSpec::required("model_file"),
        FieldSpec::required("config"),
        FieldSpec::required("references"),
        FieldSpec::required("declared_columns"),
        FieldSpec::required("query_sql"),
    ],
};
const R_NAMED_SQL_HOOK_ENTRY: RecordSpec = RecordSpec {
    name: "NamedSqlHookEntry",
    doc: "An unresolved invocation of a discovered SQL hook resource.",
    fields: &[FieldSpec::required("name"), FieldSpec::required("kwargs")],
};
const R_DISCOVERED_SQL_FUNCTION_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredSqlFunctionFile",
    doc: "A discovered SQL function file and its raw contents.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("header_values"),
        FieldSpec::required("body_sql"),
    ],
};
const R_DISCOVERED_SQL_HOOK_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredSqlHookFile",
    doc: "A discovered named SQL lifecycle hook resource.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("header_values"),
        FieldSpec::required("sql_body"),
        FieldSpec::required("name"),
        FieldSpec::new("description", FieldDefault::None),
        FieldSpec::new(
            "scope_kind",
            FieldDefault::Member("sqlbuild._native", "ScopeKind", "GLOBAL"),
        ),
        FieldSpec::new("ownership_root", FieldDefault::None),
        FieldSpec::new("owning_path", FieldDefault::None),
        FieldSpec::new("declaration_root", FieldDefault::None),
    ],
};
const R_ENUM_MEMBER: RecordSpec = RecordSpec {
    name: "EnumMember",
    doc: "One named member in a SQLBuild enum declaration.",
    fields: &[FieldSpec::required("name"), FieldSpec::required("value")],
};
const R_DISCOVERED_ENUM_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredEnumFile",
    doc: "A public SQL file containing one or more enum declarations.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("declarations"),
        FieldSpec::new(
            "scope_kind",
            FieldDefault::Member("sqlbuild._native", "ScopeKind", "GLOBAL"),
        ),
        FieldSpec::new("ownership_root", FieldDefault::None),
        FieldSpec::new("owning_path", FieldDefault::None),
        FieldSpec::new("declaration_root", FieldDefault::None),
    ],
};
const R_DISCOVERED_CONSTANT_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredConstantFile",
    doc: "A public SQL file containing one or more constant declarations.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("declarations"),
        FieldSpec::new(
            "scope_kind",
            FieldDefault::Member("sqlbuild._native", "ScopeKind", "GLOBAL"),
        ),
        FieldSpec::new("ownership_root", FieldDefault::None),
        FieldSpec::new("owning_path", FieldDefault::None),
        FieldSpec::new("declaration_root", FieldDefault::None),
    ],
};
const R_MODEL_SCHEMA_DECLARATION: RecordSpec = RecordSpec {
    name: "ModelSchemaDeclaration",
    doc: "One public reusable model column schema declaration.",
    fields: &[
        FieldSpec::required("name"),
        FieldSpec::required("columns"),
        FieldSpec::required("relative_path"),
        FieldSpec::new("extends", FieldDefault::None),
        FieldSpec::new("description", FieldDefault::None),
    ],
};
const R_DISCOVERED_MODEL_SCHEMA_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredModelSchemaFile",
    doc: "A public SQL file containing reusable model schemas.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("declarations"),
        FieldSpec::new(
            "scope_kind",
            FieldDefault::Member("sqlbuild._native", "ScopeKind", "GLOBAL"),
        ),
        FieldSpec::new("ownership_root", FieldDefault::None),
        FieldSpec::new("owning_path", FieldDefault::None),
        FieldSpec::new("declaration_root", FieldDefault::None),
    ],
};
const R_DISCOVERED_PYTHON_FUNCTION_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredPythonFunctionFile",
    doc: "A discovered Python function file and its parsed UDF metadata.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("header_values"),
        FieldSpec::required("entry_point"),
        FieldSpec::required("body_python"),
    ],
};
const R_DISCOVERED_SCHEMA_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredSchemaFile",
    doc: "A discovered schema.yml file and its raw contents.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("model_entries"),
        FieldSpec::required("seed_entries"),
    ],
};
const R_DISCOVERED_SEED_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredSeedFile",
    doc: "A discovered seed file.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
    ],
};
const R_DISCOVERED_SQL_TEST_CASE: RecordSpec = RecordSpec {
    name: "DiscoveredSqlTestCase",
    doc: "One ordered named case belonging to a SQL-native test template.",
    fields: &[
        FieldSpec::required("name"),
        FieldSpec::required("values"),
        FieldSpec::required("case_index"),
    ],
};
const R_DISCOVERED_SQL_TEST_BLOCK: RecordSpec = RecordSpec {
    name: "DiscoveredSqlTestBlock",
    doc: "One raw TEST(...) block discovered from a SQL-native test file.",
    fields: &[
        FieldSpec::required("test_index"),
        FieldSpec::required("header_values"),
        FieldSpec::required("sql_body"),
        FieldSpec::new("name", FieldDefault::None),
        FieldSpec::new(
            "mode",
            FieldDefault::Member("sqlbuild.compiler.compile.types", "SqlTestMode", "MODEL"),
        ),
        FieldSpec::new("parameters", FieldDefault::EmptyTuple),
        FieldSpec::new("cases", FieldDefault::EmptyTuple),
        FieldSpec::new("cursor_start", FieldDefault::None),
        FieldSpec::new("cursor_end", FieldDefault::None),
        FieldSpec::new("sql_body_span", FieldDefault::None),
    ],
};
const R_DISCOVERED_AUDIT_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredAuditFile",
    doc: "A discovered audit SQL file and its raw contents.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
        FieldSpec::required("contents"),
        FieldSpec::required("blocks"),
        FieldSpec::new(
            "declaration_kind",
            FieldDefault::Member("sqlbuild._native", "DeclarationKind", "AUDIT"),
        ),
        FieldSpec::new(
            "scope_kind",
            FieldDefault::Member("sqlbuild._native", "ScopeKind", "GLOBAL"),
        ),
        FieldSpec::new("ownership_root", FieldDefault::None),
        FieldSpec::new("owning_path", FieldDefault::None),
        FieldSpec::new("declaration_root", FieldDefault::None),
    ],
};
const R_DISCOVERED_AUDIT_BLOCK: RecordSpec = RecordSpec {
    name: "DiscoveredAuditBlock",
    doc: "One raw AUDIT(...) block discovered from a SQL audit file.",
    fields: &[
        FieldSpec::required("audit_index"),
        FieldSpec::required("header_values"),
        FieldSpec::required("sql_body"),
        FieldSpec::new("name", FieldDefault::None),
        FieldSpec::new(
            "evaluation_mode",
            FieldDefault::Member(
                "sqlbuild.compiler.auditing.types",
                "AuditEvaluationMode",
                "VIOLATIONS",
            ),
        ),
        FieldSpec::new("measurement_contract", FieldDefault::None),
        FieldSpec::new("measure_sql", FieldDefault::None),
        FieldSpec::new("evidence_sql", FieldDefault::None),
    ],
};
const R_DISCOVERED_ADAPTER_FILE: RecordSpec = RecordSpec {
    name: "DiscoveredAdapterFile",
    doc: "A detected project adapter Python file.",
    fields: &[
        FieldSpec::required("file_path"),
        FieldSpec::required("relative_path"),
    ],
};
const R_DISCOVERY_FILE_FAULT: RecordSpec = RecordSpec {
    name: "DiscoveryFileFault",
    doc: "One project-relative authored file fault captured during tolerant discovery.",
    fields: &[FieldSpec::required("path"), FieldSpec::required("message")],
};
const R_TOLERANT_SCOPE_DISCOVERY: RecordSpec = RecordSpec {
    name: "TolerantScopeDiscovery",
    doc: "Parsed scope inputs and independently categorized tolerant discovery faults.",
    fields: &[
        FieldSpec::required("discovered_inputs"),
        FieldSpec::new("resource_faults", FieldDefault::EmptyTuple),
        FieldSpec::new("declaration_faults", FieldDefault::EmptyTuple),
        FieldSpec::new("relationship_faults", FieldDefault::EmptyTuple),
        FieldSpec::new("config_faults", FieldDefault::EmptyTuple),
    ],
};

/// The compile and discovery value records.
pub(crate) const COMPILE_VALUE_RECORDS: &[RecordSpec] = &[
    R_RELATED_LOCATION,
    R_FIXTURE_COLUMN_INFERENCE,
    R_DYNAMIC_COLUMN_FAMILY_PROOF,
    R_DYNAMIC_COLUMN_CONTRACT_PROOF,
    R_COMPILE_MODEL_CONFIG,
    R_CURSOR_INPUT_ROLES,
    R_DECLARATION_RUNTIME_PROJECTION,
    R_DECLARATION_SCOPE_RESOLVER,
    R_DECLARATION_SCOPE_BUILD,
    R_MACRO_EXPANSION_RESULT,
    R_VISIBLE_MODEL_DECLARATIONS,
    R_DECLARATION_EXPANSION_CONTEXT,
    R_COMPILE_ADAPTER_CONTEXT,
    R_INVALID_SQL_REFERENCE_CALL,
    R_SQL_REFERENCE_SCAN,
    R_COMPILED_LINEAGE_COLUMN_FACT,
    R_POLYGLOT_ANALYSIS_RESULT,
    R_ANALYSIS_CACHE_CONTEXT,
    R_COMPILE_ANALYSIS_SELECTION,
    R_COMPILE_SQL_SCENARIO_CTE,
    R_FUNCTION_ARGUMENT,
    R_FUNCTION_RETURN_COLUMN,
    R_HAND_BUILT_ANALYSIS,
    R_MODEL_SQL_ANALYSIS,
    R_COMPILE_SQL_SCENARIO_INPUT,
    R_COMPILE_PROJECT_INPUTS,
    R_COMPILED_SOURCE,
    R_COMPILED_SEED,
    R_COMPILED_FUNCTION,
    R_PYTHON_SQL_REFERENCE_REPORT,
    R_COMPILE_SQL_TEST_CTE,
    R_COMPILE_MODEL_SQL_TEST_INPUT_PAYLOAD,
    R_COMPILE_DIRECT_LOGIC_SQL_TEST_INPUT_PAYLOAD,
    R_COMPILE_SQL_TEST_INPUT,
    R_COMPILED_MODEL_SQL_TEST_PAYLOAD,
    R_SQL_EXPANSION_CONTEXT,
    R_EXPANSION_SPAN,
    R_COMPILED_SQL_EXPANSION,
    R_MAPPED_OFFSET,
    R_COMPILED_DIRECT_LOGIC_SQL_TEST_PAYLOAD,
    R_COMPILED_SQL_TEST_RESOURCE,
    R_NATIVE_MODEL_CONFIG_SESSION,
    R_NATIVE_MODEL_CONFIG_INPUTS,
    R_MODEL_VALIDATION_REQUEST,
    R_NAMED_SQL_HOOK_ENTRY,
    R_DISCOVERED_SQL_FUNCTION_FILE,
    R_DISCOVERED_SQL_HOOK_FILE,
    R_ENUM_MEMBER,
    R_DISCOVERED_ENUM_FILE,
    R_DISCOVERED_CONSTANT_FILE,
    R_MODEL_SCHEMA_DECLARATION,
    R_DISCOVERED_MODEL_SCHEMA_FILE,
    R_DISCOVERED_PYTHON_FUNCTION_FILE,
    R_DISCOVERED_SCHEMA_FILE,
    R_DISCOVERED_SEED_FILE,
    R_DISCOVERED_SQL_TEST_CASE,
    R_DISCOVERED_SQL_TEST_BLOCK,
    R_DISCOVERED_AUDIT_FILE,
    R_DISCOVERED_AUDIT_BLOCK,
    R_DISCOVERED_ADAPTER_FILE,
    R_DISCOVERY_FILE_FAULT,
    R_TOLERANT_SCOPE_DISCOVERY,
];
