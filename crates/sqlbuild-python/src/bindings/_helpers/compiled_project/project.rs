//! The compile's natively owned project, which producers record into and consumers read.

use std::collections::{BTreeMap, HashMap};
use std::sync::Mutex;

use crate::bindings::_helpers::compiled_project::resource_diagnostics::{
    DiagnosticSettings, ResourceDiagnostics, resource_diagnostics,
};
use crate::bindings::_helpers::compiled_project::scenario_loop::ScenarioRow;
use crate::bindings::_helpers::compiled_project::sql_test_loop::{
    AttachedSqlTests, SqlTestSettings, TestFileRow,
};

use pyo3::exceptions::{PyIndexError, PyRuntimeError};
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyRef, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString};
use pyo3::{FromPyObject, pyclass, pymethods};
use serde_json::Value;
use sqlbuild_analysis::compiled_project::main::project_models::project_models;
use sqlbuild_analysis::compiled_project::main::record_model::record_model;
use sqlbuild_analysis::compiled_project::main::record_model_analysis::record_model_analysis;
use sqlbuild_analysis::compiled_project::models::{
    CompiledModelFacts, CompiledProjectFacts, DeclarationFact, DynamicFamilyFact, DynamicProofFact,
    ModelAnalysisFact, ModelConfigFacts, ModelReferenceFact, ModelSchemaFact, SchemaColumnFact,
};

use crate::bindings::_helpers::boundary::panics::{NativeCompilerError, compiler_guard};
use crate::bindings::_helpers::compiled_project::audit_loop::{
    AttachmentOwner, AuditFileRow, AuditSettings, model_owner, resource_owner,
};
use crate::bindings::_helpers::compiled_project::audit_views::{
    AuditRecord, NativeAuditInput, NativeCompiledAudit,
};
use crate::bindings::_helpers::compiled_project::compiled_model_view::{
    CompiledViewClasses, InferredRow, NativeCompiledModel,
};
use crate::bindings::_helpers::compiled_project::function_loop::{FunctionRow, FunctionSettings};
use crate::bindings::_helpers::compiled_project::function_views::{
    AttachedFunction, FunctionRecord, NativeCompiledFunction, NativeFunctionInput, ObjectKeyRow,
};
use crate::bindings::_helpers::compiled_project::inputs_view::NativeInputsView;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    ModelInputRecord, NativeModelInput,
};
use crate::bindings::_helpers::compiled_project::model_loop::NativeModelLoop;
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::project_view::NativeProjectView;
use crate::bindings::_helpers::compiled_project::seed_views::{
    NativeCompiledSeed, NativeSeedInput, SeedNamespace, SeedRecord, paired_seeds,
};
use crate::bindings::_helpers::compiled_project::source_loop::{SourceRow, SourceSettings};
use crate::bindings::_helpers::compiled_project::source_views::{
    AttachedSource, NativeCompiledSource, NativeSourceInput, SourceNamespace, SourceRecord,
};
use crate::bindings::_helpers::compiled_project::values::{object_value, plain_value};

pub(crate) const CONTRACT_KEY: &str = "contract";
const INPUT_CLASSES_UNSET: &str = "no model loop recorded inputs into this project";
const RELATIVE_PATH_ATTRIBUTE: &str = "relative_path";
const SOURCE_OWNER: &str = "source";
const SEED_OWNER: &str = "seed";
const ATTACHMENT_LOOP_UNSET: &str = "no model loop was kept to attach this project's resources";
pub(crate) const INCREMENTAL_MODE_KEY: &str = "incremental_mode";
const MATERIALIZED_KEY: &str = "materialized";
const TABLE_MATERIALIZATION: &str = "table";

/// `(name, type)`.
type NamedType = (String, Option<String>);
/// `(name, type, nullable, audit count, declared outside the model)`.
pub(crate) type SchemaColumnPy = (String, Option<String>, Option<bool>, u32, bool);
/// `(key, name, pivot column, value column, aggregate, type, name pattern)`.
pub(crate) type DynamicFamilyPy = (
    String,
    String,
    String,
    String,
    String,
    String,
    Option<String>,
);
/// `(entry audit count, columns, dynamic families, (type enforcement, named schema))`.
pub(crate) type SchemaPy = (u32, Vec<SchemaColumnPy>, Vec<DynamicFamilyPy>, (bool, bool));
/// `(output proven, bare dynamic pivot, (family key, inferred type), failure, (family, type))`.
type ProofPy = (bool, bool, Vec<NamedType>, Option<String>, Vec<NamedType>);
/// `(inferred, (name, type), nullable per column, has star, unchecked output columns)`.
type AnalysisPy = (bool, Vec<NamedType>, Vec<bool>, bool, Vec<String>);

/// Encoded config values and the encoder's error, if any.
pub(crate) type ConfigValues = (BTreeMap<String, Value>, Option<String>);

/// One model as the compile-input stage produced it.
#[derive(FromPyObject)]
pub(crate) struct ModelInputPy<'py>(
    (String, String, String, String, String),
    (Bound<'py, PyDict>, Vec<String>, Option<String>),
    Vec<(String, String, Option<String>)>,
    Option<SchemaPy>,
    Vec<String>,
    (Vec<DeclarationPy<'py>>, Vec<DeclarationPy<'py>>),
);

/// Name, relative path, members, value, value type and rendering of one declaration.
#[derive(FromPyObject)]
pub(crate) struct DeclarationPy<'py>(
    String,
    String,
    Vec<(String, Bound<'py, PyAny>)>,
    Bound<'py, PyAny>,
    Option<String>,
    Option<String>,
);

/// One compile's project facts, recorded by the stages that produce them.
#[pyclass(module = "sqlbuild._native")]
#[derive(Default)]
pub(crate) struct NativeCompiledProject {
    facts: CompiledProjectFacts,
    /// What the model loop finished for each model beyond its facts, in loop order.
    inputs: Vec<ModelInputRecord>,
    /// The Python classes model input views project their attributes with.
    input_classes: Option<Py<PyAny>>,
    /// Shared immutable column projections, allocated only when Python consumers request them.
    inferred_column_projections: Mutex<HashMap<InferredRow, Py<PyAny>>>,
    /// Lineage graphs its project views built.
    graph_builds: usize,
    /// Each attached seed, in attachment order.
    seeds: Vec<SeedRecord>,
    /// Each attached source, in attachment order.
    sources: Vec<SourceRecord>,
    /// Each attached SQL, then Python, function in attachment order.
    functions: Vec<FunctionRecord>,
    /// Each singular, then model-, source- and seed-attached, audit in attachment order.
    audits: Vec<AuditRecord>,
    /// The model loop and its host, which attach the project's other resources.
    attachment: Option<(Py<NativeModelLoop>, Py<PyAny>)>,
}

impl NativeCompiledProject {
    /// The facts recorded so far, for native consumers such as the rules request.
    pub(crate) fn facts(&self) -> &CompiledProjectFacts {
        &self.facts
    }

    /// Retain facts a producer finished natively.
    pub(crate) fn retain(&mut self, facts: CompiledModelFacts) {
        record_model(&mut self.facts, facts);
    }

    /// Retain a finished model's input record; return its index for the model's view.
    pub(crate) fn retain_input(&mut self, record: ModelInputRecord) -> usize {
        self.inputs.push(record);
        self.inputs.len() - 1
    }

    /// Keep the classes model input views project their attributes with.
    pub(crate) fn set_input_classes(&mut self, classes: Py<PyAny>) {
        self.input_classes = Some(classes);
    }

    /// Count one lineage graph a project view built.
    pub(crate) fn record_graph_build(&mut self) {
        self.graph_builds += 1;
    }

    /// Each schema-attached model, then each source and seed, with the audits attached to it.
    fn attachment_owners<'py>(&self, py: Python<'py>) -> PyResult<Vec<AttachmentOwner<'py>>> {
        let mut owners: Vec<AttachmentOwner<'py>> = Vec::new();
        for record in &self.inputs {
            let Some(schema) = &record.schema else {
                continue;
            };
            let model_file: &Bound<'py, PyAny> = record.model_file.bind(py);
            owners.push(model_owner(
                model_file
                    .getattr("file_path")?
                    .getattr("stem")?
                    .extract()?,
                model_file
                    .getattr(RELATIVE_PATH_ATTRIBUTE)?
                    .str()?
                    .to_string(),
                (schema.audits.bind(py), schema.columns.bind(py)),
            )?);
        }
        for source in &self.sources {
            let attached: &AttachedSource = source.attached();
            let path: String = attached
                .source_file
                .bind(py)
                .getattr(RELATIVE_PATH_ATTRIBUTE)?
                .str()?
                .to_string();
            owners.push(resource_owner(
                SOURCE_OWNER,
                attached.name.clone(),
                (path.clone(), path),
                (
                    attached.audits.bind(py).as_any(),
                    attached.columns.bind(py).as_any(),
                ),
            )?);
        }
        for seed in &self.seeds {
            let (name, seed_file, schema_entry, schema_file) = seed.parts();
            let schema_entry: &Bound<'py, PyAny> = schema_entry.bind(py);
            owners.push(resource_owner(
                SEED_OWNER,
                name.to_owned(),
                (
                    seed_file
                        .bind(py)
                        .getattr(RELATIVE_PATH_ATTRIBUTE)?
                        .str()?
                        .to_string(),
                    schema_file
                        .bind(py)
                        .getattr(RELATIVE_PATH_ATTRIBUTE)?
                        .str()?
                        .to_string(),
                ),
                (
                    &schema_entry.getattr("audits")?,
                    &schema_entry.getattr("columns")?,
                ),
            )?);
        }
        Ok(owners)
    }

    /// The kept model loop and its host.
    fn attachment_loop(&self, py: Python<'_>) -> PyResult<(Py<NativeModelLoop>, Py<PyAny>)> {
        match &self.attachment {
            Some((model_loop, host)) => Ok((model_loop.clone_ref(py), host.clone_ref(py))),
            None => Err(PyRuntimeError::new_err(ATTACHMENT_LOOP_UNSET)),
        }
    }

    /// Keep the model loop and its host for attaching the project's other resources.
    pub(crate) fn keep_attachment_loop(
        &mut self,
        model_loop: Py<NativeModelLoop>,
        host: Py<PyAny>,
    ) {
        self.attachment = Some((model_loop, host));
    }

    /// Every attached audit, in attachment order.
    pub(crate) fn audits(&self) -> &[AuditRecord] {
        &self.audits
    }

    /// Every attached function, in attachment order.
    pub(crate) fn functions(&self) -> &[FunctionRecord] {
        &self.functions
    }

    /// Every attached source, in attachment order.
    pub(crate) fn sources(&self) -> &[SourceRecord] {
        &self.sources
    }

    /// Keep one attached source.
    pub(crate) fn retain_source(&mut self, source: SourceRecord) {
        self.sources.push(source);
    }

    /// Every attached seed, in attachment order.
    pub(crate) fn seeds(&self) -> &[SeedRecord] {
        &self.seeds
    }

    /// Every model's input record, in loop order.
    pub(crate) fn inputs(&self) -> &[ModelInputRecord] {
        &self.inputs
    }

    /// The input record at `index`.
    pub(crate) fn input(&self, index: usize) -> PyResult<&ModelInputRecord> {
        self.inputs
            .get(index)
            .ok_or_else(|| PyIndexError::new_err(index))
    }

    /// The input record at `index`, for recording what later stages finish.
    pub(crate) fn input_mut(&mut self, index: usize) -> PyResult<&mut ModelInputRecord> {
        self.inputs
            .get_mut(index)
            .ok_or_else(|| PyIndexError::new_err(index))
    }

    /// The classes model input views project their attributes with.
    pub(crate) fn input_classes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.input_classes
            .as_ref()
            .map(|classes| classes.bind(py).clone())
            .ok_or_else(|| PyIndexError::new_err(INPUT_CLASSES_UNSET))
    }

    pub(crate) fn inferred_column<'py>(
        &self,
        py: Python<'py>,
        classes: &CompiledViewClasses<'py>,
        row: &InferredRow,
    ) -> PyResult<Bound<'py, PyAny>> {
        let (name, column_type, nullability) = row;
        if let Some(column) = self
            .inferred_column_projections
            .lock()
            .map_err(|error| NativeCompilerError::new_err(error.to_string()))?
            .get(row)
        {
            return Ok(column.bind(py).clone());
        }
        let fields = PyDict::new(py);
        fields.set_item("name", name)?;
        fields.set_item("type", column_type.as_deref())?;
        fields.set_item("nullability", classes.nullability.call1((nullability,))?)?;
        let column = classes.inferred_column.call((), Some(&fields))?;
        self.inferred_column_projections
            .lock()
            .map_err(|error| NativeCompilerError::new_err(error.to_string()))?
            .insert(row.clone(), column.clone().unbind());
        Ok(column)
    }
}

#[pymethods]
impl NativeCompiledProject {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    /// Retain one model's compile-input facts; a name recorded again is replaced in place.
    fn record_model(&mut self, model: ModelInputPy<'_>) -> PyResult<()> {
        compiler_guard(|| {
            let facts: CompiledModelFacts = model_facts(model)?;
            record_model(&mut self.facts, facts);
            Ok(())
        })
    }

    /// Attach a recorded model's typed analysis; `False` when that model was never recorded.
    fn record_model_analysis(
        &mut self,
        name: &str,
        columns: AnalysisPy,
        dynamic_proof: Option<ProofPy>,
    ) -> bool {
        let (inferred, inferred_columns, nullable_columns, fast_lineage_has_star, unchecked) =
            columns;
        let analysis: ModelAnalysisFact = ModelAnalysisFact {
            inferred_columns,
            dynamic_proof: dynamic_proof.map(
                |(output_proven, bare_dynamic_pivot, families, failure_reason, named_families)| {
                    DynamicProofFact {
                        output_proven,
                        bare_dynamic_pivot,
                        families,
                        failure_reason,
                        named_families,
                    }
                },
            ),
            inferred,
            nullable_columns,
            fast_lineage_has_star,
            unchecked_output_columns: unchecked,
        };
        record_model_analysis(&mut self.facts, name, analysis)
    }

    /// Record each assembled native model view's final typed analysis; return how many.
    fn record_view_analyses(
        slf: &Bound<'_, Self>,
        views: Vec<PyRef<'_, NativeCompiledModel>>,
    ) -> PyResult<usize> {
        let py: Python<'_> = slf.py();
        let mut facts: Vec<(String, ModelAnalysisFact)> = Vec::with_capacity(views.len());
        for view in &views {
            facts.push(view.analysis_fact(py)?);
        }
        let mut owner = slf.borrow_mut();
        let mut recorded: usize = 0;
        for (name, analysis) in facts {
            recorded += usize::from(record_model_analysis(&mut owner.facts, &name, analysis));
        }
        Ok(recorded)
    }

    /// The compile inputs view of this owner's model inputs with these input fields.
    fn inputs_view(slf: Bound<'_, Self>, fields: Bound<'_, PyDict>) -> PyResult<NativeInputsView> {
        NativeInputsView::new(slf.unbind(), &fields)
    }

    /// The compiled project view of this owner's models with these project fields.
    fn project_view(
        slf: Bound<'_, Self>,
        fields: Bound<'_, PyDict>,
    ) -> PyResult<NativeProjectView> {
        NativeProjectView::new(slf.unbind(), &fields)
    }

    /// Pair seed declarations with their CSV files and keep them; return each seed's view.
    fn attach_seeds(
        slf: &Bound<'_, Self>,
        declarations: Vec<(Py<PyAny>, Py<PyAny>)>,
        seed_files: Vec<Py<PyAny>>,
        compile_error: &Bound<'_, PyAny>,
    ) -> PyResult<Vec<NativeSeedInput>> {
        let seeds: Vec<SeedRecord> = paired_seeds(declarations, &seed_files, compile_error)?;
        let count: usize = seeds.len();
        slf.borrow_mut().seeds = seeds;
        Ok((0..count)
            .map(|index| NativeSeedInput::new(slf.clone().unbind(), index))
            .collect())
    }

    /// Keep the destinations native project assembly resolved, in seed order.
    fn record_seed_namespaces(&mut self, namespaces: Vec<SeedNamespace>) -> PyResult<()> {
        for (index, namespace) in namespaces.into_iter().enumerate() {
            self.seeds
                .get_mut(index)
                .ok_or_else(|| PyIndexError::new_err(index))?
                .set_namespace(namespace);
        }
        Ok(())
    }

    /// Attach every discovered source in order with the kept loop; return each source's view.
    fn attach_sources(
        slf: &Bound<'_, Self>,
        rows: Vec<SourceRow>,
        settings: SourceSettings,
    ) -> PyResult<Vec<NativeSourceInput>> {
        if rows.is_empty() {
            return Ok(Vec::new());
        }
        let py: Python<'_> = slf.py();
        let (model_loop, host) = slf.borrow().attachment_loop(py)?;
        model_loop
            .bind(py)
            .get()
            .run_sources(slf, host.bind(py), rows, settings)
    }

    /// Attach every SQL, then Python, function with the kept loop; return each one's view.
    fn attach_functions(
        slf: &Bound<'_, Self>,
        rows: (Vec<FunctionRow>, Vec<FunctionRow>),
        settings: FunctionSettings,
    ) -> PyResult<Vec<NativeFunctionInput>> {
        let py: Python<'_> = slf.py();
        let (model_loop, host) = slf.borrow().attachment_loop(py)?;
        let models: Vec<(String, Vec<ReferenceRow>)> = slf
            .borrow()
            .inputs
            .iter()
            .map(|record| {
                Ok((
                    record
                        .model_file
                        .bind(py)
                        .getattr(RELATIVE_PATH_ATTRIBUTE)?
                        .str()?
                        .to_string(),
                    record.references.clone(),
                ))
            })
            .collect::<PyResult<_>>()?;
        let attached: Vec<AttachedFunction> =
            model_loop
                .bind(py)
                .get()
                .run_functions(host.bind(py), rows, settings, &models)?;
        let first: usize = slf.borrow().functions.len();
        let count: usize = attached.len();
        slf.borrow_mut()
            .functions
            .extend(attached.into_iter().map(FunctionRecord::new));
        Ok((first..first + count)
            .map(|index| NativeFunctionInput::new(slf.clone().unbind(), index))
            .collect())
    }

    /// The orphaned audit factory warnings, missing descriptions and cursor-input errors.
    fn resource_diagnostics<'py>(
        &self,
        py: Python<'py>,
        settings: DiagnosticSettings,
    ) -> PyResult<ResourceDiagnostics<'py>> {
        resource_diagnostics(self, py, &settings)
    }

    /// Attach every SQL test case, then every scenario, with the kept loop.
    fn attach_sql_tests(
        slf: &Bound<'_, Self>,
        files: Vec<TestFileRow>,
        scenarios: Vec<ScenarioRow>,
        settings: SqlTestSettings,
    ) -> PyResult<AttachedSqlTests> {
        let py: Python<'_> = slf.py();
        let (model_loop, host) = slf.borrow().attachment_loop(py)?;
        let arities: HashMap<String, usize> = slf
            .borrow()
            .functions
            .iter()
            .filter(|record| !record.attached.return_columns.is_empty())
            .map(|record| {
                (
                    record.attached.name.clone(),
                    record.attached.arguments.len(),
                )
            })
            .collect();
        model_loop.bind(py).get().run_sql_tests(
            host.bind(py),
            (&files, &scenarios),
            &settings,
            arities,
        )
    }

    /// Attach singular, then resource-attached, audits; return views and override warnings.
    fn attach_audits<'py>(
        slf: &Bound<'py, Self>,
        files: Vec<AuditFileRow>,
        settings: AuditSettings,
    ) -> PyResult<(Vec<NativeAuditInput>, Vec<Bound<'py, PyAny>>)> {
        let py: Python<'py> = slf.py();
        let (model_loop, host) = slf.borrow().attachment_loop(py)?;
        let owners: Vec<AttachmentOwner<'py>> = slf.borrow().attachment_owners(py)?;
        let (attached, shadows) =
            model_loop
                .bind(py)
                .get()
                .run_audits(host.bind(py), &files, owners, &settings)?;
        let first: usize = slf.borrow().audits.len();
        let count: usize = attached.len();
        slf.borrow_mut()
            .audits
            .extend(attached.into_iter().map(AuditRecord::new));
        Ok((
            (first..first + count)
                .map(|index| NativeAuditInput::new(slf.clone().unbind(), index))
                .collect(),
            shadows,
        ))
    }

    /// Keep the scope dependency keys native project assembly resolved, in audit order.
    fn record_audit_scope_deps(&mut self, deps: Vec<Vec<ObjectKeyRow>>) -> PyResult<()> {
        for (index, keys) in deps.into_iter().enumerate() {
            self.audits
                .get_mut(index)
                .ok_or_else(|| PyIndexError::new_err(index))?
                .set_scope_deps(keys);
        }
        Ok(())
    }

    /// The assembled audit at `index`.
    fn compiled_audit(slf: &Bound<'_, Self>, index: usize) -> PyResult<NativeCompiledAudit> {
        if index >= slf.borrow().audits.len() {
            return Err(PyIndexError::new_err(index));
        }
        Ok(NativeCompiledAudit::new(slf.clone().unbind(), index))
    }

    /// Keep the dependency keys native project assembly resolved, in function order.
    fn record_function_deps(&mut self, deps: Vec<Vec<ObjectKeyRow>>) -> PyResult<()> {
        for (index, keys) in deps.into_iter().enumerate() {
            self.functions
                .get_mut(index)
                .ok_or_else(|| PyIndexError::new_err(index))?
                .set_deps(keys);
        }
        Ok(())
    }

    /// The assembled function at `index`.
    fn compiled_function(slf: &Bound<'_, Self>, index: usize) -> PyResult<NativeCompiledFunction> {
        if index >= slf.borrow().functions.len() {
            return Err(PyIndexError::new_err(index));
        }
        Ok(NativeCompiledFunction::new(slf.clone().unbind(), index))
    }

    /// Keep the namespaces native project assembly resolved, in source order.
    fn record_source_namespaces(&mut self, namespaces: Vec<SourceNamespace>) -> PyResult<()> {
        for (index, namespace) in namespaces.into_iter().enumerate() {
            self.sources
                .get_mut(index)
                .ok_or_else(|| PyIndexError::new_err(index))?
                .set_namespace(namespace);
        }
        Ok(())
    }

    /// The assembled source at `index`.
    fn compiled_source(slf: &Bound<'_, Self>, index: usize) -> PyResult<NativeCompiledSource> {
        if index >= slf.borrow().sources.len() {
            return Err(PyIndexError::new_err(index));
        }
        Ok(NativeCompiledSource::new(slf.clone().unbind(), index))
    }

    /// The assembled seed at `index`.
    fn compiled_seed(slf: &Bound<'_, Self>, index: usize) -> PyResult<NativeCompiledSeed> {
        if index >= slf.borrow().seeds.len() {
            return Err(PyIndexError::new_err(index));
        }
        Ok(NativeCompiledSeed::new(slf.clone().unbind(), index))
    }

    /// How many lineage graphs this owner's project views built.
    fn graph_builds(&self) -> usize {
        self.graph_builds
    }

    /// Whether both projects retained the same facts.
    fn __eq__(&self, other: &Self) -> bool {
        self.facts == other.facts
    }

    /// The recorded models' names, in production order.
    fn model_names(&self) -> Vec<String> {
        project_models(&self.facts)
            .iter()
            .map(|model| model.name.clone())
            .collect()
    }
}

pub(crate) fn model_facts(model: ModelInputPy<'_>) -> PyResult<CompiledModelFacts> {
    let ModelInputPy(
        (name, relative_path, query_sql, authored_query_sql, authored_sql),
        (values, header_keys, layer_schema),
        references,
        schema,
        enum_columns,
        (enum_declarations, constant_declarations),
    ) = model;
    let config_values: ConfigValues = config_values(&values);
    Ok(CompiledModelFacts {
        name,
        relative_path,
        query_sql,
        authored_query_sql,
        authored_sql,
        config: ModelConfigFacts {
            values: config_values.0,
            encoding_error: config_values.1,
            header_keys,
            layer_schema,
            contract: text_value(&values, CONTRACT_KEY)?,
            materialized: materialization(&values)?,
            incremental_mode: text_value(&values, INCREMENTAL_MODE_KEY)?,
        },
        references: references
            .into_iter()
            .map(|(kind, name, package)| ModelReferenceFact {
                kind,
                name,
                package,
            })
            .collect(),
        schema: schema.map(schema_fact),
        enum_columns,
        enum_declarations: declarations(enum_declarations)?,
        constant_declarations: declarations(constant_declarations)?,
        analysis: None,
    })
}

/// The config values, or the encoder's error, kept for the consumer that reads them.
pub(crate) fn config_values(values: &Bound<'_, PyDict>) -> ConfigValues {
    match object_value(values) {
        Ok(Value::Object(entries)) => (entries.into_iter().collect(), None),
        Ok(_) => (BTreeMap::new(), None),
        Err(error) => (BTreeMap::new(), Some(error.to_string())),
    }
}

/// The `materialized` config value when it is text, `table` when it is absent.
pub(crate) fn materialization(values: &Bound<'_, PyDict>) -> PyResult<Option<String>> {
    if values.get_item(MATERIALIZED_KEY)?.is_none() {
        return Ok(Some(TABLE_MATERIALIZATION.to_owned()));
    }
    text_value(values, MATERIALIZED_KEY)
}

/// A config value when it is text.
pub(crate) fn text_value(values: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match values.get_item(key)? {
        Some(value) if value.is_instance_of::<PyString>() => Ok(Some(value.extract()?)),
        _ => Ok(None),
    }
}

pub(crate) fn schema_fact(
    (audit_count, columns, dynamic_columns, (type_enforcement, named_schema)): SchemaPy,
) -> ModelSchemaFact {
    ModelSchemaFact {
        audit_count,
        columns: columns
            .into_iter()
            .map(
                |(name, data_type, nullable, audit_count, declared_outside_model)| {
                    SchemaColumnFact {
                        name,
                        data_type,
                        nullable,
                        audit_count,
                        declared_outside_model,
                    }
                },
            )
            .collect(),
        dynamic_columns: dynamic_columns.into_iter().map(family_fact).collect(),
        type_enforcement,
        named_schema,
    }
}

fn family_fact(
    (key, name, pivot_column, value_column, aggregate, data_type, name_pattern): DynamicFamilyPy,
) -> DynamicFamilyFact {
    DynamicFamilyFact {
        key,
        name,
        pivot_column,
        value_column,
        aggregate,
        data_type,
        name_pattern,
    }
}

pub(crate) fn declarations(rows: Vec<DeclarationPy<'_>>) -> PyResult<Vec<DeclarationFact>> {
    rows.into_iter().map(declaration).collect()
}

fn declaration(row: DeclarationPy<'_>) -> PyResult<DeclarationFact> {
    let DeclarationPy(name, relative_path, members, value, value_type, render_as) = row;
    Ok(DeclarationFact {
        name,
        relative_path,
        members: members
            .into_iter()
            .map(|(name, value)| Ok((name, plain_value(&value)?)))
            .collect::<PyResult<_>>()?,
        value: Some(plain_value(&value)?).filter(|value| !value.is_null()),
        value_type,
        render_as,
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelInput>()?;
    module.add_class::<NativeCompiledModel>()?;
    module.add_class::<NativeProjectView>()?;
    module.add_class::<NativeInputsView>()?;
    module.add_class::<NativeSeedInput>()?;
    module.add_class::<NativeCompiledSeed>()?;
    module.add_class::<NativeSourceInput>()?;
    module.add_class::<NativeFunctionInput>()?;
    module.add_class::<NativeAuditInput>()?;
    module.add_class::<NativeCompiledAudit>()?;
    module.add_class::<NativeCompiledFunction>()?;
    module.add_class::<NativeCompiledSource>()?;
    module.add_class::<NativeCompiledProject>()
}
