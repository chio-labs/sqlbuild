//! The compile's natively owned project, which producers record into and consumers read.

use std::collections::BTreeMap;

use pyo3::prelude::{Bound, PyAny, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyDict;
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
use crate::bindings::_helpers::compiled_project::values::{object_value, plain_value};

/// `(name, type)`.
type NamedType = (String, Option<String>);
/// `(name, type, nullable, audit count)`.
type SchemaColumnPy = (String, Option<String>, Option<bool>, u32);
/// `(key, name, pivot column, value column, aggregate, type, name pattern)`.
type DynamicFamilyPy = (
    String,
    String,
    String,
    String,
    String,
    String,
    Option<String>,
);
/// `(entry audit count, columns, dynamic families)`.
type SchemaPy = (u32, Vec<SchemaColumnPy>, Vec<DynamicFamilyPy>);
/// `(output proven, bare dynamic pivot, (family key, inferred type))`.
type ProofPy = (bool, bool, Vec<NamedType>);

/// Encoded config values and the encoder's error, if any.
type ConfigValues = (BTreeMap<String, Value>, Option<String>);

/// One model as the compile-input stage produced it.
#[derive(FromPyObject)]
struct ModelInputPy<'py>(
    (String, String, String, String, String),
    (Bound<'py, PyDict>, Vec<String>, Option<String>),
    Vec<(String, String, Option<String>)>,
    Option<SchemaPy>,
    Vec<String>,
    (Vec<DeclarationPy<'py>>, Vec<DeclarationPy<'py>>),
);

/// Name, relative path, members, value, value type and rendering of one declaration.
#[derive(FromPyObject)]
struct DeclarationPy<'py>(
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
}

impl NativeCompiledProject {
    /// The facts recorded so far, for native consumers such as the rules request.
    pub(crate) fn facts(&self) -> &CompiledProjectFacts {
        &self.facts
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
        inferred_columns: Vec<NamedType>,
        dynamic_proof: Option<ProofPy>,
    ) -> bool {
        let analysis: ModelAnalysisFact = ModelAnalysisFact {
            inferred_columns,
            dynamic_proof: dynamic_proof.map(|(output_proven, bare_dynamic_pivot, families)| {
                DynamicProofFact {
                    output_proven,
                    bare_dynamic_pivot,
                    families,
                }
            }),
        };
        record_model_analysis(&mut self.facts, name, analysis)
    }

    /// The recorded models' names, in production order.
    fn model_names(&self) -> Vec<String> {
        project_models(&self.facts)
            .iter()
            .map(|model| model.name.clone())
            .collect()
    }
}

fn model_facts(model: ModelInputPy<'_>) -> PyResult<CompiledModelFacts> {
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
fn config_values(values: &Bound<'_, PyDict>) -> ConfigValues {
    match object_value(values) {
        Ok(Value::Object(entries)) => (entries.into_iter().collect(), None),
        Ok(_) => (BTreeMap::new(), None),
        Err(error) => (BTreeMap::new(), Some(error.to_string())),
    }
}

fn schema_fact((audit_count, columns, dynamic_columns): SchemaPy) -> ModelSchemaFact {
    ModelSchemaFact {
        audit_count,
        columns: columns
            .into_iter()
            .map(
                |(name, data_type, nullable, audit_count)| SchemaColumnFact {
                    name,
                    data_type,
                    nullable,
                    audit_count,
                },
            )
            .collect(),
        dynamic_columns: dynamic_columns.into_iter().map(family_fact).collect(),
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

fn declarations(rows: Vec<DeclarationPy<'_>>) -> PyResult<Vec<DeclarationFact>> {
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
    module.add_class::<NativeCompiledProject>()
}
