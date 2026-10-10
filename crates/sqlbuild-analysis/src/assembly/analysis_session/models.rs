//! Plain-data request, deferrals and outcomes of the native model analysis session.

use std::collections::HashMap;
use std::sync::Arc;

use rayon::ThreadPool;
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use crate::assembly::analysis_session::_helpers::mappings::ShapeTable;
use crate::assembly::analysis_session::types::{NullabilityCallback, OutputSources, Pairs, Shapes};
use crate::semantic_validation::types::DiagnosticRow;

/// One `ref`, `source`, `seed`, `table_fn` or `udf` call a model's SQL makes.
#[derive(Debug, Clone)]
pub struct ModelReference {
    /// Python's `_analysis_reference_name`.
    pub analysis_name: String,
    /// Whether the call is a `ref`, so names a model the analysis orders by.
    pub model_ref: bool,
}

/// One analysed model, with the facts Python derives from its compile input.
#[derive(Debug, Clone)]
pub struct ModelRequest {
    pub name: String,
    /// Cursor-intrinsic analysis SQL.
    pub query_sql: String,
    pub placeholders: Pairs,
    pub references: Vec<ModelReference>,
    /// Python's `lineage_reference_map`: `(analysis name, resource type, resource name)`.
    pub lineage_references: Vec<(String, String, String)>,
    /// Sorted `binding_relation_names`.
    pub required_names: Vec<String>,
    pub recover_cte_facts: bool,
    /// Whether the SQL names `UNION`, `INTERSECT` or `EXCEPT`, as Python's search decides it.
    pub has_set_operation: bool,
    /// The snapshot validity columns a published shape appends.
    pub snapshot_columns: Option<(String, String)>,
    /// The SQL Python's dynamic pivot proof parses: placeholders replaced by their defaults.
    pub pivot_sql: String,
    pub dynamic_families: Vec<DynamicFamily>,
}

/// One declared family of columns a runtime-dynamic pivot generates.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DynamicFamily {
    pub name: String,
    pub pivot_column: String,
    pub value_column: String,
    pub aggregate: String,
    pub data_type: String,
    pub name_pattern: Option<String>,
}

/// Python's `DynamicColumnContractProof`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractProof {
    pub output_proven: bool,
    pub fixed_columns: Vec<ColumnFact>,
    /// Each family's name and inferred type.
    pub families: Vec<(String, Option<String>)>,
    pub input_relations: Vec<String>,
    pub failure_reason: Option<String>,
    pub bare_dynamic_pivot: bool,
}

/// The relation facts every dynamic pivot proof reads: Python's tables before analysis.
#[derive(Debug, Clone, Default)]
pub struct PivotTables {
    pub dialect: String,
    pub column_types: Shapes,
    pub authoritative_types: Shapes,
    pub column_nullability: Shapes,
    pub families_by_table: Vec<(String, Vec<DynamicFamily>)>,
}

/// One model's pivot SQL and declared families.
#[derive(Debug, Clone, Default)]
pub struct PivotModel {
    pub sql: String,
    pub families: Vec<DynamicFamily>,
}

/// Dynamic pivot proofs for models no session analysed.
#[derive(Debug, Clone, Default)]
pub struct PivotBatchRequest {
    pub tables: PivotTables,
    pub models: Vec<PivotModel>,
}

/// A finished session's pivot tables, analysis pool and model facts, kept for later stages.
#[derive(Debug)]
pub struct FinishedSession {
    pub(crate) tables: PivotTables,
    pub(crate) pool: Result<Arc<ThreadPool>, String>,
    pub(crate) models: HashMap<String, SessionModelFacts>,
}

/// A compiled model's output names and lineage from an analysis the session completed natively.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SessionModelFacts {
    pub columns: Option<Vec<String>>,
    pub lineage: OutputSources,
}

/// A model's dynamic pivot proof: none declared, or proven natively.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PivotOutcome {
    Absent,
    Proof(ContractProof),
}

/// Everything one compile's model analysis reads.
#[derive(Debug, Clone, Default)]
pub struct SessionRequest {
    /// The analysis dialect, `generic` when the adapter names none.
    pub dialect: String,
    /// Whether published shapes keep authored quoting, Python's `inferred_binding_shape` test.
    pub case_sensitive_shapes: bool,
    pub function_return_types: Pairs,
    /// Adapter nullability rules as `(function name, rule id)`.
    pub nullability_rules: Option<Pairs>,
    /// Runs the adapter's own rules, those with the `python` rule id.
    pub nullability_callback: Option<NullabilityCallback>,
    pub rich_type_inference: bool,
    pub column_types: Shapes,
    pub column_nullability: Shapes,
    pub complete_schemas: Shapes,
    /// The Python binding catalog's `schemas` before analysis.
    pub catalog_schemas: Shapes,
    /// Python's `dynamic_families_by_table`, in dict order.
    pub dynamic_families_by_table: Vec<(String, Vec<DynamicFamily>)>,
    pub models: Vec<ModelRequest>,
}

/// One inferred output column; nullability is Python's `InferredNullability` value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ColumnFact {
    pub name: String,
    pub data_type: Option<String>,
    pub nullability: String,
}

/// One compact lineage row with resolved names; codes index Python's enum tuples.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineageRow {
    pub output_column: String,
    pub transform_code: u8,
    pub confidence_code: u8,
    pub sources: Vec<(String, String, String)>,
}

/// Where a model's lineage facts live.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LineageFacts {
    /// Native compact rows.
    Native(Vec<LineageRow>),
    /// Plain lineage facts of a native re-analysis or legacy analysis.
    NativeFacts(Vec<LineageRow>),
}

/// Python's `PolyglotAnalysisResult` for one model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelAnalysis {
    pub analysis_succeeded: bool,
    pub columns: Option<Vec<ColumnFact>>,
    pub lineage: LineageFacts,
    pub has_star: bool,
    pub star_resolved: bool,
    pub binding_diagnostics: Vec<DiagnosticRow>,
    pub binding_validated: bool,
}

/// Python's `ModelSqlAnalysis` for one model, without the placeholders Python keeps.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelOutcome {
    pub analysis: ModelAnalysis,
    pub cleaned_sql: String,
    pub validated_schema: Shapes,
    pub fused_binding_validated: bool,
}

/// The finished run of the session: what Python records from it.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionStep {
    /// Shapes published by the run, in publication order.
    pub publications: Shapes,
    /// Native analysis failures Python logs at debug level.
    pub failures: Vec<String>,
}

/// The session's results once every deferral is answered.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionOutcome {
    pub models: Vec<ModelOutcome>,
    /// Relations the Python binding catalog adds to `schemas`, in order.
    pub schema_additions: Shapes,
    /// Relations whose analysis shapes the Python binding catalog records.
    pub analysis_names: Vec<String>,
    /// Each model's dynamic pivot proof, in request order.
    pub dynamic_contracts: Vec<PivotOutcome>,
}

/// One expression source's shape: inferred, absent, or left to Python.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExpressionShape {
    Inferred(Pairs),
    Absent,
}

/// What expression-source shape inference reads from the inference profile.
#[derive(Debug, Clone, Default)]
pub struct ExpressionShapeRequest {
    pub dialect: String,
    pub case_sensitive_shapes: bool,
    pub function_return_types: Pairs,
    /// Adapter nullability rules as `(function name, rule id)`.
    pub nullability_rules: Option<Pairs>,
    /// Runs the adapter's own rules, those with the `python` rule id.
    pub nullability_callback: Option<NullabilityCallback>,
    pub expressions: Vec<String>,
}

/// Where the session is within its waves.
#[derive(Debug)]
pub(crate) enum Phase {
    Analyze,
    Complete(usize),
    Finish(usize),
    Done,
}

/// How many analysed models a session took from its cache, analysed itself, and stored.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct AnalysisCacheStats {
    pub hits: usize,
    pub misses: usize,
    pub stored: usize,
}

/// A session's per-model analysis cache of finished native outcomes in a store.
#[derive(Debug)]
pub struct AnalysisCache {
    pub(crate) store: NativeStore,
    /// Digest of the session-wide request facts every model key starts with.
    pub(crate) session_digest: ContentDigest,
    pub(crate) keys: Vec<Option<ContentDigest>>,
    pub(crate) hits: Vec<bool>,
    /// Models whose outcome must not be stored: a logged failure or Python's answer.
    /// The whole-table digest each legacy analysis read; its entry also requires it.
    pub(crate) legacy_tables: Vec<Option<ContentDigest>>,
    pub(crate) stats: AnalysisCacheStats,
}

/// One compile's model analysis, advanced phase by phase.
#[derive(Debug)]
pub struct AnalysisSession {
    pub(crate) request: SessionRequest,
    pub(crate) catalog: SessionCatalog,
    pub(crate) dependency_ordered: bool,
    /// Whether models `ref` each other in a cycle, so Python's completion pass is skipped.
    pub(crate) cyclic: bool,
    pub(crate) waves: Vec<Vec<usize>>,
    pub(crate) next_wave: usize,
    pub(crate) available_types: ShapeTable,
    pub(crate) available_nullability: ShapeTable,
    pub(crate) complete_shapes: ShapeTable,
    pub(crate) outcomes: Vec<Option<ModelOutcome>>,
    pub(crate) phase: Phase,
    pub(crate) publications: Shapes,
    pub(crate) failures: Vec<String>,
    pub(crate) cache: Option<AnalysisCache>,
}

/// One query's CTE fact recovery, as Python's compact enrichment runs it.
#[derive(Debug, Clone)]
pub struct CteFactRequest {
    pub cleaned_sql: String,
    pub dialect: String,
    /// Input relation types; every input column's nullability is unknown, as in enrichment.
    pub input_schemas: Shapes,
    pub function_return_types: Pairs,
    /// Adapter nullability rules as `(function name, rule id)`; None where one is not Python's.
    pub nullability_rules: Option<Pairs>,
    /// Whether Python runs `_polyglot_cte_passthrough_facts` past its early return.
    pub recover: bool,
    /// Whether a filter reads NULL, so Python looks for filtered non-null outputs.
    pub null_filter: bool,
}

/// Python's recovered CTE pass-through facts and filtered non-null outputs for one query.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CteFacts {
    pub types: Pairs,
    pub nullability: Pairs,
    /// Sorted direct CTE output names.
    pub direct_outputs: Vec<String>,
    /// Sorted outputs a filter proves non-null.
    pub non_null_outputs: Vec<String>,
}
