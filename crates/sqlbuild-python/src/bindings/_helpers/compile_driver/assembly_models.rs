//! Each compiled model of an assembled project, with its syntax checks and analysis fallback.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

use crate::bindings::_helpers::boundary::panics::NativeCompilerError;
use crate::bindings::_helpers::compile_driver::assembly_analysis::{
    ANALYSIS_MODELS_MODULE, AnalysisContext, model_stem, selected_for_analysis,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::hand_built::compiled_model::compiled_model as hand_built_model;

const NATIVE_MODULE: &str = "sqlbuild._native";
const CURSOR_INTRINSICS_MODULE: &str =
    "sqlbuild.compiler.compile._helpers.render.cursor_intrinsics";
const MACROS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.macros";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const NATIVE_FAILURE_PREFIX: &str = "NativeCompilerError: ";
const HOOK_NAMES: [&str; 2] = ["pre_hooks", "post_hooks"];

/// The Python stages each model's assembly calls, looked up once per project.
struct ModelStages<'py> {
    analysis_sql: Bound<'py, PyAny>,
    placeholders: Bound<'py, PyAny>,
    validate_hooks: Bound<'py, PyAny>,
    validate_sql: Bound<'py, PyAny>,
    macro_calls: Bound<'py, PyAny>,
    native_input: Bound<'py, PyAny>,
}

/// One model's assembly inputs: the attached model, its native facts and its two gates.
struct ModelRequest<'a, 'py> {
    model_input: &'a Bound<'py, PyAny>,
    native_model: Bound<'py, PyAny>,
    sql_analysis_enabled: bool,
    sql_validation_enabled: bool,
}

/// Every model of the project, compiled in input order.
pub(crate) fn compiled_models<'py>(
    inputs: &Bound<'py, PyAny>,
    context: &AnalysisContext<'py>,
    (native_models, names): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = inputs.py();
    let native: Bound<'py, PyAny> = py.import(NATIVE_MODULE)?.into_any();
    let stages: ModelStages<'py> = ModelStages {
        analysis_sql: imported(
            py,
            CURSOR_INTRINSICS_MODULE,
            "cursor_intrinsics_analysis_sql",
        )?,
        placeholders: native.getattr("model_placeholders")?,
        validate_hooks: native.getattr("validate_hook_sql_syntax")?,
        validate_sql: native.getattr("validate_sql_syntax")?,
        macro_calls: imported(py, MACROS_MODULE, "find_macro_call_names")?,
        native_input: native.getattr("NativeModelInput")?,
    };
    let analysis_enabled: bool = context.sql_analysis_enabled.is_truthy()?;
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for (index, model_input) in inputs.getattr("model_inputs")?.try_iter()?.enumerate() {
        let model_input: Bound<'py, PyAny> = model_input?;
        let sql_analysis_enabled: bool = analysis_enabled
            && model_input.getattr("sql_validation_enabled")?.is_truthy()?
            && selected_for_analysis(&model_input, names)?;
        let request: ModelRequest<'_, 'py> = ModelRequest {
            model_input: &model_input,
            sql_analysis_enabled,
            sql_validation_enabled: selected_for_analysis(&model_input, names)?,
            native_model: native_models.get_item(index)?,
        };
        models.push(compiled_model(&stages, context, &request)?);
    }
    PyTuple::new(py, models)
}

/// `_assemble_compiled_model`.
fn compiled_model<'py>(
    stages: &ModelStages<'py>,
    context: &AnalysisContext<'py>,
    request: &ModelRequest<'_, 'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let model_input: &Bound<'py, PyAny> = request.model_input;
    let py: Python<'py> = model_input.py();
    let model_name: Bound<'py, PyAny> = model_stem(model_input)?;
    let syntax_validated: bool = request.native_model.getattr("syntax_valid")?.is_truthy()?;
    let config_values: Bound<'py, PyAny> = model_input.getattr("config")?.getattr("values")?;
    let analysis_query_sql: Bound<'py, PyAny> = call_with(
        &stages.analysis_sql,
        &[
            ("sql", model_input.getattr("query_sql")?),
            (
                "cursor_type",
                config_values.call_method1("get", ("cursor_type",))?,
            ),
        ],
    )?;
    let placeholders: Bound<'py, PyAny> = stages.placeholders.call1((model_input,))?;
    let input_validated: bool = model_input.getattr("sql_validation_enabled")?.is_truthy()?;
    let location: Bound<'py, PyTuple> = PyTuple::new(
        py,
        [
            model_name.clone(),
            model_input.getattr("model_file")?.getattr("file_path")?,
        ],
    )?;
    let syntax: Bound<'py, PyTuple> = PyTuple::new(
        py,
        [
            placeholders.clone(),
            context.profile.getattr("sql_analysis_dialect")?,
        ],
    )?;
    let validates: bool = input_validated && !syntax_validated;
    if request.sql_validation_enabled && validates {
        for hook_name in HOOK_NAMES {
            stages.validate_hooks.call1((
                config_values.call_method1("get", (hook_name,))?,
                hook_name,
                &location,
                &syntax,
            ))?;
        }
    }
    let mut session_analysis: Bound<'py, PyAny> = py.None().into_bound(py);
    let mut fallback: Bound<'py, PyAny> = py.None().into_bound(py);
    if request.sql_analysis_enabled {
        let analyses: &Bound<'py, PyAny> = &context.analyses;
        let position: Bound<'py, PyAny> = if analyses.is_none() {
            py.None().into_bound(py)
        } else {
            analyses
                .getattr("positions")?
                .call_method1("get", (&model_name,))?
        };
        if analyses.is_none() || position.is_none() {
            return Err(NativeCompilerError::new_err(format!(
                "{NATIVE_FAILURE_PREFIX}native model analysis: the session returned no \
                 analysis for model '{}'",
                model_name.str()?
            )));
        }
        session_analysis = PyTuple::new(py, [analyses.getattr("session")?, position])?.into_any();
        if !analyses.getattr("succeeded")?.contains(&model_name)? {
            if validates {
                stages
                    .validate_sql
                    .call1((&analysis_query_sql, &location, &syntax))?;
            }
            fallback = fallback_columns(context, &analysis_query_sql, &placeholders)?;
        }
    } else if request.sql_validation_enabled && validates {
        stages
            .validate_sql
            .call1((&analysis_query_sql, &location, &syntax))?;
    }
    let declared_macro_deps: Bound<'py, PyAny> = model_input.getattr("macro_deps")?;
    let macro_deps: Bound<'py, PyAny> = if declared_macro_deps.is_truthy()? {
        declared_macro_deps
    } else {
        stages
            .macro_calls
            .call1((model_input.getattr("macro_source_sql")?,))?
    };
    let native_model: &Bound<'py, PyAny> = &request.native_model;
    if model_input.is_instance(&stages.native_input)? {
        let macro_list: Bound<'py, PyList> =
            PyList::new(py, macro_deps.try_iter()?.collect::<PyResult<Vec<_>>>()?)?;
        return model_input.call_method1(
            "compiled_model",
            ((
                native_model.getattr("deps")?,
                session_analysis,
                fallback,
                native_model.getattr("dynamic_contract")?,
                macro_list,
            ),),
        );
    }
    let analysis: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "HandBuiltAnalysis")?,
        &[
            ("session", session_analysis),
            ("fallback", fallback),
            (
                "standalone_proof",
                native_model.getattr("dynamic_contract")?,
            ),
        ],
    )?;
    hand_built_model(
        model_input,
        &native_model.getattr("deps")?,
        &analysis,
        &macro_deps,
    )
}

/// The columns a parse-only native query inference reads from a model whose analysis failed.
fn fallback_columns<'py>(
    context: &AnalysisContext<'py>,
    analysis_query_sql: &Bound<'py, PyAny>,
    placeholders: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = analysis_query_sql.py();
    let query: Bound<'py, PyAny> = call_with(
        &imported(py, ANALYSIS_MODELS_MODULE, "NativeColumnQuery")?,
        &[
            ("sql", analysis_query_sql.clone()),
            ("mode", PyString::new(py, "parse").into_any()),
            ("placeholders", placeholders.clone()),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "infer_native_query_column_rows")?,
        &[
            ("queries", PyTuple::new(py, [query])?.into_any()),
            ("profile", context.profile.clone()),
            ("column_nullability_by_table", context.nullability.clone()),
        ],
    )?
    .get_item(0)?
    .get_item(1)
}

/// `_project_binding_diagnostics`: every analysed model's located binding diagnostics.
pub(crate) fn project_binding_diagnostics<'py>(
    models: &Bound<'py, PyTuple>,
    analyses: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut diagnostics: Vec<Bound<'py, PyAny>> = Vec::new();
    if analyses.is_none() {
        return Ok(diagnostics);
    }
    let positions: Bound<'py, PyAny> = analyses.getattr("positions")?;
    for model in models.as_any().try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        if positions.contains(model.getattr("name")?)? {
            for diagnostic in model.getattr("binding_diagnostics")?.try_iter()? {
                diagnostics.push(diagnostic?);
            }
        }
    }
    Ok(diagnostics)
}

/// `_binding_rows`: each analysed model's raw binding rows by model name.
pub(crate) fn binding_rows<'py>(analyses: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = analyses.py();
    let rows_by_name: Bound<'py, PyDict> = PyDict::new(py);
    if analyses.is_none() {
        return Ok(rows_by_name);
    }
    let session: Bound<'py, PyAny> = analyses.getattr("session")?;
    if session.is_none() {
        return Ok(rows_by_name);
    }
    let rows: Bound<'py, PyAny> = session.call_method0("binding_rows")?;
    for item in analyses
        .getattr("positions")?
        .call_method0("items")?
        .try_iter()?
    {
        let item: Bound<'py, PyAny> = item?;
        rows_by_name.set_item(item.get_item(0)?, rows.get_item(item.get_item(1)?)?)?;
    }
    Ok(rows_by_name)
}
