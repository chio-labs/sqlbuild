//! Plain-data requests and outcomes of native semantic completion.

use std::collections::{HashMap, HashSet};

use crate::semantic_checks::types::CompletedParts;

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

/// Why native semantic completion hands a stage back to Python.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticDeferral {
    UnsupportedDialect,
    UnreadableSql,
    NonAsciiText,
    UnexpectedPosition,
    UnsupportedType,
    NativeFailure,
}

impl SemanticDeferral {
    /// The deferral kind recorded for the harness.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::UnsupportedDialect => "unsupported_dialect",
            Self::UnreadableSql => "unreadable_sql",
            Self::NonAsciiText => "non_ascii_text",
            Self::UnexpectedPosition => "unexpected_position",
            Self::UnsupportedType => "unsupported_type",
            Self::NativeFailure => "native_failure",
        }
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

/// Type recovery's first step: nothing to recover, a plan, or a deferral.
#[derive(Clone, Debug)]
pub enum TypeRecoveryStep {
    Unchanged,
    Planned(TypeRecoveryPlan),
    Deferred(SemanticDeferral),
}

impl TypeRecoveryStep {
    /// `unchanged`, `planned` or `deferred`.
    pub fn status(&self) -> &'static str {
        match self {
            Self::Unchanged => "unchanged",
            Self::Planned(_) => "planned",
            Self::Deferred(_) => "deferred",
        }
    }

    /// The deferral kind, when the stage is handed back to Python.
    pub fn deferral(&self) -> Option<&'static str> {
        match self {
            Self::Deferred(deferral) => Some(deferral.as_str()),
            _ => None,
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

/// Recovery, explanation and opt-out rejection, or a deferral.
#[derive(Clone, Debug)]
pub enum CompletionOutcome {
    Completed {
        diagnostics: Vec<CompletedDiagnostic>,
        /// Indexes into `diagnostics` per model, or `None` when models keep their bindings.
        model_bindings: Option<Vec<Vec<usize>>>,
        order: Vec<FinalDiagnostic>,
    },
    Deferred(SemanticDeferral),
}

impl CompletionOutcome {
    /// `(deferral kind, completed parts)`: exactly one side is set.
    pub fn into_parts(self) -> (Option<&'static str>, Option<CompletedParts>) {
        match self {
            Self::Completed {
                diagnostics,
                model_bindings,
                order,
            } => (None, Some((diagnostics, model_bindings, order))),
            Self::Deferred(deferral) => (Some(deferral.as_str()), None),
        }
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
}

/// One source's cursor column and file text.
#[derive(Clone, Debug)]
pub struct MetadataSource {
    pub name: String,
    /// The cursor column, when it is set and non-empty.
    pub cursor_column: Option<String>,
    pub contents: String,
}

/// One model SQL test's file text and its CTEs with their inferred column names.
#[derive(Clone, Debug)]
pub struct MetadataSqlTest {
    pub contents: String,
    pub ctes: Vec<(String, Vec<String>)>,
}

/// Python's `get_semantic_metadata_diagnostics` inputs, apart from audits and resource SQL.
#[derive(Clone, Debug)]
pub struct MetadataRequest {
    pub dialect: Option<String>,
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
