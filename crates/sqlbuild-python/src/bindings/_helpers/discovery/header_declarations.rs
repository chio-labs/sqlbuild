//! Model-header enums and constants, and typed constant file entries, validated natively.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::declarations::errors::DeclarationFailure;
use sqlbuild_model_config::declarations::main::model_constant_declarations::model_constant_declarations;
use sqlbuild_model_config::declarations::main::model_enum_declarations::model_enum_declarations;
use sqlbuild_model_config::declarations::main::typed_constant_declaration::typed_constant_declaration;
use sqlbuild_model_config::declarations::models::{
    ConstantFacts, DeclarationSite, EnumFacts, EnumValue,
};
use sqlbuild_model_config::sql_values::errors::SqlValueFailure;
use sqlbuild_model_config::sql_values::models::RawSqlValue;

use crate::bindings::_helpers::contracts::sql_values::{
    SqlValueClasses, raw_value, sql_value, sql_value_error,
};

const MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const DISCOVERY_ERRORS_MODULE: &str = "sqlbuild.compiler.discovery.exceptions";
const IDENTITY_ERRORS_MODULE: &str = "sqlbuild.compiler.resource_names.exceptions";
const RENDERING_MODULE: &str = "sqlbuild.sql_values.types";

fn declaration_error(py: Python<'_>, failure: DeclarationFailure) -> PyResult<PyErr> {
    Ok(match failure {
        DeclarationFailure::Parse(message) => PyErr::from_value(
            py.import(DISCOVERY_ERRORS_MODULE)?
                .getattr("DeclarationParseError")?
                .call1((message,))?,
        ),
        DeclarationFailure::Identity(message, help) => {
            let keywords = PyDict::new(py);
            keywords.set_item("help", help)?;
            PyErr::from_value(
                py.import(IDENTITY_ERRORS_MODULE)?
                    .getattr("ResourceIdentityError")?
                    .call((message,), Some(&keywords))?,
            )
        }
        DeclarationFailure::DecimalOverflow => {
            sql_value_error(py, SqlValueFailure::DecimalOverflow)?
        }
    })
}

/// Who owns built declarations: their relative path and model.
struct Owner<'py> {
    relative_path: Bound<'py, PyAny>,
    model_name: Option<String>,
}

fn enum_record<'py>(
    py: Python<'py>,
    facts: EnumFacts,
    owner: &Owner<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let models = py.import(MODELS_MODULE)?;
    let member_class = models.getattr("EnumMember")?;
    let int_class = py.import("builtins")?.getattr("int")?;
    let members = facts
        .members
        .into_iter()
        .map(|(name, value)| {
            let value = match value {
                EnumValue::Text(text) => text.into_bound_py_any(py)?,
                EnumValue::Integer(digits) => int_class.call1((digits,))?,
            };
            member_class.call1((name, value))
        })
        .collect::<PyResult<Vec<_>>>()?;
    models.getattr("EnumDeclaration")?.call1((
        facts.name,
        PyTuple::new(py, members)?,
        facts.scalar_type,
        &owner.relative_path,
        owner.model_name.as_deref(),
    ))
}

fn constant_record<'py>(
    py: Python<'py>,
    facts: ConstantFacts,
    owner: &Owner<'py>,
    classes: &SqlValueClasses<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let render_as = match facts.render_as {
        Some(rendering) => py
            .import(RENDERING_MODULE)?
            .getattr("CollectionRendering")?
            .call1((rendering,))?,
        None => py.None().into_bound(py),
    };
    py.import(MODELS_MODULE)?
        .getattr("ConstantDeclaration")?
        .call1((
            facts.name,
            sql_value(&facts.value, classes)?,
            &owner.relative_path,
            owner.model_name.as_deref(),
            render_as,
        ))
}

fn optional_raw(
    value: Option<&Bound<'_, PyAny>>,
    classes: &SqlValueClasses<'_>,
) -> PyResult<Option<RawSqlValue>> {
    value
        .filter(|value| !value.is_none())
        .map(|value| raw_value(value, classes))
        .transpose()
}

type HeaderDeclarations<'py> = (Bound<'py, PyTuple>, Bound<'py, PyTuple>);

/// `parse_model_enum_declarations` then `parse_model_constant_declarations` for one model.
#[pyfunction]
fn model_header_declarations<'py>(
    py: Python<'py>,
    header: (Option<Bound<'py, PyAny>>, Option<Bound<'py, PyAny>>),
    model_name: String,
    relative_path: Bound<'py, PyAny>,
) -> PyResult<HeaderDeclarations<'py>> {
    let (enums, constants) = header;
    let classes = SqlValueClasses::load(py)?;
    let file_path = relative_path.str()?.to_string();
    let site = DeclarationSite {
        file_path: &file_path,
        model_name: Some(&model_name),
    };
    let owner = Owner {
        relative_path: relative_path.clone(),
        model_name: Some(model_name.clone()),
    };
    let raw_enums = optional_raw(enums.as_ref(), &classes)?;
    let enum_facts = match model_enum_declarations(raw_enums.as_ref(), site) {
        Ok(facts) => facts,
        Err(failure) => return Err(declaration_error(py, failure)?),
    };
    let raw_constants = optional_raw(constants.as_ref(), &classes)?;
    let constant_facts = match model_constant_declarations(raw_constants.as_ref(), site) {
        Ok(facts) => facts,
        Err(failure) => return Err(declaration_error(py, failure)?),
    };
    let enum_records = enum_facts
        .into_iter()
        .map(|facts| enum_record(py, facts, &owner))
        .collect::<PyResult<Vec<_>>>()?;
    let constant_records = constant_facts
        .into_iter()
        .map(|facts| constant_record(py, facts, &owner, &classes))
        .collect::<PyResult<Vec<_>>>()?;
    Ok((
        PyTuple::new(py, enum_records)?,
        PyTuple::new(py, constant_records)?,
    ))
}

/// `typed_constant_declaration` for a public constant file entry.
#[pyfunction]
fn typed_constant_record<'py>(
    py: Python<'py>,
    constant: (String, Bound<'py, PyAny>),
    options: (Option<String>, Option<String>),
    paths: (Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let (name, value) = constant;
    let (explicit_type, render_as) = options;
    let (file_path, relative_path) = paths;
    let classes = SqlValueClasses::load(py)?;
    let raw = raw_value(&value, &classes)?;
    let path = file_path.str()?.to_string();
    match typed_constant_declaration(
        &name,
        &raw,
        (explicit_type.as_deref(), render_as.as_deref()),
        &path,
    ) {
        Ok(facts) => constant_record(
            py,
            facts,
            &Owner {
                relative_path,
                model_name: None,
            },
            &classes,
        ),
        Err(failure) => Err(declaration_error(py, failure)?),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(model_header_declarations, module)?)?;
    module.add_function(wrap_pyfunction!(typed_constant_record, module)?)
}
