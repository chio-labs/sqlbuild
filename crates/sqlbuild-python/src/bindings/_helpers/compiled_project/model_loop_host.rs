//! The Python host the loop hands finished models and user-code steps to.

use pyo3::FromPyObject;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple};
use sqlbuild_analysis::compiled_project::main::plain_model_facts::plain_model_facts;
use sqlbuild_analysis::compiled_project::models::{
    CompiledModelFacts, ModelConfigFacts, PlainModel,
};

use crate::bindings::_helpers::compiled_project::model_input_view::{
    ExpansionRecord, InputProjections, ModelInputRecord, SchemaRecord,
};
use crate::bindings::_helpers::compiled_project::model_loop_header::AttachedHeader;
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{
    reference_fact, stripped_values,
};
use crate::bindings::_helpers::compiled_project::project::{
    CONTRACT_KEY, INCREMENTAL_MODE_KEY, materialization, text_value,
};
use crate::bindings::_helpers::compiled_project::project::{
    DeclarationPy, config_values, declarations,
};
use crate::bindings::_helpers::render::declaration_expansion::{
    ExpandedDeclarations, ScannedReference, span_rows,
};
use crate::bindings::_helpers::render::macro_call_rows::{SpanRow, span_row};
use crate::bindings::_helpers::render::macro_expansion::ExpansionOutput;

const HEADER_KEYS_ATTRIBUTE: &str = "model_header_keys";
const LAYER_SCHEMA_ATTRIBUTE: &str = "layer_schema";
const VALUES_ARGUMENT: &str = "values";
const ENUMS_ARGUMENT: &str = "enums";
const CONSTANTS_ARGUMENT: &str = "constants";
const LOCAL_ENUMS_ATTRIBUTE: &str = "local_enums";
const LOCAL_CONSTANTS_ATTRIBUTE: &str = "local_constants";
const NAME_ATTRIBUTE: &str = "name";

/// `((name, POSIX path, relative path, file path), column locations, query, contents, scan)`.
#[derive(FromPyObject)]
pub(crate) struct ModelLoopRow(
    pub(crate) (String, String, String, String),
    /// Header column locations, header values, and the model's own enums and constants.
    pub(crate) (Py<PyDict>, Py<PyDict>, Py<PyAny>, Py<PyAny>),
    pub(crate) String,
    pub(crate) String,
    pub(crate) Option<(Vec<ScannedReference>, Option<u8>)>,
    /// The `@@`-interpolated query, its template reads, its error, and its substitution spans.
    pub(crate) InterpolationRow,
    /// The discovered model file, owned by the discovery inputs.
    pub(crate) Py<PyAny>,
);
/// `(interpolated query, template reads, error, substitution spans)`.
pub(crate) type InterpolationRow = (String, Vec<(String, String)>, Option<String>, Vec<SpanRow>);
/// `(kind, name, package, call argument count)`.
pub(crate) type ReferenceRow = (String, String, Option<String>, Option<usize>);

/// One model the native loop finished, before the host builds its Python view.
pub(crate) struct FinishedModel<'py> {
    pub(crate) config: Bound<'py, PyAny>,
    /// The hook-expanded config values, header metadata still included.
    pub(crate) values: Bound<'py, PyDict>,
    pub(crate) query_sql: String,
    pub(crate) header: AttachedHeader<'py>,
    pub(crate) references: Vec<ReferenceRow>,
    pub(crate) declarations: ExpandedDeclarations<'py>,
    /// Whether the SQL is analysed, and where a rejected `sql_analysis false` was authored.
    pub(crate) analysis: (bool, Option<Bound<'py, PyAny>>),
    /// The usages of the model's named schema and Python hooks, recorded after its hook usages.
    pub(crate) named_usages: Vec<Bound<'py, PyAny>>,
    /// The query's macro expansion, when it calls macros.
    pub(crate) macros: Option<ExpansionOutput>,
}

/// The Python classes a finished model's record is built with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct RecordClasses<'py> {
    /// `dataclasses.replace`.
    replace: Bound<'py, PyAny>,
    /// `declaration_rows`, the facts rows of the model's local enums and constants.
    declaration_rows: Bound<'py, PyAny>,
}

/// What the loop knows about a finished model besides its loop row.
pub(crate) struct RecordInputs<'a, 'py> {
    pub(crate) classes: &'a RecordClasses<'py>,
    /// The visible declarations, for the model's own enums and constants.
    pub(crate) visible: &'a Bound<'py, PyAny>,
}

/// A natively finished model's input record, and the facts the project retains.
pub(crate) fn finished_record<'py>(
    inputs: &RecordInputs<'_, 'py>,
    row: ModelLoopRow,
    finished: FinishedModel<'py>,
) -> PyResult<(ModelInputRecord, CompiledModelFacts)> {
    let py: Python<'py> = inputs.visible.py();
    let ModelLoopRow(
        (name, relative_path, _, _),
        _,
        authored_query_sql,
        authored_sql,
        _,
        (interpolated_sql, _, _, interpolation_spans),
        model_file,
    ) = row;
    let stripped: Bound<'py, PyDict> = stripped_values(py, &finished.values)?;
    let mut usages: Vec<Bound<'py, PyAny>> = finished.declarations.usages;
    if let Some(schema) = &finished.header.schema {
        usages.extend(schema.generated_usages.iter().cloned());
    }
    let enum_columns: Vec<String> = match &finished.header.schema {
        Some(schema) => schema.enum_columns.keys().extract()?,
        None => Vec::new(),
    };
    let local_enums: Bound<'py, PyTuple> =
        dict_values(&inputs.visible.getattr(LOCAL_ENUMS_ATTRIBUTE)?)?;
    let local_constants: Bound<'py, PyTuple> =
        dict_values(&inputs.visible.getattr(LOCAL_CONSTANTS_ATTRIBUTE)?)?;
    let rows_arguments: Bound<'py, PyDict> = PyDict::new(py);
    rows_arguments.set_item(ENUMS_ARGUMENT, &local_enums)?;
    rows_arguments.set_item(CONSTANTS_ARGUMENT, &local_constants)?;
    let (enums, constants): (Vec<DeclarationPy<'py>>, Vec<DeclarationPy<'py>>) = inputs
        .classes
        .declaration_rows
        .call((), Some(&rows_arguments))?
        .extract()?;
    let replaced: Bound<'py, PyDict> = PyDict::new(py);
    replaced.set_item(VALUES_ARGUMENT, &stripped)?;
    let config: Bound<'py, PyAny> = inputs
        .classes
        .replace
        .call((&finished.config,), Some(&replaced))?;
    let mut declaration_usages: Vec<Bound<'py, PyAny>> = unique(py, usages)?;
    declaration_usages.extend(finished.named_usages);
    let (macro_sql, macro_spans, macro_deps, macro_usages) = match finished.macros {
        Some(macros) => {
            let mut names: Vec<String> = Vec::new();
            for dependency in unique(
                py,
                macros
                    .dependencies
                    .into_iter()
                    .map(|item| item.into_bound(py))
                    .collect(),
            )? {
                names.push(dependency.getattr(NAME_ATTRIBUTE)?.extract()?);
            }
            (
                macros.sql,
                macros
                    .spans
                    .into_iter()
                    .map(span_row)
                    .collect::<Vec<SpanRow>>(),
                names,
                unique(
                    py,
                    macros
                        .usages
                        .into_iter()
                        .map(|item| item.into_bound(py))
                        .collect(),
                )?,
            )
        }
        None => (
            finished.declarations.spliced.sql.clone(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ),
    };
    let schema: Option<SchemaRecord> = finished.header.schema.as_ref().map(|schema| SchemaRecord {
        description: finished.header.description.clone(),
        columns: schema.columns.clone().unbind(),
        audits: schema.audits.clone().unbind(),
        dynamic_columns: schema.dynamic_columns.clone().unbind(),
        type_enforcement: schema.type_enforcement,
        model_schema: schema.model_schema.clone(),
    });
    let discovered_query: Py<PyString> = model_file
        .bind(py)
        .getattr("query_sql")?
        .downcast_into::<PyString>()?
        .unbind();
    let authored: Py<PyString> = shared_sql(py, &authored_query_sql, &[&discovered_query])?;
    let macro_source: Py<PyString> =
        shared_sql(py, &finished.declarations.spliced.sql, &[&authored])?;
    let expanded: Py<PyString> = shared_sql(py, &macro_sql, &[&authored, &macro_source])?;
    let query: Py<PyString> = shared_sql(
        py,
        &finished.query_sql,
        &[&authored, &macro_source, &expanded],
    )?;
    let record: ModelInputRecord = ModelInputRecord {
        model_file: model_file.clone_ref(py),
        config: config.unbind(),
        query_sql: query,
        macro_source_sql: macro_source,
        references: finished.references.clone(),
        schema,
        sql_validation_enabled: finished.analysis.0,
        rejected_opt_out: finished.analysis.1.map(Bound::unbind),
        enum_declarations: local_enums.unbind(),
        constant_declarations: local_constants.unbind(),
        enum_columns: finished
            .header
            .schema
            .as_ref()
            .map_or_else(|| PyDict::new(py), |schema| schema.enum_columns.clone())
            .unbind(),
        macro_deps,
        macro_usages: PyTuple::new(py, macro_usages)?.unbind(),
        declaration_usages: PyTuple::new(py, unique(py, declaration_usages)?)?.unbind(),
        expansion: ExpansionRecord {
            authored: interpolated_sql == authored_query_sql,
            authored_sql: authored,
            expanded_sql: expanded,
            interpolation_spans,
            declaration_spans: span_rows(&finished.declarations.spliced),
            macro_spans,
        },
        projections: InputProjections::default(),
        compiled: None,
    };
    let (values, encoding_error) = config_values(&stripped);
    let facts: CompiledModelFacts = plain_model_facts(PlainModel {
        name,
        relative_path,
        query_sql: finished.query_sql,
        authored_query_sql,
        authored_sql,
        config: ModelConfigFacts {
            values,
            encoding_error,
            header_keys: finished.config.getattr(HEADER_KEYS_ATTRIBUTE)?.extract()?,
            layer_schema: finished.config.getattr(LAYER_SCHEMA_ATTRIBUTE)?.extract()?,
            contract: text_value(&stripped, CONTRACT_KEY)?,
            materialized: materialization(&stripped)?,
            incremental_mode: text_value(&stripped, INCREMENTAL_MODE_KEY)?,
        },
        schema: finished.header.schema.map(|schema| schema.fact),
        references: finished
            .references
            .into_iter()
            .map(reference_fact)
            .collect(),
        enum_columns,
        enum_declarations: declarations(enums)?,
        constant_declarations: declarations(constants)?,
    });
    Ok((record, facts))
}

/// Reuse an identical immutable spelling already owned by this model.
fn shared_sql(py: Python<'_>, sql: &str, candidates: &[&Py<PyString>]) -> PyResult<Py<PyString>> {
    for candidate in candidates {
        if candidate.bind(py).to_str()? == sql {
            return Ok(candidate.clone_ref(py));
        }
    }
    Ok(PyString::new(py, sql).unbind())
}

/// A dict's values in insertion order.
fn dict_values<'py>(mapping: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    let mapping: &Bound<'py, PyDict> = mapping.downcast()?;
    PyTuple::new(py_of(mapping), mapping.values())
}

fn py_of<'py>(mapping: &Bound<'py, PyDict>) -> Python<'py> {
    mapping.py()
}

/// `dict.fromkeys(items)`: each item once, first occurrence first, by Python equality.
fn unique<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let seen: Bound<'py, PyDict> = PyDict::new(py);
    for item in items {
        seen.set_item(item, py.None())?;
    }
    Ok(seen.keys().into_iter().collect())
}
