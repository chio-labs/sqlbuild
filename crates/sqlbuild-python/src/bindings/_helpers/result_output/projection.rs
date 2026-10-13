//! Executor results matched to the canonical terminals of the installed event index.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyRef, PyResult, Python};
use pyo3::types::{PyFloat, PyInt};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::plan_output::values::text;
use crate::bindings::_helpers::result_output::terminal_index::{TerminalEventIndex, current_index};

const RUN_MODELS: &str = "sqlbuild.executor.run.models";
const BUILD_MODELS: &str = "sqlbuild.executor.build.models";
const LOAD_MODELS: &str = "sqlbuild.executor.load.models";
const PYTHON_NODE_MODELS: &str = "sqlbuild.executor.python_nodes.models";
const TESTING_MODELS: &str = "sqlbuild.executor.testing.models";
const AUDITING_MODELS: &str = "sqlbuild.executor.auditing.models";
const CLONE_MODELS: &str = "sqlbuild.executor.clone.models";
const SQL_TEST_ID_MODULE: &str = "sqlbuild.executor.testing.main.resource_id";
const AUDIT_ID_MODULE: &str = "sqlbuild.executor.auditing.main.resource_id";

/// The executor result types that result output distinguishes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ResultKind {
    Model,
    Seed,
    Function,
    Load,
    PythonNode,
    PythonCheck,
    SqlTest,
    Audit,
    CloneItem,
    Other,
}

/// The kind of one executor result, by its Python class.
pub(crate) fn result_kind(result: &Bound<'_, PyAny>) -> PyResult<ResultKind> {
    let py: Python<'_> = result.py();
    let kinds: [(&str, &str, ResultKind); 9] = [
        (RUN_MODELS, "ModelExecutionResult", ResultKind::Model),
        (BUILD_MODELS, "SeedExecutionResult", ResultKind::Seed),
        (
            BUILD_MODELS,
            "FunctionExecutionResult",
            ResultKind::Function,
        ),
        (LOAD_MODELS, "LoadExecutionResult", ResultKind::Load),
        (
            PYTHON_NODE_MODELS,
            "PythonNodeExecutionResult",
            ResultKind::PythonNode,
        ),
        (
            PYTHON_NODE_MODELS,
            "PythonCheckExecutionResult",
            ResultKind::PythonCheck,
        ),
        (
            TESTING_MODELS,
            "SqlTestExecutionResult",
            ResultKind::SqlTest,
        ),
        (AUDITING_MODELS, "AuditExecutionResult", ResultKind::Audit),
        (CLONE_MODELS, "CloneItemResult", ResultKind::CloneItem),
    ];
    for (module, class_name, kind) in kinds {
        if result.is_instance(&imported(py, module, class_name)?)? {
            return Ok(kind);
        }
    }
    Ok(ResultKind::Other)
}

/// `sql_test_resource_id` of one SQL test result.
pub(crate) fn sql_test_check_id(result: &Bound<'_, PyAny>) -> PyResult<String> {
    let fields: Vec<(&str, Bound<'_, PyAny>)> =
        ["test_name", "source_path", "block_index", "case_name"]
            .into_iter()
            .map(|name| Ok((name, result.getattr(name)?)))
            .collect::<PyResult<_>>()?;
    call_with(
        &imported(result.py(), SQL_TEST_ID_MODULE, "sql_test_resource_id")?,
        &fields,
    )?
    .extract()
}

/// `audit_resource_id` of one audit result.
pub(crate) fn audit_check_id(result: &Bound<'_, PyAny>) -> PyResult<String> {
    let fields: Vec<(&str, Bound<'_, PyAny>)> = [
        ("audit_name", "audit_name"),
        ("attachment_kind", "attachment_kind"),
        ("attached_target_kind", "attached_target_kind"),
        ("attached_target_name", "attached_target_name"),
        ("attached_column_name", "attached_column_name"),
    ]
    .into_iter()
    .map(|(keyword, name)| Ok((keyword, result.getattr(name)?)))
    .collect::<PyResult<_>>()?;
    call_with(
        &imported(result.py(), AUDIT_ID_MODULE, "audit_resource_id")?,
        &fields,
    )?
    .extract()
}

/// The canonical resource name and identifier of an executor result.
pub(crate) fn resource_identity(result: &Bound<'_, PyAny>) -> PyResult<Option<(String, String)>> {
    let name = |field: &str| -> PyResult<String> { text(&result.getattr(field)?) };
    Ok(Some(match result_kind(result)? {
        ResultKind::Model => {
            let resource: String = name("model_name")?;
            (resource.clone(), format!("model:{resource}"))
        }
        ResultKind::Seed => {
            let resource: String = name("seed_name")?;
            (resource.clone(), format!("seed:{resource}"))
        }
        ResultKind::Function => {
            let resource: String = name("function_name")?;
            (
                resource.clone(),
                format!("{}:{resource}", name("function_kind")?),
            )
        }
        ResultKind::Load => {
            let resource: String = name("source_name")?;
            (resource.clone(), format!("source:{resource}"))
        }
        ResultKind::PythonNode => {
            let resource: String = name("node_name")?;
            let kind: String = text(&result.getattr("kind")?.getattr("value")?)?;
            (resource.clone(), format!("{kind}:{resource}"))
        }
        ResultKind::PythonCheck => {
            let resource: String = name("node_name")?;
            (resource.clone(), format!("check:{resource}"))
        }
        ResultKind::SqlTest => (name("test_name")?, sql_test_check_id(result)?),
        ResultKind::Audit => (name("audit_name")?, audit_check_id(result)?),
        ResultKind::CloneItem | ResultKind::Other => return Ok(None),
    }))
}

/// `round(value)`: the nearest integer, ties to even.
pub(crate) fn rounded(py: Python<'_>, value: f64) -> PyResult<Bound<'_, PyAny>> {
    py.import("builtins")?.getattr("round")?.call1((value,))
}

/// A number from Python: an `int` (including `bool`) or a `float`.
pub(crate) fn number(value: &Bound<'_, PyAny>) -> PyResult<Option<f64>> {
    if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() {
        return Ok(Some(value.extract()?));
    }
    Ok(None)
}

/// Results matched against the installed terminal event index, if any.
pub(crate) struct Projection<'py> {
    py: Python<'py>,
    index: Option<PyRef<'py, TerminalEventIndex>>,
    /// Scenario whose resources are namespaced under `scenario:<name>:`.
    pub(crate) scenario: Option<String>,
}

impl<'py> Projection<'py> {
    pub(crate) fn installed(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            py,
            index: current_index(py)?,
            scenario: None,
        })
    }

    fn namespaced(&self, resource_id: String) -> String {
        match &self.scenario {
            Some(scenario) => format!("scenario:{scenario}:{resource_id}"),
            None => resource_id,
        }
    }

    /// The latest terminal of a resource, or `None` without one or without an index.
    fn terminal(
        &self,
        resource_name: &str,
        resource_id: &str,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        match &self.index {
            Some(index) => index.latest_terminal(self.py, resource_name, Some(resource_id)),
            None => Ok(None),
        }
    }

    /// The strongest aggregate terminal of the invocation.
    pub(crate) fn lifecycle_terminal(&self) -> PyResult<Option<Bound<'py, PyAny>>> {
        match &self.index {
            Some(index) => index.aggregate_terminal(self.py),
            None => Ok(None),
        }
    }

    /// Whether the resource has a terminal; always true without an index.
    pub(crate) fn resource_terminal_recorded(
        &self,
        resource_name: &str,
        resource_id: &str,
    ) -> PyResult<bool> {
        if self.index.is_none() {
            return Ok(true);
        }
        Ok(self
            .terminal(resource_name, &self.namespaced(resource_id.to_owned()))?
            .is_some())
    }

    /// Whether an executor result has a terminal.
    pub(crate) fn terminal_recorded(&self, result: &Bound<'py, PyAny>) -> PyResult<bool> {
        match resource_identity(result)? {
            Some((name, resource_id)) => self.resource_terminal_recorded(&name, &resource_id),
            None => Ok(self.index.is_none()),
        }
    }

    /// The results that have a terminal.
    pub(crate) fn terminal_results(
        &self,
        results: &Bound<'py, PyAny>,
    ) -> PyResult<Vec<Bound<'py, PyAny>>> {
        let mut kept: Vec<Bound<'py, PyAny>> = Vec::new();
        for result in results.try_iter()? {
            let result: Bound<'py, PyAny> = result?;
            if self.terminal_recorded(&result)? {
                kept.push(result);
            }
        }
        Ok(kept)
    }

    /// The terminal's `duration_ms`, or the fallback without an index.
    pub(crate) fn resource_duration(
        &self,
        (resource_name, resource_id): (&str, &str),
        fallback: Option<f64>,
    ) -> PyResult<Option<f64>> {
        if self.index.is_none() {
            return Ok(fallback);
        }
        let Some(terminal) =
            self.terminal(resource_name, &self.namespaced(resource_id.to_owned()))?
        else {
            return Ok(None);
        };
        number(
            &terminal
                .getattr("payload")?
                .call_method1("get", ("duration_ms",))?,
        )
    }

    /// The rounded canonical duration of a result, else its own `duration_ms`.
    pub(crate) fn result_duration(
        &self,
        result: &Bound<'py, PyAny>,
        fallback: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let Some((name, resource_id)) = resource_identity(result)? else {
            return Ok(fallback.clone());
        };
        match self.resource_duration((&name, &resource_id), number(fallback)?)? {
            Some(duration) => rounded(self.py, duration),
            None => Ok(self.py.None().into_bound(self.py)),
        }
    }
}
