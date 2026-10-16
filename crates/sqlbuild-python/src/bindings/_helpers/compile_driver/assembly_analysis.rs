//! Project assembly's inference profile, binding catalog, source shapes and model analysis.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple};

use sqlbuild_analysis::assembly::analysis_session::main::native_dialect::native_dialect;

use crate::bindings::_helpers::analysis::binding_catalog::{BindingCatalog, ignores_quoted_case};
use crate::bindings::_helpers::compile_driver::analysis_cache::analysis_cache_context;
use crate::bindings::_helpers::compile_driver::assembly::AssemblyRequest;
use crate::bindings::_helpers::compile_driver::compile_timings::{
    record_compile_cpu_timing, record_compile_timing,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

const GENERIC_DIALECT: &str = "generic";
const UDF_PREFIX: &str = "__sqlbuild_udf_";

/// The analysis state every assembled model and the project share.
pub(crate) struct AnalysisContext<'py> {
    pub(crate) profile: Bound<'py, PyAny>,
    /// Python's `settings.sql_analysis and not skip_column_inference`, as that value.
    pub(crate) sql_analysis_enabled: Bound<'py, PyAny>,
    pub(crate) column_types: Bound<'py, PyAny>,
    pub(crate) nullability: Bound<'py, PyAny>,
    pub(crate) complete_schemas: Bound<'py, PyAny>,
    pub(crate) dynamic_families: Bound<'py, PyAny>,
    /// The `NativeModelAnalyses`, or `None` when no model was analysed.
    pub(crate) analyses: Bound<'py, PyAny>,
}

/// Whether `model_input` is selected for analysis by `names` (`None` selects every model).
pub(crate) fn selected_for_analysis(
    model_input: &Bound<'_, PyAny>,
    names: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    Ok(names.is_none() || names.contains(model_stem(model_input)?)?)
}

/// The model's name: its file's stem.
pub(crate) fn model_stem<'py>(model_input: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    model_input
        .getattr("model_file")?
        .getattr("file_path")?
        .getattr("stem")
}

/// Python's `left and not right`.
pub(crate) fn and_not<'py>(
    left: &Bound<'py, PyAny>,
    right: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if !left.is_truthy()? {
        return Ok(left.clone());
    }
    Ok(PyBool::new(left.py(), !right.is_truthy()?)
        .to_owned()
        .into_any())
}

/// The profile, catalog, declared relations and model analyses of `request`'s project.
pub(crate) fn analysis_context<'py>(
    py: Python<'py>,
    request: &AssemblyRequest,
) -> PyResult<AnalysisContext<'py>> {
    let inputs: &Bound<'py, PyAny> = request.inputs.bind(py);
    let sql_analysis_enabled: Bound<'py, PyAny> = and_not(
        &inputs
            .getattr("effective_settings")?
            .getattr("sql_analysis")?,
        request.skip_column_inference.bind(py),
    )?;
    let relations: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::DeclaredRelations)?.call1((inputs,))?;
    let column_types: Bound<'py, PyAny> = relations.get_item(0)?;
    let nullability: Bound<'py, PyAny> = relations.get_item(1)?;
    let complete_schemas: Bound<'py, PyAny> = relations.get_item(2)?;
    let dynamic_families: Bound<'py, PyAny> = dynamic_families_by_table(inputs)?.into_any();
    let profile: Bound<'py, PyAny> =
        profile_with_catalog(inputs, request.inference_profile.bind(py), &column_types)?;
    let mut context: AnalysisContext<'py> = AnalysisContext {
        profile,
        sql_analysis_enabled,
        column_types,
        nullability,
        complete_schemas,
        dynamic_families,
        analyses: py.None().into_bound(py),
    };
    if context.sql_analysis_enabled.is_truthy()? {
        record_expression_shapes(inputs, &context)?;
    }
    let catalog: Bound<'py, PyAny> = context.profile.getattr("binding_catalog")?;
    catalog
        .getattr("native")?
        .call_method1("update_relations", (&context.complete_schemas,))?;
    catalog
        .getattr("schemas")?
        .call_method1("update", (&context.complete_schemas,))?;
    context.analyses = model_analyses(request, &context)?;
    Ok(context)
}

/// `_build_dynamic_families_by_table`: enforced contract models' dynamic column families.
fn dynamic_families_by_table<'py>(inputs: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = inputs.py();
    let enforced: Bound<'py, PyAny> =
        registry::class(py, RecordId::ContractPolicy)?.getattr("ENFORCED")?;
    let families: Bound<'py, PyDict> = PyDict::new(py);
    for model_input in inputs.getattr("model_inputs")?.try_iter()? {
        let model_input: Bound<'py, PyAny> = model_input?;
        let contract: Bound<'py, PyAny> = model_input
            .getattr("config")?
            .getattr("values")?
            .call_method1("get", ("contract",))?;
        if !contract.eq(&enforced)? {
            continue;
        }
        let schema_entry: Bound<'py, PyAny> = model_input.getattr("schema_entry")?;
        if schema_entry.is_none() {
            continue;
        }
        let dynamic_columns: Bound<'py, PyAny> = schema_entry.getattr("dynamic_columns")?;
        if dynamic_columns.is_truthy()? {
            families.set_item(schema_entry.getattr("name")?, dynamic_columns)?;
        }
    }
    Ok(families)
}

/// Sorted function names and declared types registered with native validation.
pub(crate) fn declared_names<'py>(
    inputs: &Bound<'py, PyAny>,
    column_types: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = inputs.py();
    let functions: Bound<'py, PyAny> = inputs.getattr("sql_function_inputs")?;
    let names: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::KnownFunctionNames)?.call1((functions.clone(),))?;
    let types: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::KnownDeclaredTypes)?,
        &[
            ("functions", functions),
            ("column_types", column_types.clone()),
        ],
    )?;
    Ok((names, types))
}

/// The adapter's profile with project declarations, the native dialect and a binding catalog.
fn profile_with_catalog<'py>(
    inputs: &Bound<'py, PyAny>,
    inference_profile: &Bound<'py, PyAny>,
    column_types: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let replace: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?;
    let profile: Bound<'py, PyAny> = if inference_profile.is_truthy()? {
        inference_profile.clone()
    } else {
        host::entry(py, AdapterHost::ExpressionInferenceProfile)?.call0()?
    };
    let (known_functions, known_types): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        declared_names(inputs, column_types)?;
    let dialect: Bound<'py, PyAny> = profile.getattr("sql_analysis_dialect")?;
    let ignore_case: Bound<'py, PyAny> = PyBool::new(
        py,
        ignores_quoted_case(&inputs.getattr("effective_connection")?, &dialect)?,
    )
    .to_owned()
    .into_any();
    let name: Option<String> = if dialect.is_none() {
        None
    } else {
        Some(dialect.extract()?)
    };
    let native: Bound<'py, PyAny> = match native_dialect(name.as_deref()) {
        Some(native) if Some(native) != name.as_deref() => PyString::new(py, native).into_any(),
        _ => dialect,
    };
    let profile: Bound<'py, PyAny> = replace.call(
        (profile.clone(),),
        Some(&keywords(
            py,
            &[
                ("semantic_known_functions", known_functions),
                ("semantic_known_types", known_types),
                ("quoted_identifiers_ignore_case", ignore_case),
                ("sql_analysis_dialect", native),
                (
                    "function_return_types",
                    function_return_types(inputs, &profile)?.into_any(),
                ),
            ],
        )?),
    )?;
    let dialect: Bound<'py, PyAny> = profile.getattr("sql_analysis_dialect")?;
    let dialect: String = if dialect.is_truthy()? {
        dialect.extract()?
    } else {
        GENERIC_DIALECT.to_owned()
    };
    let catalog: Bound<'py, PyAny> = Bound::new(
        py,
        BindingCatalog::create(
            py,
            (
                dialect,
                profile
                    .getattr("quoted_identifiers_ignore_case")?
                    .extract()?,
                profile.getattr("semantic_known_functions")?.extract()?,
                profile.getattr("semantic_known_types")?.extract()?,
            ),
            PyDict::new(py).as_any(),
        )?,
    )?
    .into_any();
    replace.call(
        (profile,),
        Some(&keywords(py, &[("binding_catalog", catalog)])?),
    )
}

/// The profile's function return types with each scalar project function's analysis name.
fn function_return_types<'py>(
    inputs: &Bound<'py, PyAny>,
    profile: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = inputs.py();
    let types: Bound<'py, PyDict> = PyDict::new(py);
    types.call_method1("update", (profile.getattr("function_return_types")?,))?;
    let scalar: Bound<'py, PyDict> = PyDict::new(py);
    for function in inputs.getattr("sql_function_inputs")?.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        if function.getattr("return_columns")?.is_truthy()? {
            continue;
        }
        let name: Bound<'py, PyAny> = function.getattr("name")?.str()?.into_any();
        let key: Bound<'py, PyAny> = PyString::new(py, UDF_PREFIX)
            .into_any()
            .add(name)?
            .call_method0("upper")?;
        scalar.set_item(key, function.getattr("returns")?)?;
    }
    types.update(scalar.as_mapping())?;
    Ok(types)
}

/// Record each expression source's analysed shape as its declared relation.
fn record_expression_shapes<'py>(
    inputs: &Bound<'py, PyAny>,
    context: &AnalysisContext<'py>,
) -> PyResult<()> {
    let py: Python<'py> = inputs.py();
    let mut sources: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut expressions: Vec<Bound<'py, PyAny>> = Vec::new();
    for source_input in inputs.getattr("source_inputs")?.try_iter()? {
        let source_input: Bound<'py, PyAny> = source_input?;
        let expression: Bound<'py, PyAny> = source_input
            .getattr("source_entry")?
            .getattr("expression")?;
        if expression.is_truthy()? {
            sources.push(source_input);
            expressions.push(expression);
        }
    }
    let shapes: Vec<Bound<'py, PyAny>> = call_with(
        &registry::native(py, NativeAttr::InferNativeExpressionSourceShapes)?,
        &[
            ("expressions", PyTuple::new(py, expressions)?.into_any()),
            ("profile", context.profile.clone()),
        ],
    )?
    .try_iter()?
    .collect::<PyResult<_>>()?;
    if shapes.len() != sources.len() {
        let relation: &str = if shapes.len() < sources.len() {
            "shorter"
        } else {
            "longer"
        };
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "zip() argument 2 is {relation} than argument 1"
        )));
    }
    let unknown: Bound<'py, PyAny> =
        registry::class(py, RecordId::InferredNullability)?.getattr("UNKNOWN")?;
    for (source_input, shape) in sources.iter().zip(shapes) {
        if shape.is_none() {
            continue;
        }
        let name: Bound<'py, PyAny> = source_input.getattr("source_entry")?.getattr("name")?;
        let declared_types: Bound<'py, PyAny> = context
            .column_types
            .call_method1("get", (&name, PyDict::new(py)))?;
        let declared_shape: Bound<'py, PyDict> = PyDict::new(py);
        for item in shape.call_method0("items")?.try_iter()? {
            let item: Bound<'py, PyAny> = item?;
            let column: Bound<'py, PyAny> = item.get_item(0)?;
            declared_shape.set_item(
                &column,
                declared_types.call_method1("get", (&column, item.get_item(1)?))?,
            )?;
        }
        context.complete_schemas.set_item(&name, &declared_shape)?;
        context.column_types.set_item(&name, &declared_shape)?;
        let nullability: Bound<'py, PyDict> = PyDict::new(py);
        for column in declared_shape.keys() {
            let known: Bound<'py, PyAny> = context
                .nullability
                .call_method1("get", (&name, PyDict::new(py)))?;
            nullability.set_item(&column, known.call_method1("get", (&column, &unknown))?)?;
        }
        context.nullability.set_item(&name, nullability)?;
    }
    Ok(())
}

/// Each selected model's native analysis, timed as `model_analysis_ms`, when SQL analysis runs.
fn model_analyses<'py>(
    request: &AssemblyRequest,
    context: &AnalysisContext<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.profile.py();
    if !context.sql_analysis_enabled.is_truthy()? {
        return Ok(py.None().into_bound(py));
    }
    let inputs: &Bound<'py, PyAny> = request.inputs.bind(py);
    let names: &Bound<'py, PyAny> = request.analysis_model_names.bind(py);
    let mode: &Bound<'py, PyAny> = request.column_lineage_mode.bind(py);
    let lineage_mode: Bound<'py, PyAny> = registry::class(py, RecordId::ColumnLineageMode)?;
    let rich: bool = mode.eq(lineage_mode.getattr("RICH")?)?;
    let allow_compact: bool = mode.eq(lineage_mode.getattr("FAST")?)? || rich;
    let flags: (Bound<'py, PyAny>, Bound<'py, PyAny>) = (
        PyBool::new(py, allow_compact).to_owned().into_any(),
        PyBool::new(py, rich).to_owned().into_any(),
    );
    let cache: Bound<'py, PyAny> = if names.ne(PyFrozenSet::empty(py)?)? {
        analysis_cache(request, context, &flags)?
    } else {
        py.None().into_bound(py)
    };
    record_compile_timing("model_analysis_ms", || {
        record_compile_cpu_timing(py, "model_analysis_cpu_ms", || {
            let (known_functions, known_types): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
                declared_names(inputs, &context.column_types)?;
            let mut model_inputs: Vec<Bound<'py, PyAny>> = Vec::new();
            for model_input in inputs.getattr("model_inputs")?.try_iter()? {
                let model_input: Bound<'py, PyAny> = model_input?;
                if model_input.getattr("sql_validation_enabled")?.is_truthy()?
                    && selected_for_analysis(&model_input, names)?
                {
                    model_inputs.push(model_input);
                }
            }
            let analysis_request: Bound<'py, PyAny> = call_with(
                &registry::class(py, RecordId::NativeModelAnalysisRequest)?,
                &[
                    ("known_functions", known_functions),
                    ("known_types", known_types),
                    ("model_inputs", PyTuple::new(py, model_inputs)?.into_any()),
                    ("column_nullability_by_table", context.nullability.clone()),
                    ("column_types_by_table", context.column_types.clone()),
                    ("inference_profile", context.profile.clone()),
                    ("allow_compact_analysis", flags.0.clone()),
                    ("rich_type_inference", flags.1.clone()),
                    ("analysis_cache", cache.clone()),
                    ("complete_binding_schemas", context.complete_schemas.clone()),
                    (
                        "dynamic_families_by_table",
                        context.dynamic_families.clone(),
                    ),
                ],
            )?;
            call_with(
                &registry::native(py, NativeAttr::AnalyzeNativeModelSql)?,
                &[("request", analysis_request)],
            )
        })
    })
}

/// The analysis cache context keyed by the project's declarations, target and vars.
fn analysis_cache<'py>(
    request: &AssemblyRequest,
    context: &AnalysisContext<'py>,
    (allow_compact, rich): &(Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.profile.py();
    let inputs: &Bound<'py, PyAny> = request.inputs.bind(py);
    let (known_functions, known_types): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        declared_names(inputs, &context.column_types)?;
    let namespace: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("known_functions", known_functions),
            ("known_types", known_types),
            ("target", inputs.getattr("effective_target_name")?),
            ("vars", inputs.getattr("effective_vars")?),
        ],
    )?;
    Ok(analysis_cache_context(
        request.analysis_cache_dir.bind(py),
        &context.profile,
        (allow_compact, rich),
        namespace.as_any(),
    )?
    .unwrap_or_else(|| py.None().into_bound(py)))
}
