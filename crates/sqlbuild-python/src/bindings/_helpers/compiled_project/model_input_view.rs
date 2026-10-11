//! A model's compile input, read from the native compiled project that owns it.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{FromPyObject, IntoPyObject, pyclass, pymethods};

use crate::bindings::_helpers::compiled_project::compiled_model_view::{
    CompiledArguments, CompiledRecord, CompiledViewClasses, NativeCompiledModel, compiled_record,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::render::declaration_expansion::SpanRow;
use crate::bindings::_helpers::rules::relation_keys::{RelationKeyRow, relation_key_row};

const MODEL_RELATION_KIND: &str = "ref";

/// The Python classes a model input's projected attributes are built with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct InputViewClasses<'py> {
    pub(crate) compiled: CompiledViewClasses<'py>,
    sql_reference: Bound<'py, PyAny>,
    reference_kind: Bound<'py, PyAny>,
    schema_model_entry: Bound<'py, PyAny>,
    sql_expansion: Bound<'py, PyAny>,
    expansion_span: Bound<'py, PyAny>,
}

/// A model's attached header schema; its specs carry user-authored audit arguments.
pub(crate) struct SchemaRecord {
    pub(crate) description: Option<String>,
    pub(crate) columns: Py<PyTuple>,
    pub(crate) audits: Py<PyTuple>,
    pub(crate) dynamic_columns: Py<PyTuple>,
    pub(crate) type_enforcement: bool,
    pub(crate) model_schema: Option<String>,
}

/// The expansion passes of a model's query, from authored text to expanded SQL.
pub(crate) struct ExpansionRecord {
    /// The authored query below the header.
    pub(crate) authored_sql: Py<PyString>,
    /// The declaration- and macro-expanded SQL before canonicalisation.
    pub(crate) expanded_sql: Py<PyString>,
    pub(crate) interpolation_spans: Vec<SpanRow>,
    pub(crate) declaration_spans: Vec<SpanRow>,
    pub(crate) macro_spans: Vec<SpanRow>,
    /// Whether interpolation left the authored query unchanged.
    pub(crate) authored: bool,
}

/// What the model loop finished for one model beyond its facts; handles carry user values.
pub(crate) struct ModelInputRecord {
    /// The discovered model file, owned by the discovery inputs.
    pub(crate) model_file: Py<PyAny>,
    /// The resolved config, whose values hold user values.
    pub(crate) config: Py<PyAny>,
    /// Immutable text shared with discovery, expansions and every Python-facing projection.
    pub(crate) query_sql: Py<PyString>,
    pub(crate) macro_source_sql: Py<PyString>,
    pub(crate) references: Vec<ReferenceRow>,
    pub(crate) schema: Option<SchemaRecord>,
    pub(crate) sql_validation_enabled: bool,
    pub(crate) rejected_opt_out: Option<Py<PyAny>>,
    /// The model's own enums and constants, whose values are user values.
    pub(crate) enum_declarations: Py<PyTuple>,
    pub(crate) constant_declarations: Py<PyTuple>,
    pub(crate) enum_columns: Py<PyDict>,
    pub(crate) macro_deps: Vec<String>,
    /// Usage records, the identities the scope index is built from.
    pub(crate) macro_usages: Py<PyTuple>,
    pub(crate) declaration_usages: Py<PyTuple>,
    pub(crate) expansion: ExpansionRecord,
    /// Attribute projections built on first access, shared by every view of the model.
    pub(crate) projections: InputProjections,
    /// What assembly and the semantic checks finished, once the model is assembled.
    pub(crate) compiled: Option<CompiledRecord>,
}

/// A model input's Python attribute projections, each built once on first access.
pub(crate) struct InputProjections {
    references: PyOnceLock<Py<PyTuple>>,
    schema_entry: PyOnceLock<Py<PyAny>>,
    sql_expansion: PyOnceLock<Py<PyAny>>,
    lint_expansion: PyOnceLock<Py<PyAny>>,
}

impl Default for InputProjections {
    fn default() -> Self {
        Self {
            references: PyOnceLock::new(),
            schema_entry: PyOnceLock::new(),
            sql_expansion: PyOnceLock::new(),
            lint_expansion: PyOnceLock::new(),
        }
    }
}

/// One model's compile input, projected from the owner on demand.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelInput {
    owner: Py<NativeCompiledProject>,
    index: usize,
}

impl NativeModelInput {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self { owner, index }
    }

    fn read<'py, T>(
        &self,
        py: Python<'py>,
        read: impl FnOnce(&ModelInputRecord, Python<'py>) -> PyResult<T>,
    ) -> PyResult<T> {
        read_input(&self.owner, self.index, py, read)
    }
}

/// Read the input record at `index` of `owner`.
pub(crate) fn read_input<'py, T>(
    owner: &Py<NativeCompiledProject>,
    index: usize,
    py: Python<'py>,
    read: impl FnOnce(&ModelInputRecord, Python<'py>) -> PyResult<T>,
) -> PyResult<T> {
    let owner = owner.bind(py).borrow();
    read(owner.input(index)?, py)
}

/// The classes the owner's views project attributes with.
pub(crate) fn view_classes<'py>(
    owner: &Py<NativeCompiledProject>,
    py: Python<'py>,
) -> PyResult<InputViewClasses<'py>> {
    owner.bind(py).borrow().input_classes(py)?.extract()
}

#[pymethods]
impl NativeModelInput {
    #[getter]
    fn model_file(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.read(py, |record, py| Ok(record.model_file.clone_ref(py)))
    }

    #[getter]
    fn config(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.read(py, |record, py| Ok(record.config.clone_ref(py)))
    }

    #[getter]
    fn query_sql(&self, py: Python<'_>) -> PyResult<Py<PyString>> {
        self.read(py, |record, py| Ok(record.query_sql.clone_ref(py)))
    }

    #[getter]
    fn macro_source_sql(&self, py: Python<'_>) -> PyResult<Py<PyString>> {
        self.read(py, |record, py| Ok(record.macro_source_sql.clone_ref(py)))
    }

    #[getter]
    fn references(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, _| references(&classes, record))
    }

    #[getter]
    fn schema_entry(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, _| schema_entry(&classes, record))
    }

    /// Each reference as `(kind, name, package, call argument count)`.
    #[getter]
    fn reference_rows(&self, py: Python<'_>) -> PyResult<Vec<ReferenceRow>> {
        self.read(py, |record, _| Ok(record.references.clone()))
    }

    /// The model's declared key facts, for deriving its unique keys.
    #[getter]
    fn relation_key_row(&self, py: Python<'_>) -> PyResult<RelationKeyRow> {
        self.read(py, model_relation_key_row)
    }

    /// The name of the schema entry attached to the model, or `None`.
    #[getter]
    fn attached_schema_name(&self, py: Python<'_>) -> PyResult<Option<String>> {
        self.read(py, |record, py| attached_schema_name(record, py))
    }

    #[getter]
    fn schema_file(&self, py: Python<'_>) -> Py<PyAny> {
        py.None()
    }

    #[getter]
    fn sql_validation_enabled(&self, py: Python<'_>) -> PyResult<bool> {
        self.read(py, |record, _| Ok(record.sql_validation_enabled))
    }

    #[getter]
    fn rejected_sql_analysis_opt_out(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.read(py, |record, py| Ok(rejected_opt_out(record, py)))
    }

    #[getter]
    fn enum_declarations(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        self.read(py, |record, py| Ok(record.enum_declarations.clone_ref(py)))
    }

    #[getter]
    fn constant_declarations(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        self.read(py, |record, py| {
            Ok(record.constant_declarations.clone_ref(py))
        })
    }

    #[getter]
    fn enum_columns(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        self.read(py, |record, py| Ok(record.enum_columns.clone_ref(py)))
    }

    #[getter]
    fn macro_deps<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        self.read(py, |record, py| PyTuple::new(py, &record.macro_deps))
    }

    #[getter]
    fn macro_usages(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        self.read(py, |record, py| Ok(record.macro_usages.clone_ref(py)))
    }

    #[getter]
    fn declaration_usages(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        self.read(py, |record, py| Ok(record.declaration_usages.clone_ref(py)))
    }

    /// Record what assembly finished for the model; return its compiled model view.
    fn compiled_model(
        &self,
        py: Python<'_>,
        arguments: CompiledArguments,
    ) -> PyResult<NativeCompiledModel> {
        let mut owner = self.owner.bind(py).borrow_mut();
        let record: &mut ModelInputRecord = owner.input_mut(self.index)?;
        let name: String = record
            .model_file
            .bind(py)
            .getattr("file_path")?
            .getattr("stem")?
            .extract()?;
        record.compiled = Some(compiled_record(py, record, &name, arguments)?);
        Ok(NativeCompiledModel::new(
            self.owner.clone_ref(py),
            self.index,
        ))
    }

    /// The authored-to-expanded passes, when interpolation left the authored query unchanged.
    #[getter]
    fn sql_expansion(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, _| authored_expansion(&classes, record))
    }

    /// The whole expansion, variables included, which early SQL lint reuses.
    #[getter]
    fn lint_expansion(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, py| {
            record
                .projections
                .lint_expansion
                .get_or_try_init(py, || {
                    let expansion: &ExpansionRecord = &record.expansion;
                    expansion_object(
                        &classes,
                        expansion,
                        &[
                            &expansion.interpolation_spans,
                            &expansion.declaration_spans,
                            &expansion.macro_spans,
                        ],
                    )
                })
                .map(|expansion| expansion.clone_ref(py))
        })
    }
}

/// The authored-to-expanded passes, when interpolation left the authored query unchanged.
pub(crate) fn authored_expansion(
    classes: &InputViewClasses<'_>,
    record: &ModelInputRecord,
) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = classes.sql_expansion.py();
    record
        .projections
        .sql_expansion
        .get_or_try_init(py, || {
            let expansion: &ExpansionRecord = &record.expansion;
            if !expansion.authored {
                return Ok(py.None());
            }
            expansion_object(
                classes,
                expansion,
                &[&expansion.declaration_spans, &expansion.macro_spans],
            )
        })
        .map(|expansion| expansion.clone_ref(py))
}

/// Where a rejected `sql_analysis false` was authored, or `None`.
pub(crate) fn rejected_opt_out(record: &ModelInputRecord, py: Python<'_>) -> Py<PyAny> {
    record
        .rejected_opt_out
        .as_ref()
        .map_or_else(|| py.None(), |location| location.clone_ref(py))
}

/// The model's `CompileSqlReference` tuple, built once.
pub(crate) fn references(
    classes: &InputViewClasses<'_>,
    record: &ModelInputRecord,
) -> PyResult<Py<PyTuple>> {
    reference_tuple(classes, &record.references, &record.projections.references)
}

/// `CompileSqlReference` records of `rows`, built once into `cache`.
pub(crate) fn reference_tuple(
    classes: &InputViewClasses<'_>,
    rows: &[ReferenceRow],
    cache: &PyOnceLock<Py<PyTuple>>,
) -> PyResult<Py<PyTuple>> {
    let py: Python<'_> = classes.sql_reference.py();
    cache
        .get_or_try_init(py, || {
            let mut references: Vec<Bound<'_, PyAny>> = Vec::with_capacity(rows.len());
            for (kind, name, package, count) in rows {
                let fields: Bound<'_, PyDict> = PyDict::new(py);
                fields.set_item("ref_kind", classes.reference_kind.call1((kind,))?)?;
                fields.set_item("ref_name", name)?;
                fields.set_item("ref_package", package)?;
                fields.set_item("call_argument_count", count)?;
                references.push(classes.sql_reference.call((), Some(&fields))?);
            }
            Ok::<_, pyo3::PyErr>(PyTuple::new(py, references)?.unbind())
        })
        .map(|references| references.clone_ref(py))
}

/// The model's declared key facts: its config and attached schema columns and audits.
pub(crate) fn model_relation_key_row(
    record: &ModelInputRecord,
    py: Python<'_>,
) -> PyResult<RelationKeyRow> {
    let values: Bound<'_, PyAny> = record.config.bind(py).getattr("values")?;
    relation_key_row(
        MODEL_RELATION_KIND,
        record
            .model_file
            .bind(py)
            .getattr("file_path")?
            .getattr("stem")?
            .extract()?,
        values.downcast::<PyDict>()?,
        record.schema.as_ref().map(|schema| {
            (
                schema.columns.bind(py).as_any(),
                schema.audits.bind(py).as_any(),
            )
        }),
    )
}

/// The name of the model's attached schema entry, its file stem, or `None`.
pub(crate) fn attached_schema_name(
    record: &ModelInputRecord,
    py: Python<'_>,
) -> PyResult<Option<String>> {
    if record.schema.is_none() {
        return Ok(None);
    }
    Ok(Some(
        record
            .model_file
            .bind(py)
            .getattr("file_path")?
            .getattr("stem")?
            .extract()?,
    ))
}

/// The model's attached `SchemaModelEntry`, or `None`, built once.
pub(crate) fn schema_entry(
    classes: &InputViewClasses<'_>,
    record: &ModelInputRecord,
) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = classes.schema_model_entry.py();
    record
        .projections
        .schema_entry
        .get_or_try_init(py, || {
            let Some(schema) = &record.schema else {
                return Ok::<_, pyo3::PyErr>(py.None());
            };
            let fields: Bound<'_, PyDict> = PyDict::new(py);
            fields.set_item(
                "name",
                record
                    .model_file
                    .bind(py)
                    .getattr("file_path")?
                    .getattr("stem")?,
            )?;
            fields.set_item("model_schema", &schema.model_schema)?;
            fields.set_item("description", &schema.description)?;
            fields.set_item("type_enforcement", schema.type_enforcement.then_some(true))?;
            fields.set_item("columns", schema.columns.bind(py))?;
            fields.set_item("dynamic_columns", schema.dynamic_columns.bind(py))?;
            fields.set_item("audits", schema.audits.bind(py))?;
            Ok(classes.schema_model_entry.call((), Some(&fields))?.unbind())
        })
        .map(|entry| entry.clone_ref(py))
}

/// `CompiledSqlExpansion(authored_sql, expanded_sql, passes)` for these passes.
fn expansion_object(
    classes: &InputViewClasses<'_>,
    expansion: &ExpansionRecord,
    passes: &[&Vec<SpanRow>],
) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = classes.sql_expansion.py();
    let mut pass_objects: Vec<Bound<'_, PyTuple>> = Vec::with_capacity(passes.len());
    for spans in passes {
        let mut span_objects: Vec<Bound<'_, PyAny>> = Vec::with_capacity(spans.len());
        for span in spans.iter() {
            span_objects.push(classes.expansion_span.call1(span.into_pyobject(py)?)?);
        }
        pass_objects.push(PyTuple::new(py, span_objects)?);
    }
    let fields: Bound<'_, PyDict> = PyDict::new(py);
    fields.set_item("authored_sql", expansion.authored_sql.bind(py))?;
    fields.set_item("expanded_sql", expansion.expanded_sql.bind(py))?;
    fields.set_item("passes", PyTuple::new(py, pass_objects)?)?;
    Ok(classes.sql_expansion.call((), Some(&fields))?.unbind())
}
