//! The compile's natively owned project, which producers record into and consumers read.

use std::collections::BTreeMap;

use pyo3::exceptions::PyIndexError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
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

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::compiled_project::compiled_model_view::NativeCompiledModel;
use crate::bindings::_helpers::compiled_project::inputs_view::NativeInputsView;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    ModelInputRecord, NativeModelInput,
};
use crate::bindings::_helpers::compiled_project::project_view::NativeProjectView;
use crate::bindings::_helpers::compiled_project::values::{object_value, plain_value};

pub(crate) const CONTRACT_KEY: &str = "contract";
const INPUT_CLASSES_UNSET: &str = "no model loop recorded inputs into this project";
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
    /// Lineage graphs its project views built.
    graph_builds: usize,
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
    module.add_class::<NativeCompiledProject>()
}
