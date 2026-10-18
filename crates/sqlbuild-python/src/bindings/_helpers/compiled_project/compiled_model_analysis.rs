//! A compiled model's analysis, kept from the native session and projected on demand.

use std::borrow::Cow;
use std::collections::HashMap;

use pyo3::IntoPyObject;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::assembly::analysis_session::main::resolved_cleaned_sql::resolved_cleaned_sql;
use sqlbuild_analysis::assembly::analysis_session::models::{
    ColumnFact, ContractProof, LineageFacts, LineageRow, ModelOutcome, PivotOutcome,
};
use sqlbuild_analysis::binding_locations::main::locate_binding_diagnostics::locate_binding_diagnostics;
use sqlbuild_analysis::binding_locations::models::{BindingSource, LocatedDiagnostic};
use sqlbuild_analysis::semantic_validation::types::{DiagnosticRow, Expansion};

use crate::bindings::_helpers::analysis_session::session::NativeModelAnalysisSession;
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::compiled_project::compiled_model_view::{
    CompiledViewClasses, InferredRow,
};
use crate::bindings::_helpers::compiled_project::model_input_view::ModelInputRecord;
use crate::bindings::_helpers::discovery::model_file_record::NativeModelFile;
use crate::bindings::_helpers::record_behaviours::lineage_facts::{
    confidence_member, transform_kind_member,
};

const COMPILE_PHASE: &str = "compile";
const MODEL_RESOURCE: &str = "model";

/// `(output proven, fixed columns, (family, inferred type), inputs, failure, bare pivot)`.
pub(crate) type ProofArgument = (
    bool,
    Vec<InferredRow>,
    Vec<(String, Option<String>)>,
    Vec<String>,
    Option<String>,
    bool,
);

/// The session analysis a model was assembled from: the session and its request position.
pub(crate) type SessionArgument = (Py<NativeModelAnalysisSession>, usize);

/// What one model's analysis left for its compiled model.
pub(crate) struct AnalysisRecord {
    pub(crate) inferred: Option<Vec<InferredRow>>,
    lineage: Option<LineageFacts>,
    pub(crate) has_star: bool,
    pub(crate) star_resolved: bool,
    binding: Vec<LocatedDiagnostic>,
    pub(crate) binding_validated: bool,
    pub(crate) proof: Option<ContractProof>,
    projections: AnalysisProjections,
}

/// Python projections of the analysis, each built once on first access.
struct AnalysisProjections {
    lineage: PyOnceLock<Py<PyAny>>,
    binding: PyOnceLock<Py<PyTuple>>,
    proof: PyOnceLock<Py<PyAny>>,
}

impl Default for AnalysisProjections {
    fn default() -> Self {
        Self {
            lineage: PyOnceLock::new(),
            binding: PyOnceLock::new(),
            proof: PyOnceLock::new(),
        }
    }
}

fn inferred_row(column: &ColumnFact) -> InferredRow {
    (
        column.name.clone(),
        column.data_type.clone(),
        column.nullability.clone(),
    )
}

fn proof_fact(argument: ProofArgument) -> ContractProof {
    let (output_proven, fixed, families, input_relations, failure_reason, bare_dynamic_pivot) =
        argument;
    ContractProof {
        output_proven,
        fixed_columns: fixed
            .into_iter()
            .map(|(name, data_type, nullability)| ColumnFact {
                name,
                data_type,
                nullability,
            })
            .collect(),
        families,
        input_relations,
        failure_reason,
        bare_dynamic_pivot,
    }
}

/// The model's analysis: the session's outcome, a failed analysis's fallback columns, the proof.
pub(crate) fn analysis_record(
    py: Python<'_>,
    input: &ModelInputRecord,
    analysis: Option<SessionArgument>,
    (fallback, standalone_proof): (Option<Vec<InferredRow>>, Option<ProofArgument>),
) -> PyResult<AnalysisRecord> {
    let mut record: AnalysisRecord = AnalysisRecord {
        inferred: None,
        lineage: None,
        has_star: false,
        star_resolved: false,
        binding: Vec::new(),
        binding_validated: false,
        proof: standalone_proof.map(proof_fact),
        projections: AnalysisProjections::default(),
    };
    if let Some((session, index)) = analysis {
        let session = session.borrow(py);
        let (outcome, contract): &(ModelOutcome, PivotOutcome) = session.outcome(index)?;
        let analysed = &outcome.analysis;
        if analysed.analysis_succeeded {
            record.inferred = analysed
                .columns
                .as_ref()
                .map(|columns| columns.iter().map(inferred_row).collect());
            record.lineage = Some(analysed.lineage.clone());
            record.has_star = analysed.has_star;
            record.star_resolved = analysed.star_resolved;
        } else {
            record.inferred = fallback;
        }
        if let PivotOutcome::Proof(proof) = contract {
            record.proof = Some(proof.clone());
        }
        record.binding = located(input, outcome)?;
        record.binding_validated = analysed.binding_validated;
    }
    if let Some(proof) = record.proof.as_ref().filter(|proof| proof.output_proven) {
        record.inferred = Some(proof.fixed_columns.iter().map(inferred_row).collect());
        record.has_star = true;
    }
    Ok(record)
}

/// The model's binding diagnostics at their authored locations.
fn located(input: &ModelInputRecord, outcome: &ModelOutcome) -> PyResult<Vec<LocatedDiagnostic>> {
    let rows: &[DiagnosticRow] = &outcome.analysis.binding_diagnostics;
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let cleaned: Cow<'_, str> = resolved_cleaned_sql(outcome).map_err(compiler_error)?;
    let model_file: &NativeModelFile = input.model_file.get();
    let authored: &str = model_file.contents_text();
    let query: &str = model_file.query_text();
    let expansion = &input.expansion;
    let passes: Vec<Vec<Expansion>> = vec![
        expansion.declaration_spans.clone(),
        expansion.macro_spans.clone(),
    ];
    let source: BindingSource<'_> = BindingSource {
        authored,
        query,
        cleaned: &cleaned,
        expansion: expansion
            .authored
            .then_some((&*expansion.expanded_sql, passes.as_slice())),
    };
    locate_binding_diagnostics(rows, &source).map_err(PyValueError::new_err)
}

impl AnalysisRecord {
    /// The session's lineage rows, or `None` when the model kept no lineage.
    pub(crate) fn lineage_rows(&self) -> Option<&[LineageRow]> {
        self.lineage.as_ref().map(|lineage| match lineage {
            LineageFacts::Native(rows) | LineageFacts::NativeFacts(rows) => rows.as_slice(),
        })
    }

    /// The session's lineage as `CompactLineageFacts` or plain facts, or `None`.
    pub(crate) fn lineage_object(
        &self,
        py: Python<'_>,
        classes: &CompiledViewClasses<'_>,
    ) -> PyResult<Py<PyAny>> {
        self.projections
            .lineage
            .get_or_try_init(py, || match &self.lineage {
                None => Ok(py.None()),
                Some(LineageFacts::Native(rows)) => compact_lineage(classes, rows),
                Some(LineageFacts::NativeFacts(rows)) => lineage_facts(classes, rows),
            })
            .map(|lineage| lineage.clone_ref(py))
    }

    /// The number of upstream sources across the model's lineage rows, or `None` without lineage.
    pub(crate) fn lineage_edge_count(&self) -> Option<usize> {
        match &self.lineage {
            None => None,
            Some(LineageFacts::Native(rows) | LineageFacts::NativeFacts(rows)) => {
                Some(rows.iter().map(|row| row.sources.len()).sum())
            }
        }
    }

    /// The model's `CompilerDiagnostic` tuple, built once.
    pub(crate) fn binding_tuple(
        &self,
        py: Python<'_>,
        classes: &CompiledViewClasses<'_>,
        model: (&str, &Bound<'_, PyAny>),
    ) -> PyResult<Py<PyTuple>> {
        self.projections
            .binding
            .get_or_try_init(py, || {
                let mut diagnostics: Vec<Py<PyAny>> = Vec::with_capacity(self.binding.len());
                for diagnostic in &self.binding {
                    diagnostics.push(compiler_diagnostic(classes, diagnostic, model)?);
                }
                Ok::<_, pyo3::PyErr>(PyTuple::new(py, diagnostics)?.unbind())
            })
            .map(|diagnostics| diagnostics.clone_ref(py))
    }

    /// The model's `DynamicColumnContractProof`, or `None`.
    pub(crate) fn proof_object(
        &self,
        py: Python<'_>,
        classes: &CompiledViewClasses<'_>,
    ) -> PyResult<Py<PyAny>> {
        self.projections
            .proof
            .get_or_try_init(py, || match &self.proof {
                None => Ok(py.None()),
                Some(proof) => contract_proof(classes, proof),
            })
            .map(|proof| proof.clone_ref(py))
    }
}

/// `compact_lineage`: rows over a per-model string pool, sources pooled before each output.
fn compact_lineage(classes: &CompiledViewClasses<'_>, rows: &[LineageRow]) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = classes.compact_lineage_facts.py();
    let mut pool: StringPool<'_> = StringPool::default();
    let mut compact: Vec<Bound<'_, PyTuple>> = Vec::with_capacity(rows.len());
    for row in rows {
        let mut sources: Vec<(usize, usize, usize)> = Vec::with_capacity(row.sources.len());
        for (resource_type, resource_name, column_name) in &row.sources {
            let kind: usize = pool.index(resource_type);
            let name: usize = pool.index(resource_name);
            sources.push((kind, name, pool.index(column_name)));
        }
        let output: usize = pool.index(&row.output_column);
        compact.push(
            (
                output,
                row.transform_code,
                row.confidence_code,
                PyTuple::new(py, sources)?,
            )
                .into_pyobject(py)?,
        );
    }
    let fields: Bound<'_, PyDict> = PyDict::new(py);
    fields.set_item("string_pool", PyTuple::new(py, pool.ordered)?)?;
    fields.set_item("rows", PyTuple::new(py, compact)?)?;
    Ok(classes
        .compact_lineage_facts
        .call((), Some(&fields))?
        .unbind())
}

/// Python's `pool.setdefault(text, len(pool))`, remembering first-seen order.
#[derive(Default)]
struct StringPool<'a> {
    indexes: HashMap<&'a str, usize>,
    ordered: Vec<&'a str>,
}

impl<'a> StringPool<'a> {
    fn index(&mut self, text: &'a str) -> usize {
        if let Some(index) = self.indexes.get(text) {
            return *index;
        }
        self.ordered.push(text);
        self.indexes.insert(text, self.ordered.len() - 1);
        self.ordered.len() - 1
    }
}

/// `lineage_facts`: plain `CompiledLineageColumnFact`s of a re-analysis.
fn lineage_facts(classes: &CompiledViewClasses<'_>, rows: &[LineageRow]) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = classes.lineage_column_fact.py();
    let mut facts: Vec<Py<PyAny>> = Vec::with_capacity(rows.len());
    for row in rows {
        let mut sources: Vec<Py<PyAny>> = Vec::with_capacity(row.sources.len());
        for (resource_type, resource_name, column_name) in &row.sources {
            let fields: Bound<'_, PyDict> = PyDict::new(py);
            fields.set_item("resource_type", resource_type)?;
            fields.set_item("resource_name", resource_name)?;
            fields.set_item("column_name", column_name)?;
            sources.push(
                classes
                    .lineage_source_fact
                    .call((), Some(&fields))?
                    .unbind(),
            );
        }
        let fields: Bound<'_, PyDict> = PyDict::new(py);
        fields.set_item("output_column", &row.output_column)?;
        fields.set_item("upstream_columns", PyTuple::new(py, sources)?)?;
        fields.set_item(
            "transform_kind",
            transform_kind_member(py, usize::from(row.transform_code))?,
        )?;
        fields.set_item(
            "confidence",
            confidence_member(py, usize::from(row.confidence_code))?,
        )?;
        facts.push(
            classes
                .lineage_column_fact
                .call((), Some(&fields))?
                .unbind(),
        );
    }
    Ok(PyTuple::new(py, facts)?.into_any().unbind())
}

/// One located binding diagnostic as the model's `CompilerDiagnostic`.
fn compiler_diagnostic(
    classes: &CompiledViewClasses<'_>,
    diagnostic: &LocatedDiagnostic,
    (name, path): (&str, &Bound<'_, PyAny>),
) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = path.py();
    let location: Option<Bound<'_, PyAny>> = match &diagnostic.location {
        None => None,
        Some(span) => {
            let fields: Bound<'_, PyDict> = PyDict::new(py);
            fields.set_item("path", path)?;
            fields.set_item("line", span.line)?;
            fields.set_item("column", span.column)?;
            fields.set_item("end_line", span.end_line)?;
            fields.set_item("end_column", span.end_column)?;
            Some(classes.source_location.call((), Some(&fields))?)
        }
    };
    let fields: Bound<'_, PyDict> = PyDict::new(py);
    fields.set_item("phase", COMPILE_PHASE)?;
    fields.set_item("severity", &diagnostic.severity)?;
    fields.set_item("code", &diagnostic.code)?;
    fields.set_item("message", &diagnostic.message)?;
    fields.set_item("resource_type", MODEL_RESOURCE)?;
    fields.set_item("resource_name", name)?;
    fields.set_item("path", path)?;
    fields.set_item("line", diagnostic.line)?;
    fields.set_item("column", diagnostic.column)?;
    fields.set_item("location", location)?;
    Ok(classes
        .compiler_diagnostic
        .call((), Some(&fields))?
        .unbind())
}

/// `contract_proof`: the session's dynamic pivot proof as Python's.
fn contract_proof(classes: &CompiledViewClasses<'_>, proof: &ContractProof) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = classes.contract_proof.py();
    let mut fixed: Vec<Py<PyAny>> = Vec::with_capacity(proof.fixed_columns.len());
    for column in &proof.fixed_columns {
        let fields: Bound<'_, PyDict> = PyDict::new(py);
        fields.set_item("name", &column.name)?;
        fields.set_item("type", &column.data_type)?;
        fields.set_item(
            "nullability",
            classes.nullability.call1((&column.nullability,))?,
        )?;
        fixed.push(classes.inferred_column.call((), Some(&fields))?.unbind());
    }
    let mut families: Vec<Py<PyAny>> = Vec::with_capacity(proof.families.len());
    for (name, inferred_type) in &proof.families {
        let fields: Bound<'_, PyDict> = PyDict::new(py);
        fields.set_item("name", name)?;
        fields.set_item("inferred_type", inferred_type)?;
        families.push(classes.family_proof.call((), Some(&fields))?.unbind());
    }
    let fields: Bound<'_, PyDict> = PyDict::new(py);
    fields.set_item("output_proven", proof.output_proven)?;
    fields.set_item("fixed_columns", PyTuple::new(py, fixed)?)?;
    fields.set_item("families", PyTuple::new(py, families)?)?;
    fields.set_item("input_relations", PyTuple::new(py, &proof.input_relations)?)?;
    fields.set_item("failure_reason", &proof.failure_reason)?;
    fields.set_item("bare_dynamic_pivot", proof.bare_dynamic_pivot)?;
    Ok(classes.contract_proof.call((), Some(&fields))?.unbind())
}
