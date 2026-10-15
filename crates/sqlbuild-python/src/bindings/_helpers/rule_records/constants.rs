//! Layouts of the rule engine value records hosted natively.

use crate::bindings::_helpers::records::models::{FieldDefault, FieldSpec, RecordSpec};

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

/// The rule engine value records.
pub(crate) const RULE_RECORDS: &[RecordSpec] = &[
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
