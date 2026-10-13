//! Inference-profile settings crossing into native analysis: rule ids, shapes and the catalog.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};
use sqlbuild_analysis::assembly::analysis_session::types::{Pairs, Shapes};

const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const BINDING_CATALOG_MODULE: &str = "sqlbuild.compiler.sql_analysis.main._binding_catalog";
const SQL_ANALYSIS_CONSTANTS_MODULE: &str = "sqlbuild.compiler.sql_analysis.constants";
const GENERIC_DIALECT: &str = "generic";
const ADAPTER_RULE_ID: &str = "python";
/// `(module, function, native rule id)` of the nullability rules the native analysis knows.
const KNOWN_RULES: [(&str, &str, &str); 3] = [
    (
        "sqlbuild.adapter.type_system.main.first_arg_nullability",
        "first_arg_nullability",
        "first_arg",
    ),
    (
        "sqlbuild.adapter.type_system.main.conditional_result_nullability",
        "conditional_result_nullability",
        "conditional_result",
    ),
    (
        "sqlbuild.adapter.type_system.main.safe_cast_nullability",
        "safe_cast_nullability",
        "safe_cast",
    ),
];

/// The adapter's own nullability rules and `InferredNullability`, which native analysis calls.
pub(crate) type AdapterRules = Option<(Py<PyDict>, Py<PyAny>)>;

/// The adapter nullability rules as `(name, rule id)` rows, and the adapter's own rules.
pub(crate) fn nullability_rules(profile: &Bound<'_, PyAny>) -> PyResult<(Pairs, AdapterRules)> {
    let py: Python<'_> = profile.py();
    let known: Bound<'_, PyDict> = PyDict::new(py);
    for (module, function, id) in KNOWN_RULES {
        known.set_item(py.import(module)?.getattr(function)?, id)?;
    }
    let adapter: Bound<'_, PyDict> = PyDict::new(py);
    let mut rows: Pairs = Vec::new();
    for item in profile
        .getattr("function_nullability_rules")?
        .call_method0("items")?
        .try_iter()?
    {
        let (name, rule): (Bound<'_, PyAny>, Bound<'_, PyAny>) = item?.extract()?;
        let id: String = match known.get_item(&rule)? {
            Some(id) => id.extract()?,
            None => {
                adapter.set_item(&name, &rule)?;
                ADAPTER_RULE_ID.to_owned()
            }
        };
        rows.push((name.extract()?, id));
    }
    if adapter.is_empty() {
        return Ok((rows, None));
    }
    let nullability: Bound<'_, PyAny> = py
        .import(LINEAGE_TYPES_MODULE)?
        .getattr("InferredNullability")?;
    Ok((rows, Some((adapter.unbind(), nullability.unbind()))))
}

/// `{relation: {column: value}}` as ordered rows, each value as `str(value)`.
pub(crate) fn shape_rows(shapes: &Bound<'_, PyAny>) -> PyResult<Shapes> {
    let mut rows: Shapes = Vec::new();
    for item in shapes.call_method0("items")?.try_iter()? {
        let (name, shape): (String, Bound<'_, PyAny>) = item?.extract()?;
        let mut pairs: Pairs = Vec::new();
        for column in shape.call_method0("items")?.try_iter()? {
            let (column, value): (String, Bound<'_, PyAny>) = column?.extract()?;
            pairs.push((column, value.str()?.extract()?));
        }
        rows.push((name, pairs));
    }
    Ok(rows)
}

/// A `{key: value}` text mapping's items in order.
pub(crate) fn pairs(mapping: &Bound<'_, PyAny>) -> PyResult<Pairs> {
    mapping
        .call_method0("items")?
        .try_iter()?
        .map(|item| item?.extract())
        .collect()
}

/// `profile.sql_analysis_dialect or "generic"`.
pub(crate) fn profile_dialect(profile: &Bound<'_, PyAny>) -> PyResult<String> {
    dialect_or_generic(&profile.getattr("sql_analysis_dialect")?)
}

/// `dialect or "generic"`.
pub(crate) fn dialect_or_generic(dialect: &Bound<'_, PyAny>) -> PyResult<String> {
    if dialect.is_truthy()? {
        return dialect.extract();
    }
    Ok(GENERIC_DIALECT.to_owned())
}

/// Python's `NATIVE_DIALECT_ALIASES.get(dialect, dialect)`.
pub(crate) fn aliased_dialect(py: Python<'_>, dialect: String) -> PyResult<String> {
    let aliases: Bound<'_, PyAny> = py
        .import(SQL_ANALYSIS_CONSTANTS_MODULE)?
        .getattr("NATIVE_DIALECT_ALIASES")?;
    let key: Bound<'_, PyString> = PyString::new(py, &dialect);
    aliases.call_method1("get", (&key, &key))?.extract()
}

/// Python's `inferred_binding_shape` test for keeping authored identifier quoting.
pub(crate) fn case_sensitive_shapes(
    profile: &Bound<'_, PyAny>,
    dialect: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    if profile
        .getattr("quoted_identifiers_ignore_case")?
        .is_truthy()?
    {
        return Ok(false);
    }
    profile
        .py()
        .import(SQL_ANALYSIS_CONSTANTS_MODULE)?
        .getattr("CASE_SENSITIVE_BINDING_DIALECTS")?
        .contains(dialect)
}

/// `profile.binding_catalog or create_binding_catalog(...)` with no functions, types or relations.
pub(crate) fn profile_catalog<'py>(
    profile: &Bound<'py, PyAny>,
    dialect: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let catalog: Bound<'py, PyAny> = profile.getattr("binding_catalog")?;
    if catalog.is_truthy()? {
        return Ok(catalog);
    }
    let py: Python<'py> = profile.py();
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("dialect", dialect)?;
    arguments.set_item(
        "quoted_ignore_case",
        profile.getattr("quoted_identifiers_ignore_case")?,
    )?;
    arguments.set_item("known_functions", ())?;
    arguments.set_item("known_types", ())?;
    arguments.set_item("relations", PyDict::new(py))?;
    py.import(BINDING_CATALOG_MODULE)?
        .getattr("create_binding_catalog")?
        .call((), Some(&arguments))
}

/// `profile.function_return_types` items in order.
pub(crate) fn return_types(profile: &Bound<'_, PyAny>) -> PyResult<Pairs> {
    pairs(&profile.getattr("function_return_types")?)
}
