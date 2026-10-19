//! Plain-data requests and outcomes of native semantic completion.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use crate::semantic_checks::types::CompletedParts;
use crate::type_system::errors::TypeNormalizationError;

/// One compiled model output column and the upstream columns it reads.
#[derive(Clone, Debug, Default)]
pub struct LineageOutput {
    pub output_column: String,
    pub upstream: Vec<(String, String)>,
}

/// One binding diagnostic a model owns, identified by its value-equality id.
#[derive(Clone, Debug)]
pub struct ModelBinding {
    pub id: usize,
    pub code: String,
    pub message: String,
    pub is_error: bool,
}

/// One raw native binding row Python kept for a model, identified by its value-equality id.
#[derive(Clone, Debug)]
pub struct RawBinding {
    pub id: usize,
    pub code: String,
    pub message: String,
    pub start: Option<i64>,
    pub end: Option<i64>,
}

/// The project-diagnostic fields `update_binding_models` reads.
#[derive(Clone, Debug)]
pub struct DiagnosticOwner {
    pub id: usize,
    pub code: String,
    pub is_model: bool,
    pub resource_name: Option<String>,
}

/// One model as type recovery reads it.
#[derive(Clone, Debug)]
pub struct RecoveryModel {
    pub name: String,
    pub query_sql: String,
    pub inferred_columns: Option<Vec<String>>,
    pub references: Vec<String>,
    pub lineage: Vec<LineageOutput>,
    pub bindings: Vec<ModelBinding>,
    pub raw_bindings: Vec<RawBinding>,
}

/// Python's `recover_output_types` inputs as plain data.
#[derive(Clone, Debug)]
pub struct TypeRecoveryRequest {
    pub dialect: Option<String>,
    pub models: Vec<RecoveryModel>,
    pub diagnostics: Vec<DiagnosticOwner>,
}

/// Why completion fails: Python's error for the same input, or an internal native failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SemanticFailure {
    /// The wheel's `TypeError` for tokenizing without a dialect.
    NoDialect,
    /// The wheel's `ValueError` for a dialect name Polyglot does not know.
    UnknownDialect(String),
    /// The error Python's type normalization raised.
    TypeNormalization(TypeNormalizationError),
    /// An internal native failure, raised as `NativeCompilerError`.
    Internal(String),
}

impl SemanticFailure {
    /// An internal failure with a fixed reason that never quotes SQL.
    pub(crate) fn internal(reason: &str) -> Self {
        Self::Internal(reason.to_owned())
    }
}

/// The poisoned outputs found before the revalidation Python runs on the binding catalog.
#[derive(Clone, Debug, Default)]
pub struct TypeRecoveryPlan {
    pub poisoned: Vec<((String, String), usize)>,
    pub roots_by_model: HashMap<usize, HashMap<usize, usize>>,
    pub outputs_by_diagnostic: HashMap<usize, HashSet<String>>,
    pub causes_by_model: Vec<(usize, HashSet<usize>)>,
}

impl TypeRecoveryPlan {
    /// Failed model indexes to revalidate with unknown poisoned types, in model order.
    pub fn revalidated_models(&self) -> Vec<usize> {
        self.causes_by_model
            .iter()
            .map(|(index, _)| *index)
            .collect()
    }

    /// Poisoned `(model, column)` outputs in Python's dict order.
    pub fn poisoned_outputs(&self) -> Vec<(String, String)> {
        self.poisoned.iter().map(|(key, _)| key.clone()).collect()
    }
}

/// Type recovery's first step: nothing to recover, or a plan.
#[derive(Clone, Debug)]
pub enum TypeRecoveryStep {
    Unchanged,
    Planned(TypeRecoveryPlan),
}

impl TypeRecoveryStep {
    /// `unchanged` or `planned`.
    pub fn status(&self) -> &'static str {
        match self {
            Self::Unchanged => "unchanged",
            Self::Planned(_) => "planned",
        }
    }

    /// The plan Python's revalidation and the finishing step read.
    pub fn plan(&self) -> Option<&TypeRecoveryPlan> {
        match self {
            Self::Planned(plan) => Some(plan),
            _ => None,
        }
    }
}

/// Type recovery's edits: retained diagnostics with appended notes and model binding positions.
#[derive(Clone, Debug, Default)]
pub struct TypeRecoveryOutcome {
    /// `(project diagnostic index, appended note)` for every retained diagnostic, in order.
    pub kept: Vec<(usize, Option<String>)>,
    /// Indexes into `kept` of each model's binding diagnostics, in model order.
    pub model_bindings: Vec<Vec<usize>>,
}

/// A diagnostic location's line and column fields.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SemanticLocation {
    pub line: i64,
    pub column: i64,
    pub end_line: Option<i64>,
    pub end_column: Option<i64>,
}

/// One project diagnostic as recovery, explanation and opt-out rejection read it.
#[derive(Clone, Debug)]
pub struct SemanticDiagnostic {
    pub id: usize,
    pub code: String,
    pub message: String,
    /// `None` when the diagnostic has no resource type.
    pub resource_type: Option<String>,
    pub resource_name: Option<String>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub location: Option<SemanticLocation>,
    pub help: Option<String>,
    pub notes: Vec<String>,
}

/// One model as recovery, explanation and opt-out rejection read it.
#[derive(Clone, Debug)]
pub struct CompletionModel {
    pub name: String,
    pub query_sql: String,
    pub authored_sql: String,
    pub inferred_columns: Vec<String>,
    pub lineage: Vec<LineageOutput>,
    pub binding_codes: Vec<String>,
    /// The rejected opt-out location's file name, when the model's opt-out is rejected.
    pub rejected_opt_out_file: Option<String>,
}

/// Python's recovery, explanation and opt-out inputs as plain data.
#[derive(Clone, Debug)]
pub struct CompletionRequest {
    pub dialect: Option<String>,
    pub diagnostics: Vec<SemanticDiagnostic>,
    pub models: Vec<CompletionModel>,
    /// Closed relation shapes in Python's dict order.
    pub shapes: Vec<(String, Vec<(String, String)>)>,
}

/// One diagnostic after recovery and explanation, as fields Python replaces.
#[derive(Clone, Debug)]
pub struct CompletedDiagnostic {
    pub source: usize,
    pub message: String,
    pub help: Option<String>,
    pub notes: Vec<String>,
    pub location: Option<SemanticLocation>,
    pub line: Option<i64>,
    pub column: Option<i64>,
    pub changed: bool,
}

/// One P009 error replacing a rejected opt-out model's findings.
#[derive(Clone, Debug)]
pub struct OptOutDiagnostic {
    pub model: usize,
    pub message: String,
    pub note: String,
    pub help: String,
}

/// One entry of the final diagnostic order.
#[derive(Clone, Debug)]
pub enum FinalDiagnostic {
    Completed(usize),
    OptOut(OptOutDiagnostic),
}

impl FinalDiagnostic {
    /// `(completed position, opt-out error)`: exactly one side is set.
    pub fn into_parts(self) -> (Option<usize>, Option<OptOutDiagnostic>) {
        match self {
            Self::Completed(position) => (Some(position), None),
            Self::OptOut(opt_out) => (None, Some(opt_out)),
        }
    }
}

/// Recovery, explanation and opt-out rejection.
#[derive(Clone, Debug)]
pub struct CompletionOutcome {
    pub diagnostics: Vec<CompletedDiagnostic>,
    /// Indexes into `diagnostics` per model, or `None` when models keep their bindings.
    pub model_bindings: Option<Vec<Vec<usize>>>,
    pub order: Vec<FinalDiagnostic>,
}

impl CompletionOutcome {
    /// The completed diagnostics, model binding positions and final order.
    pub fn into_parts(self) -> CompletedParts {
        (self.diagnostics, self.model_bindings, self.order)
    }
}

/// One declared project function as Python's metadata checks read it.
#[derive(Clone, Debug)]
pub struct MetadataFunction {
    /// Python's `function.name.casefold()`, the key calls are looked up by.
    pub key: String,
    /// `(argument name, declared type)` in declaration order.
    pub arguments: Vec<(String, String)>,
}

/// One model as Python's metadata checks read it.
#[derive(Clone, Debug)]
pub struct MetadataModel {
    pub name: String,
    pub query_sql: String,
    pub authored_sql: String,
    /// False when the model opts out of SQL analysis or was never binding-validated.
    pub checked: bool,
    /// Whether the model references a UDF or table function.
    pub calls_functions: bool,
    /// `(config key, column names)` checked against the model's own shape, in Python's order.
    pub references: Vec<(String, Vec<String>)>,
    /// `(upstream, column names)` of `cursor_inputs`, in Python's dict order.
    pub cursor_inputs: Vec<(String, Vec<String>)>,
    pub cursor: Option<String>,
    pub cursor_type: Option<String>,
    /// The model's schema audits, model-level ones first, in Python's order.
    pub audits: Vec<MetadataAudit>,
}

/// One accepted value of an `accepted_values` audit, by Python type.
#[derive(Clone, Debug, PartialEq)]
pub enum AuditValue {
    Null,
    Bool(bool),
    /// An `int` or `float`, as `str(value)`.
    Number(String),
    Text(String),
    /// Any other object, which keeps the audit from being checked.
    Other,
}

/// One schema audit as the metadata checks read it.
#[derive(Clone, Debug, PartialEq)]
pub struct MetadataAudit {
    /// The schema column the audit is attached to, if any.
    pub column: Option<String>,
    pub definition: String,
    /// The `expression` argument, when it is a string.
    pub expression: Option<String>,
    /// `str(arguments.get("to", ""))`.
    pub target: String,
    /// `str(arguments.get("field", ""))`.
    pub field: String,
    /// The `values` argument, when it is a list or tuple.
    pub values: Option<Vec<AuditValue>>,
}

/// One schema audit diagnostic, located at its name in the model's authored SQL.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuditFinding {
    pub code: String,
    pub message: String,
    pub line: i64,
    pub column: i64,
    pub is_error: bool,
}

/// One source's cursor column and file text, shared with the other sources of its file.
#[derive(Clone, Debug)]
pub struct MetadataSource {
    pub name: String,
    /// The cursor column, when it is set and non-empty.
    pub cursor_column: Option<String>,
    pub contents: Arc<str>,
}

/// One model SQL test's shared file text and its CTEs with their inferred column names.
#[derive(Clone, Debug)]
pub struct MetadataSqlTest {
    pub contents: Arc<str>,
    pub ctes: Vec<(String, Vec<String>)>,
}

/// Python's `get_semantic_metadata_diagnostics` inputs, apart from resource SQL.
#[derive(Clone, Debug)]
pub struct MetadataRequest {
    pub dialect: Option<String>,
    /// The inference profile's `quoted_identifiers_ignore_case`.
    pub quoted_ignore_case: bool,
    /// The inference profile's declared function return types.
    pub return_types: Vec<(String, String)>,
    pub functions: Vec<MetadataFunction>,
    /// Closed relation shapes in Python's dict order.
    pub shapes: Vec<(String, Vec<(String, String)>)>,
    pub models: Vec<MetadataModel>,
    pub sources: Vec<MetadataSource>,
    pub sql_tests: Vec<MetadataSqlTest>,
}

/// One metadata error located in its resource's text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MetadataFinding {
    pub code: &'static str,
    pub message: String,
    pub line: i64,
    pub column: i64,
}

/// One model's function errors, which precede its audits, and its config reference errors.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelMetadataFindings {
    pub functions: Vec<MetadataFinding>,
    /// Schema audit findings, which follow function errors and precede reference errors.
    pub audits: Vec<AuditFinding>,
    pub references: Vec<MetadataFinding>,
}

/// The metadata errors per resource, and the types whose normalization fell back to text.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct MetadataOutcome {
    pub models: Vec<ModelMetadataFindings>,
    /// `(source index, error)`.
    pub sources: Vec<(usize, MetadataFinding)>,
    /// `(SQL test index, error, end column)`.
    pub sql_tests: Vec<(usize, MetadataFinding, i64)>,
    pub fallback_types: Vec<String>,
}

/// The kind of resource owning checked SQL, by Python's `CompiledResourceType` value.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ResourceSqlKind {
    Audit,
    SqlTest,
    Model,
}

/// One compiled audit as the resource SQL checks read it.
#[derive(Clone, Debug)]
pub struct AuditSqlInput {
    pub name: String,
    pub definition_name: String,
    /// `(target kind, target name)` the audit is attached to.
    pub attached_target: Option<(String, String)>,
    pub attached_column: Option<String>,
    /// Whether the audit file lives under the `<built-in>` root.
    pub built_in: bool,
    pub path: String,
    pub contents: Arc<str>,
    /// `(compiled SQL, authored SQL)` of the body, measure and evidence queries.
    pub bodies: Vec<(Option<String>, Option<String>)>,
    /// Whether the AUDIT header sets `sql_analysis false`.
    pub opts_out: bool,
    pub relations: Vec<String>,
}

/// One compiled SQL test as the resource SQL checks read it.
#[derive(Clone, Debug)]
pub struct SqlTestSqlInput {
    pub name: String,
    pub expected_model_names: Vec<String>,
    pub path: String,
    pub contents: Arc<str>,
    pub sql_body: String,
    pub authored_body: String,
    pub opts_out: bool,
}

/// One SQL hook of a model: its config key, index, statement, named file and definition.
#[derive(Clone, Debug)]
pub struct HookSqlInput {
    pub key: String,
    pub index: usize,
    pub statement: String,
    pub hook_path: Option<String>,
    pub definition: Option<String>,
    pub relations: Vec<String>,
}

/// One model's SQL hooks as the resource SQL checks read them.
#[derive(Clone, Debug)]
pub struct HookModelInput {
    pub name: String,
    pub path: String,
    pub authored_sql: Arc<str>,
    pub analysis_disabled: bool,
    pub hooks: Vec<HookSqlInput>,
}

/// Python's `get_resource_sql_diagnostics` inputs as plain data.
#[derive(Clone, Debug)]
pub struct ResourceSqlRequest {
    pub dialect: Option<String>,
    pub quoted_ignore_case: bool,
    pub require_sql_analysis: bool,
    /// Closed relation shapes in Python's dict order.
    pub shapes: Vec<(String, Vec<(String, String)>)>,
    pub audits: Vec<AuditSqlInput>,
    pub sql_tests: Vec<SqlTestSqlInput>,
    pub models: Vec<HookModelInput>,
    /// `(relative path, contents)` of each SQL hook file.
    pub hook_files: Vec<(String, Arc<str>)>,
}

/// A resource SQL finding's authored start and, when it covers text, its end.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ResourceSpan {
    pub line: i64,
    pub column: i64,
    pub end_line: Option<i64>,
    pub end_column: Option<i64>,
}

impl ResourceSpan {
    /// A span that marks only its start.
    pub fn start(line: i64, column: i64) -> Self {
        Self {
            line,
            column,
            end_line: None,
            end_column: None,
        }
    }
}

/// A located resource SQL finding, or a rejected `sql_analysis false` with its note.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceSqlDiagnostic {
    pub kind: ResourceSqlKind,
    pub resource_name: String,
    pub is_error: bool,
    pub code: String,
    pub message: String,
    pub path: String,
    pub span: ResourceSpan,
    pub note: Option<String>,
    pub help: Option<String>,
}

/// Why the resource SQL checks stop: Python's error for the same input, or an internal failure.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ResourceSqlFailure {
    /// The `CompileInputError` cursor intrinsic replacement raises.
    CursorIntrinsic(String),
    /// The `ValueError` analysis normalization raises.
    Normalization(String),
    /// An internal native failure, raised as `NativeCompilerError`.
    Internal(String),
}
