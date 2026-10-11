//! JSON bindings for native `sqb rename` and `sqb mv`; expected failures return `{"error": ...}`.

use std::cell::RefCell;
use std::path::{Path, PathBuf};

use pyo3::prelude::{Bound, Py, PyAny, PyErr, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use serde::Serialize;
use serde::de::DeserializeOwned;
use serde_json::json;
use sqlbuild_refactor::refactoring::errors::{RefactorError, RefactorErrorKind};
use sqlbuild_refactor::refactoring::main::commit_refactor_plan::commit_refactor_plan;
use sqlbuild_refactor::refactoring::main::plan_refactor::plan_refactor;
use sqlbuild_refactor::refactoring::main::stage_refactor_plan::stage_refactor_plan;
use sqlbuild_refactor::refactoring::main::with_model_migration::with_model_migration;
use sqlbuild_refactor::refactoring::models::{
    DeclarationPlacement, ModelFacts, RefactorFacts, RefactorPlan, RefactorRequest,
};
use sqlbuild_refactor::refactoring::types::Originals;

use crate::bindings::_helpers::boundary::panics::{
    NativeCompilerError, compiler_guard, value_error,
};

fn decode<T: DeserializeOwned>(text: &str) -> PyResult<T> {
    serde_json::from_str(text).map_err(value_error)
}

fn encode<T: Serialize>(key: &str, result: Result<T, RefactorError>) -> PyResult<String> {
    let value = match result {
        Ok(value) => json!({ key: value }),
        Err(error) if error.kind == RefactorErrorKind::Internal => {
            return Err(NativeCompilerError::new_err(error.message));
        }
        Err(error) => json!({ "error": error }),
    };
    serde_json::to_string(&value).map_err(value_error)
}

/// Plan one refactoring; `declaration_placement((model, destination))` returns JSON placement.
#[pyfunction]
fn plan_refactor_json(
    py: Python<'_>,
    facts_json: &str,
    request_json: &str,
    declaration_placement: Py<PyAny>,
) -> PyResult<String> {
    compiler_guard(|| {
        let facts: RefactorFacts = decode(facts_json)?;
        let request: RefactorRequest = decode(request_json)?;
        let host_error: RefCell<Option<PyErr>> = RefCell::new(None);
        let host = |model: &str, destination: &str| {
            let placement = declaration_placement
                .call1(py, ((model, destination),))
                .and_then(|value| value.extract::<String>(py))
                .and_then(|text| decode::<DeclarationPlacement>(&text));
            placement.map_err(|error| {
                host_error.replace(Some(error));
                RefactorError::internal("the declaration-move host failed")
            })
        };
        let result = plan_refactor(&facts, &request, &host);
        if let Some(error) = host_error.into_inner() {
            return Err(error);
        }
        encode("plan", result)
    })
}

/// Copy the project inputs once, apply the plan in `staging_dir`, and return the originals.
#[pyfunction]
fn stage_refactor_plan_json(
    project_dir: &str,
    staging_dir: &str,
    plan_json: &str,
    copy_inputs: bool,
) -> PyResult<String> {
    compiler_guard(|| {
        let plan: RefactorPlan = decode(plan_json)?;
        encode(
            "originals",
            stage_refactor_plan(
                Path::new(project_dir),
                Path::new(staging_dir),
                &plan,
                copy_inputs,
            ),
        )
    })
}

/// The plan with model `migrate_from` added whenever the relation moves.
#[pyfunction]
#[pyo3(signature = (plan_json, before_json, after_json, originals_json))]
fn with_model_migration_json(
    plan_json: &str,
    before_json: &str,
    after_json: Option<&str>,
    originals_json: &str,
) -> PyResult<String> {
    compiler_guard(|| {
        let plan: RefactorPlan = decode(plan_json)?;
        let before: Vec<ModelFacts> = decode(before_json)?;
        let after: Option<Vec<ModelFacts>> = after_json.map(decode).transpose()?;
        let originals: Originals = decode(originals_json)?;
        encode(
            "plan",
            Ok(with_model_migration(
                &plan,
                &before,
                after.as_deref(),
                &originals,
            )),
        )
    })
}

/// Write a verified plan into the project, restoring every file if any write fails.
#[pyfunction]
fn commit_refactor_plan_json(
    project_dir: &str,
    originals_json: &str,
    plan_json: &str,
) -> PyResult<String> {
    compiler_guard(|| {
        let plan: RefactorPlan = decode(plan_json)?;
        let originals: Originals = decode(originals_json)?;
        let written =
            commit_refactor_plan(Path::new(project_dir), &originals, &plan).map(path_strings);
        encode("written", written)
    })
}

fn path_strings(paths: Vec<PathBuf>) -> Vec<String> {
    paths
        .into_iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_refactor_json, module)?)?;
    module.add_function(wrap_pyfunction!(stage_refactor_plan_json, module)?)?;
    module.add_function(wrap_pyfunction!(with_model_migration_json, module)?)?;
    module.add_function(wrap_pyfunction!(commit_refactor_plan_json, module)?)?;
    Ok(())
}
