//! A compiled model, read from the native compiled project that owns it.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple, PyTupleMethods};
use pyo3::{FromPyObject, pyclass, pymethods};

use crate::bindings::_helpers::compiled_project::model_input_view::{
    InputViewClasses, ModelInputRecord, read_input, references, rejected_opt_out, schema_entry,
    view_classes,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::graph::project_graph::ResourceRow;

const DATABASE_KEY: &str = "database";
const SCHEMA_KEY: &str = "schema";
const ALIAS_KEY: &str = "alias";
const VALUES_ATTRIBUTE: &str = "values";
const LOGICAL_SCHEMA_ATTRIBUTE: &str = "logical_schema";
const LOGICAL_DATABASE_ATTRIBUTE: &str = "logical_database";
const MODEL_RESOURCE: &str = "model";
const TAGS_KEY: &str = "tags";

/// `(name, type, nullability)` of one inferred output column.
pub(crate) type InferredRow = (String, Option<String>, String);

/// `(name, type)` of a declared column.
pub(crate) type DeclaredRow = (String, Option<String>);

/// `(database, schema, name)` of a relation.
pub(crate) type DestinationRow = (Option<String>, Option<String>, String);

/// The Python classes a compiled model's projected attributes are built with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct CompiledViewClasses<'py> {
    object_key: Bound<'py, PyAny>,
    relation_location: Bound<'py, PyAny>,
    inferred_column: Bound<'py, PyAny>,
    nullability: Bound<'py, PyAny>,
}

/// A compiled relation location's parts.
#[derive(Clone)]
pub(crate) struct DestinationFact {
    database: Option<String>,
    schema: Option<String>,
    name: String,
    qualified_name: Option<String>,
    logical_schema: Option<String>,
    logical_database: Option<String>,
}

/// What assembly and the semantic checks finished for one compiled model.
pub(crate) struct CompiledRecord {
    /// `(resource type, name)` of each dependency.
    deps: Vec<(String, String)>,
    destination: DestinationFact,
    inferred: Option<Vec<InferredRow>>,
    /// The native session's compact lineage sequence, or `None`.
    fast_lineage_columns: Option<Py<PyAny>>,
    fast_lineage_has_star: bool,
    fast_lineage_star_resolved: bool,
    /// Binding diagnostics, normally none; kept until diagnostics are owner facts.
    binding_diagnostics: Py<PyTuple>,
    binding_validated: bool,
    /// The dynamic column proof, normally none; kept until proofs are owner facts.
    dynamic_column_contract: Option<Py<PyAny>>,
    macro_deps: Vec<String>,
    projections: CompiledProjections,
}

/// A compiled model's Python attribute projections, each built once on first access.
struct CompiledProjections {
    key: PyOnceLock<Py<PyAny>>,
    deps: PyOnceLock<Py<PyTuple>>,
}

impl Default for CompiledProjections {
    fn default() -> Self {
        Self {
            key: PyOnceLock::new(),
            deps: PyOnceLock::new(),
        }
    }
}

/// What later stages changed for one view of a model; the owner's record stays as assembled.
#[derive(Default)]
struct ModelOverlay {
    binding_diagnostics: Option<Py<PyTuple>>,
    /// Output columns whose types semantic recovery forgot, left unchecked by the contract.
    poisoned: Vec<String>,
    destination: Option<DestinationFact>,
}

impl ModelOverlay {
    fn clone_ref(&self, py: Python<'_>) -> Self {
        Self {
            binding_diagnostics: self
                .binding_diagnostics
                .as_ref()
                .map(|diagnostics| diagnostics.clone_ref(py)),
            poisoned: self.poisoned.clone(),
            destination: self.destination.clone(),
        }
    }
}

/// One view's projections of attributes its overlay can change, each built once.
struct ViewProjections {
    destination: PyOnceLock<Py<PyAny>>,
    inferred_columns: PyOnceLock<Py<PyAny>>,
}

impl Default for ViewProjections {
    fn default() -> Self {
        Self {
            destination: PyOnceLock::new(),
            inferred_columns: PyOnceLock::new(),
        }
    }
}

/// `(compact lineage, has star, star resolved)`.
type LineageArgument = (Option<Py<PyAny>>, bool, bool);

/// What assembly hands the owner for one model.
#[derive(FromPyObject)]
pub(crate) struct CompiledArguments(
    Vec<(String, String)>,
    Option<Vec<InferredRow>>,
    LineageArgument,
    (Py<PyTuple>, bool),
    Option<Py<PyAny>>,
    Vec<String>,
);

/// The compiled record of one model, with its configured destination.
pub(crate) fn compiled_record(
    py: Python<'_>,
    input: &ModelInputRecord,
    name: &str,
    arguments: CompiledArguments,
) -> PyResult<CompiledRecord> {
    let CompiledArguments(
        deps,
        inferred,
        (fast_lineage_columns, fast_lineage_has_star, fast_lineage_star_resolved),
        (binding_diagnostics, binding_validated),
        dynamic_column_contract,
        macro_deps,
    ) = arguments;
    let config: &Bound<'_, PyAny> = input.config.bind(py);
    let values: Bound<'_, PyDict> = config.getattr(VALUES_ATTRIBUTE)?.downcast_into()?;
    Ok(CompiledRecord {
        deps,
        destination: DestinationFact {
            database: text_value(&values, DATABASE_KEY)?,
            schema: text_value(&values, SCHEMA_KEY)?,
            name: text_value(&values, ALIAS_KEY)?.unwrap_or_else(|| name.to_owned()),
            qualified_name: None,
            logical_schema: config.getattr(LOGICAL_SCHEMA_ATTRIBUTE)?.extract()?,
            logical_database: config.getattr(LOGICAL_DATABASE_ATTRIBUTE)?.extract()?,
        },
        inferred,
        fast_lineage_columns,
        fast_lineage_has_star,
        fast_lineage_star_resolved,
        binding_diagnostics,
        binding_validated,
        dynamic_column_contract,
        macro_deps,
        projections: CompiledProjections::default(),
    })
}

fn text_value(values: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match values.get_item(key)? {
        Some(value) if value.is_instance_of::<pyo3::types::PyString>() => {
            Ok(Some(value.extract()?))
        }
        _ => Ok(None),
    }
}

/// The destination with adapter defaults filled in; `render` renders its qualified name.
fn defaulted_destination(
    current: &DestinationFact,
    defaults: (Option<String>, Option<String>),
    render: &Bound<'_, PyAny>,
) -> PyResult<DestinationFact> {
    let (default_schema, default_database) = defaults;
    let schema: Option<String> = current.schema.clone().or(default_schema);
    let database: Option<String> = current.database.clone().or(default_database);
    let keywords: Bound<'_, PyDict> = PyDict::new(render.py());
    keywords.set_item(DATABASE_KEY, &database)?;
    keywords.set_item(SCHEMA_KEY, &schema)?;
    keywords.set_item("name", &current.name)?;
    let qualified_name: Option<String> = render.call((), Some(&keywords))?.extract()?;
    Ok(DestinationFact {
        database,
        schema,
        name: current.name.clone(),
        qualified_name,
        logical_schema: current.logical_schema.clone(),
        logical_database: current.logical_database.clone(),
    })
}

/// One compiled model, projected from the owner on demand.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeCompiledModel {
    owner: Py<NativeCompiledProject>,
    index: usize,
    overlay: ModelOverlay,
    projections: ViewProjections,
}

impl NativeCompiledModel {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self::with_overlay(owner, index, ModelOverlay::default())
    }

    fn with_overlay(owner: Py<NativeCompiledProject>, index: usize, overlay: ModelOverlay) -> Self {
        Self {
            owner,
            index,
            overlay,
            projections: ViewProjections::default(),
        }
    }

    fn changed(&self, py: Python<'_>, change: impl FnOnce(&mut ModelOverlay)) -> Self {
        let mut overlay: ModelOverlay = self.overlay.clone_ref(py);
        change(&mut overlay);
        Self::with_overlay(self.owner.clone_ref(py), self.index, overlay)
    }

    fn read<'py, T>(
        &self,
        py: Python<'py>,
        read: impl FnOnce(&ModelInputRecord, Python<'py>) -> PyResult<T>,
    ) -> PyResult<T> {
        read_input(&self.owner, self.index, py, read)
    }

    fn compiled<'py, T>(
        &self,
        py: Python<'py>,
        read: impl FnOnce(&CompiledRecord, Python<'py>) -> PyResult<T>,
    ) -> PyResult<T> {
        self.read(py, |record, py| read(compiled_of(record)?, py))
    }

    fn model_file_attribute(&self, py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
        self.read(py, |record, py| {
            Ok(record.model_file.bind(py).getattr(name)?.unbind())
        })
    }
}

/// The compiled record of an input, which assembly records before any view is handed out.
fn compiled_of(record: &ModelInputRecord) -> PyResult<&CompiledRecord> {
    record
        .compiled
        .as_ref()
        .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("the model was not assembled"))
}

#[pymethods]
impl NativeCompiledModel {
    #[getter]
    fn key(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, py| {
            let compiled: &CompiledRecord = compiled_of(record)?;
            compiled
                .projections
                .key
                .get_or_try_init(py, || {
                    object_key(&classes.compiled, MODEL_RESOURCE, &model_name(record, py)?)
                })
                .map(|key| key.clone_ref(py))
        })
    }

    #[getter]
    fn deps(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.compiled(py, |compiled, py| {
            compiled
                .projections
                .deps
                .get_or_try_init(py, || {
                    let mut keys: Vec<Py<PyAny>> = Vec::with_capacity(compiled.deps.len());
                    for (kind, name) in &compiled.deps {
                        keys.push(object_key(&classes.compiled, kind, name)?);
                    }
                    Ok::<_, pyo3::PyErr>(PyTuple::new(py, keys)?.unbind())
                })
                .map(|deps| deps.clone_ref(py))
        })
    }

    #[getter]
    fn name(&self, py: Python<'_>) -> PyResult<String> {
        self.read(py, |record, py| model_name(record, py))
    }

    #[getter]
    fn relative_path(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.model_file_attribute(py, "relative_path")
    }

    #[getter]
    fn query_sql(&self, py: Python<'_>) -> PyResult<String> {
        self.read(py, |record, _| Ok(record.query_sql.clone()))
    }

    #[getter]
    fn config(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.read(py, |record, py| Ok(record.config.clone_ref(py)))
    }

    #[getter]
    fn destination(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.compiled(py, |compiled, py| {
            self.projections
                .destination
                .get_or_try_init(py, || {
                    let destination: &DestinationFact = self
                        .overlay
                        .destination
                        .as_ref()
                        .unwrap_or(&compiled.destination);
                    let fields: Bound<'_, PyDict> = PyDict::new(py);
                    fields.set_item(DATABASE_KEY, &destination.database)?;
                    fields.set_item(SCHEMA_KEY, &destination.schema)?;
                    fields.set_item("name", &destination.name)?;
                    fields.set_item("qualified_name", &destination.qualified_name)?;
                    fields.set_item(LOGICAL_SCHEMA_ATTRIBUTE, &destination.logical_schema)?;
                    fields.set_item(LOGICAL_DATABASE_ATTRIBUTE, &destination.logical_database)?;
                    Ok::<_, pyo3::PyErr>(
                        classes
                            .compiled
                            .relation_location
                            .call((), Some(&fields))?
                            .unbind(),
                    )
                })
                .map(|destination| destination.clone_ref(py))
        })
    }

    #[getter]
    fn references(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, _| references(&classes, record))
    }

    /// Each reference as `(kind, name, package, call argument count)`.
    #[getter]
    fn reference_rows(&self, py: Python<'_>) -> PyResult<Vec<ReferenceRow>> {
        self.read(py, |record, _| Ok(record.references.clone()))
    }

    /// `(resource type, name)` of the model's key.
    #[getter]
    fn key_row(&self, py: Python<'_>) -> PyResult<(String, String)> {
        self.read(py, |record, py| {
            Ok((MODEL_RESOURCE.to_owned(), model_name(record, py)?))
        })
    }

    /// `(resource type, name)` of each dependency.
    #[getter]
    fn dep_rows(&self, py: Python<'_>) -> PyResult<Vec<(String, String)>> {
        self.compiled(py, |compiled, _| Ok(compiled.deps.clone()))
    }

    /// `(database, schema, name)` of the model's destination.
    #[getter]
    fn destination_row(&self, py: Python<'_>) -> PyResult<DestinationRow> {
        self.compiled(py, |compiled, _| {
            let destination: &DestinationFact = self
                .overlay
                .destination
                .as_ref()
                .unwrap_or(&compiled.destination);
            Ok((
                destination.database.clone(),
                destination.schema.clone(),
                destination.name.clone(),
            ))
        })
    }

    /// Each inferred column as `(name, type, nullability)`, or `None` when none were inferred.
    #[getter]
    fn inferred_rows(&self, py: Python<'_>) -> PyResult<Option<Vec<InferredRow>>> {
        self.compiled(py, |compiled, _| {
            let Some(rows) = &compiled.inferred else {
                return Ok(None);
            };
            let mut shown: Vec<InferredRow> = Vec::with_capacity(rows.len());
            for (name, column_type, nullability) in rows {
                let poisoned: bool = self.overlay.poisoned.contains(name);
                let column_type: Option<String> = if poisoned { None } else { column_type.clone() };
                shown.push((name.clone(), column_type, nullability.clone()));
            }
            Ok(Some(shown))
        })
    }

    /// Each declared column of the attached schema as `(name, type)`, or `None` without one.
    #[getter]
    fn schema_column_rows(&self, py: Python<'_>) -> PyResult<Option<Vec<DeclaredRow>>> {
        self.read(py, |record, py| {
            let Some(schema) = &record.schema else {
                return Ok(None);
            };
            let mut rows: Vec<DeclaredRow> = Vec::new();
            for column in schema.columns.bind(py).iter() {
                rows.push((
                    column.getattr("name")?.extract()?,
                    column.getattr("type")?.extract()?,
                ));
            }
            Ok(Some(rows))
        })
    }

    /// Whether the attached schema declares dynamic columns.
    #[getter(has_dynamic_columns)]
    fn dynamic_columns_declared(&self, py: Python<'_>) -> PyResult<bool> {
        self.read(py, |record, py| {
            Ok(record
                .schema
                .as_ref()
                .is_some_and(|schema| !schema.dynamic_columns.bind(py).is_empty()))
        })
    }

    /// Inferred columns, else the attached schema's declared columns, else zero.
    #[getter]
    fn output_column_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.read(py, |record, py| {
            if let Some(rows) = &compiled_of(record)?.inferred {
                return Ok(rows.len());
            }
            Ok(record
                .schema
                .as_ref()
                .map_or(0, |schema| schema.columns.bind(py).len()))
        })
    }

    #[getter]
    fn schema_entry(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.read(py, |record, _| schema_entry(&classes, record))
    }

    #[getter]
    fn inferred_columns(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.compiled(py, |compiled, py| {
            self.projections
                .inferred_columns
                .get_or_try_init(py, || {
                    let Some(rows) = &compiled.inferred else {
                        return Ok::<_, pyo3::PyErr>(py.None());
                    };
                    let mut columns: Vec<Bound<'_, PyAny>> = Vec::with_capacity(rows.len());
                    for (name, column_type, nullability) in rows {
                        let poisoned: bool = self.overlay.poisoned.contains(name);
                        let fields: Bound<'_, PyDict> = PyDict::new(py);
                        fields.set_item("name", name)?;
                        fields.set_item("type", column_type.as_ref().filter(|_| !poisoned))?;
                        fields.set_item(
                            "nullability",
                            classes.compiled.nullability.call1((nullability,))?,
                        )?;
                        columns.push(classes.compiled.inferred_column.call((), Some(&fields))?);
                    }
                    Ok(PyTuple::new(py, columns)?.into_any().unbind())
                })
                .map(|columns| columns.clone_ref(py))
        })
    }

    #[getter]
    fn fast_lineage_columns(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.compiled(py, |compiled, py| {
            Ok(compiled
                .fast_lineage_columns
                .as_ref()
                .map_or_else(|| py.None(), |columns| columns.clone_ref(py)))
        })
    }

    #[getter]
    fn fast_lineage_has_star(&self, py: Python<'_>) -> PyResult<bool> {
        self.compiled(py, |compiled, _| Ok(compiled.fast_lineage_has_star))
    }

    #[getter]
    fn fast_lineage_star_resolved(&self, py: Python<'_>) -> PyResult<bool> {
        self.compiled(py, |compiled, _| Ok(compiled.fast_lineage_star_resolved))
    }

    #[getter]
    fn authored_sql(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.model_file_attribute(py, "contents")
    }

    #[getter]
    fn authored_query_sql(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.model_file_attribute(py, "query_sql")
    }

    #[getter]
    fn output_column_locations(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.model_file_attribute(py, "output_column_locations")
    }

    #[getter]
    fn extract_implicit_alias_columns(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.model_file_attribute(py, "extract_implicit_alias_columns")
    }

    #[getter]
    fn macro_deps<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        self.compiled(py, |compiled, py| PyTuple::new(py, &compiled.macro_deps))
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
    fn binding_diagnostics(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        self.compiled(py, |compiled, py| {
            Ok(self
                .overlay
                .binding_diagnostics
                .as_ref()
                .unwrap_or(&compiled.binding_diagnostics)
                .clone_ref(py))
        })
    }

    #[getter]
    fn binding_validated(&self, py: Python<'_>) -> PyResult<bool> {
        self.compiled(py, |compiled, _| Ok(compiled.binding_validated))
    }

    #[getter]
    fn dynamic_column_contract(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.compiled(py, |compiled, py| {
            Ok(compiled
                .dynamic_column_contract
                .as_ref()
                .map_or_else(|| py.None(), |proof| proof.clone_ref(py)))
        })
    }

    #[getter]
    fn unchecked_output_columns<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyFrozenSet>> {
        PyFrozenSet::new(py, &self.overlay.poisoned)
    }

    #[getter]
    fn rejected_sql_analysis_opt_out(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.read(py, |record, py| Ok(rejected_opt_out(record, py)))
    }

    /// This model with its final binding diagnostics.
    fn with_binding_diagnostics(&self, py: Python<'_>, diagnostics: Py<PyTuple>) -> Self {
        self.changed(py, |overlay| {
            overlay.binding_diagnostics = Some(diagnostics)
        })
    }

    /// This model after semantic type recovery: its bindings and the outputs left unchecked.
    fn with_type_recovery(
        &self,
        py: Python<'_>,
        diagnostics: Py<PyTuple>,
        poisoned: Vec<String>,
    ) -> Self {
        self.changed(py, |overlay| {
            overlay.binding_diagnostics = Some(diagnostics);
            overlay.poisoned = poisoned;
        })
    }

    /// This model with the adapter's default schema and database filled into its destination.
    fn with_target_defaults(
        &self,
        py: Python<'_>,
        defaults: (Option<String>, Option<String>),
        render: Bound<'_, PyAny>,
    ) -> PyResult<Self> {
        let destination: DestinationFact = self.compiled(py, |compiled, _| {
            let current: &DestinationFact = self
                .overlay
                .destination
                .as_ref()
                .unwrap_or(&compiled.destination);
            defaulted_destination(current, defaults, &render)
        })?;
        Ok(self.changed(py, |overlay| overlay.destination = Some(destination)))
    }
}

/// The model's project graph row: its key, dependencies, tags and folder.
pub(crate) fn model_graph_row(
    model: &NativeCompiledModel,
    py: Python<'_>,
) -> PyResult<ResourceRow> {
    model.read(py, |record, py| {
        let compiled: &CompiledRecord = compiled_of(record)?;
        let values: Bound<'_, PyAny> = record.config.bind(py).getattr(VALUES_ATTRIBUTE)?;
        let mut tags: Vec<String> = Vec::new();
        if let Some(value) = values.downcast::<PyDict>()?.get_item(TAGS_KEY)?
            && (value.is_instance_of::<pyo3::types::PyList>()
                || value.is_instance_of::<pyo3::types::PyTuple>())
        {
            for tag in value.try_iter()? {
                tags.push(tag?.str()?.extract()?);
            }
        }
        let folder: String = record
            .model_file
            .bind(py)
            .getattr("relative_path")?
            .getattr("parent")?
            .str()?
            .extract()?;
        Ok((
            (MODEL_RESOURCE.to_owned(), model_name(record, py)?),
            compiled.deps.clone(),
            tags,
            Some(folder),
        ))
    })
}

fn model_name(record: &ModelInputRecord, py: Python<'_>) -> PyResult<String> {
    record
        .model_file
        .bind(py)
        .getattr("file_path")?
        .getattr("stem")?
        .extract()
}

fn object_key(classes: &CompiledViewClasses<'_>, kind: &str, name: &str) -> PyResult<Py<PyAny>> {
    let fields: Bound<'_, PyDict> = PyDict::new(classes.object_key.py());
    fields.set_item("resource_type", kind)?;
    fields.set_item("name", name)?;
    Ok(classes.object_key.call((), Some(&fields))?.unbind())
}
