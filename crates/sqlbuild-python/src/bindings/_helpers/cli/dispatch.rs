//! `sqb` command dispatch: the native route table applied to a parsed namespace.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_cli::dispatch::main::command_dispatch::command_dispatch;
use sqlbuild_cli::dispatch::main::unavailable_handler::unavailable_handler;
use sqlbuild_cli::dispatch::models::{
    ClassRef, CommandFacts, DiffSide, Dispatch, DispatchFailure, Field, Route, Source,
};
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const EXCEPTIONS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const ENTRY_MODELS_MODULE: &str = "sqlbuild.cli.entry.models";
const WAREHOUSES_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.warehouses";
const WAREHOUSE_SCOPE_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.warehouse_scope";
const LAUNCH_RECORD_MODULE: &str = "sqlbuild.cli.entry.main._withhold_launch_record";
const DIFF_VALIDATION_MODULE: &str = "sqlbuild.cli.commands._helpers.diff.validation";
const FORMAT_PATHS_MODULE: &str = "sqlbuild.cli.commands._helpers.lint.positional_paths";
const PATHLIB_MODULE: &str = "pathlib";
const COMMENT_PREFIX: &str = "#";
const UTF8: &str = "utf-8";

/// One invocation being dispatched: its namespace and the values derived from it once.
struct Invocation<'py> {
    args: Bound<'py, PyAny>,
    project_dir: Bound<'py, PyAny>,
    select: Bound<'py, PyTuple>,
    selector_files: Bound<'py, PyTuple>,
}

impl<'py> Invocation<'py> {
    fn py(&self) -> Python<'py> {
        self.args.py()
    }

    fn attr(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        self.args.getattr(name)
    }

    fn flag(&self, name: &str) -> PyResult<bool> {
        self.attr(name)?.is_truthy()
    }

    fn present(&self, name: &str) -> PyResult<bool> {
        Ok(!self.attr(name)?.is_none())
    }

    /// The value of one handler argument or request field.
    fn value(&self, source: Source) -> PyResult<Bound<'py, PyAny>> {
        let py: Python<'py> = self.py();
        match source {
            Source::Attr(name) => self.attr(name),
            Source::TupleOf(name) => tuple_of(&self.attr(name)?),
            Source::Text(name) => Ok(self.attr(name)?.str()?.into_any()),
            Source::OrDefault(name, default) => {
                let value: Bound<'py, PyAny> = self.attr(name)?;
                if value.is_truthy()? {
                    Ok(value)
                } else {
                    Ok(PyString::new(py, default).into_any())
                }
            }
            Source::OptionalPath(name) => {
                let value: Bound<'py, PyAny> = self.attr(name)?;
                if value.is_none() {
                    Ok(value)
                } else {
                    path_class(py)?.call1((value,))
                }
            }
            Source::Flag(value) => value.into_bound_py_any(py),
            Source::Member(class, name) => class_object(py, class)?.call1((self.attr(name)?,)),
            Source::Constant(class, value) => class_object(py, class)?.call1((value,)),
            Source::Nested(class, fields) => {
                class_object(py, class)?.call((), Some(&self.fields(fields)?))
            }
            Source::ProjectDir => Ok(self.project_dir.clone()),
            Source::EffectiveProjectDir => {
                if self.project_dir.is_none() {
                    path_class(py)?.call_method0("cwd")
                } else {
                    Ok(self.project_dir.clone())
                }
            }
            Source::Select => Ok(self.select.clone().into_any()),
            Source::SelectorFiles => Ok(self.selector_files.clone().into_any()),
            Source::QueryLimit => {
                if self.flag("query_no_limit")? {
                    Ok(py.None().into_bound(py))
                } else {
                    self.attr("query_limit")
                }
            }
            Source::DiffName(side) => self.diff_name(side),
            Source::FormatSelect => {
                let paths: Bound<'py, PyAny> = call_with(
                    &imported(py, FORMAT_PATHS_MODULE, "format_path_selectors")?,
                    &[
                        ("paths", tuple_of(&self.attr("format_paths")?)?),
                        ("project_dir", self.project_dir.clone()),
                        ("cwd", path_class(py)?.call_method0("cwd")?),
                    ],
                )?;
                concatenated(&self.select.clone().into_any(), &paths)
            }
            Source::ScenarioSelect => concatenated(
                &self.attr("scenario_selector")?,
                &self.select.clone().into_any(),
            ),
        }
    }

    fn diff_name(&self, side: DiffSide) -> PyResult<Bound<'py, PyAny>> {
        let range: Bound<'py, PyAny> = self.attr("target_range")?;
        if range.is_none() {
            return Ok(range);
        }
        let parsed: Bound<'py, PyAny> =
            imported(self.py(), DIFF_VALIDATION_MODULE, "parse_diff_name_range")?
                .call1((range,))?;
        parsed.get_item(match side {
            DiffSide::From => 0,
            DiffSide::To => 1,
        })
    }

    fn fields(&self, fields: &[Field]) -> PyResult<Bound<'py, PyDict>> {
        let values: Bound<'py, PyDict> = PyDict::new(self.py());
        for field in fields {
            values.set_item(field.name, self.value(field.source)?)?;
        }
        Ok(values)
    }

    fn facts(&self) -> PyResult<CommandFacts> {
        let command: Option<String> = optional_text(&self.attr("command")?)?;
        let subcommand_attribute: &str = match command.as_deref() {
            Some("dbt") => "dbt_command",
            Some("scenario") => "scenario_command",
            _ => "command",
        };
        Ok(CommandFacts {
            subcommand: optional_text(&self.attr(subcommand_attribute)?)?,
            command,
            json: self.flag("json")?,
            refactor_target: self.present("refactor_target")?,
            from_target: self.present("from_target")?,
            contract_ready: self.present("contract_command")? && self.present("contract_from")?,
            format_diff: self.flag("format_diff")?,
            format_fix: self.flag("format_fix")?,
            format_fixtures_only: self.flag("format_fixtures_only")?,
            scenario_local: self.flag("scenario_local")?,
            scenario_retain: self.flag("scenario_retain")?,
            scenario_snapshot_sync: self.flag("scenario_sync_snapshots")?
                || self.flag("scenario_refresh")?,
        })
    }
}

fn optional_text(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.str()?.to_string()))
}

fn path_class(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, PATHLIB_MODULE, "Path")
}

fn class_object<'py>(py: Python<'py>, class: ClassRef) -> PyResult<Bound<'py, PyAny>> {
    imported(py, class.module, class.name)
}

fn tuple_of<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(value.py(), value.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any())
}

fn concatenated<'py>(
    first: &Bound<'py, PyAny>,
    second: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let items: Vec<Bound<'py, PyAny>> = first
        .try_iter()?
        .chain(second.try_iter()?)
        .collect::<PyResult<_>>()?;
    Ok(PyTuple::new(first.py(), items)?.into_any())
}

/// `CliUserError(message, code=..., help=...)`.
fn user_error(py: Python<'_>, failure: DispatchFailure) -> PyErr {
    let raised = (|| {
        let keywords: Bound<'_, PyDict> = PyDict::new(py);
        keywords.set_item("code", failure.code)?;
        keywords.set_item("help", failure.help)?;
        imported(py, EXCEPTIONS_MODULE, "CliUserError")?.call((failure.message,), Some(&keywords))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// `--select` and the selectors of every `--select-file`, with each file's selector count.
fn selector_inputs<'py>(
    args: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyTuple>, Bound<'py, PyTuple>)> {
    let py: Python<'py> = args.py();
    let mut selectors: Vec<Bound<'py, PyAny>> = args
        .getattr("select")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let summary_class: Bound<'py, PyAny> =
        imported(py, ENTRY_MODELS_MODULE, "SelectorFileSummary")?;
    let mut files: Vec<Bound<'py, PyAny>> = Vec::new();
    for raw_path in args.getattr("select_file")?.try_iter()? {
        let path: Bound<'py, PyAny> = path_class(py)?.call1((raw_path?,))?;
        let keywords: Bound<'py, PyDict> = PyDict::new(py);
        keywords.set_item("encoding", UTF8)?;
        let lines: Vec<String> = path
            .call_method("read_text", (), Some(&keywords))?
            .call_method0("splitlines")?
            .extract()?;
        let mut count: usize = 0;
        for line in &lines {
            let stripped: &str = python_strip(line);
            if stripped.is_empty() || stripped.starts_with(COMMENT_PREFIX) {
                continue;
            }
            selectors.push(PyString::new(py, stripped).into_any());
            count += 1;
        }
        files.push(call_with(
            &summary_class,
            &[
                ("path", path),
                ("selector_count", count.into_bound_py_any(py)?),
            ],
        )?);
    }
    Ok((PyTuple::new(py, selectors)?, PyTuple::new(py, files)?))
}

/// Call the route's command implementation, or the handler a test injected for its slot.
fn call_route<'py>(
    invocation: &Invocation<'py>,
    route: &Route,
    handler: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.py();
    let mut positional: Vec<Bound<'py, PyAny>> = Vec::new();
    let keywords: Bound<'py, PyDict> = PyDict::new(py);
    let (callable, positional_count) = match handler {
        Some(handler) => (handler, route.shape.slot_positional),
        None => {
            let (module, function) = route.implementation;
            if let Some(extra) = route.implementation_extra {
                keywords.set_item(extra.name, invocation.value(extra.source)?)?;
            }
            let count: usize = if route.shape.implementation_keywords {
                0
            } else {
                route.shape.slot_positional
            };
            (imported(py, module, function)?, count)
        }
    };
    for (index, field) in route.arguments.iter().enumerate() {
        let value: Bound<'py, PyAny> = invocation.value(field.source)?;
        if index < positional_count {
            positional.push(value);
        } else {
            keywords.set_item(field.name, value)?;
        }
    }
    callable.call(PyTuple::new(py, positional)?, Some(&keywords))
}

fn routed_command<'py>(
    args: &Bound<'py, PyAny>,
    handlers: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = args.py();
    let raw_project_dir: Bound<'py, PyAny> = args.getattr("project_dir")?;
    let project_dir: Bound<'py, PyAny> = if raw_project_dir.is_none() {
        raw_project_dir
    } else {
        path_class(py)?
            .call1((raw_project_dir,))?
            .call_method0("resolve")?
    };
    let (select, selector_files) = selector_inputs(args)?;
    if args.getattr("select_file")?.is_truthy()? {
        imported(py, LAUNCH_RECORD_MODULE, "withhold_launch_record")?.call0()?;
    }
    let invocation = Invocation {
        args: args.clone(),
        project_dir,
        select,
        selector_files,
    };
    match command_dispatch(&invocation.facts()?) {
        Dispatch::Nothing => 0.into_bound_py_any(py),
        Dispatch::Fail(failure) => Err(user_error(py, failure)),
        Dispatch::Run(route, failure) => {
            let handler: Option<Bound<'py, PyAny>> = match handlers {
                Some(handlers) => {
                    let slot: Bound<'py, PyAny> = handlers.getattr(route.slot)?;
                    if slot.is_none() {
                        let command: String = args.getattr("command")?.str()?.to_string();
                        let code: &str = route.unavailable_code.unwrap_or("C000");
                        return Err(user_error(py, unavailable_handler(&command, code)));
                    }
                    Some(slot)
                }
                None => None,
            };
            if let Some(failure) = failure {
                return Err(user_error(py, failure));
            }
            call_route(&invocation, route, handler)
        }
    }
}

/// Run a parsed command's handler, imported only when it runs unless `handlers` injects it.
#[pyfunction]
#[pyo3(signature = (*, args, handlers=None))]
fn dispatch_cli_command<'py>(
    args: &Bound<'py, PyAny>,
    handlers: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = args.py();
    let warehouse: Bound<'py, PyAny> = args.getattr("warehouse")?;
    if !warehouse.is_none() {
        let raw_project_dir: Bound<'py, PyAny> = args.getattr("project_dir")?;
        let project_dir: Bound<'py, PyAny> = if raw_project_dir.is_none() {
            path_class(py)?.call_method0("cwd")?
        } else {
            path_class(py)?
                .call1((raw_project_dir,))?
                .call_method0("resolve")?
        };
        call_with(
            &imported(py, WAREHOUSES_MODULE, "validate_cli_warehouse")?,
            &[
                ("cli_warehouse", warehouse.clone()),
                ("project_dir", project_dir),
            ],
        )?;
    }
    let scope: Bound<'py, PyAny> = call_with(
        &imported(py, WAREHOUSE_SCOPE_MODULE, "command_warehouse_scope")?,
        &[
            ("command", args.getattr("command")?),
            ("cli_warehouse", warehouse),
            ("cli_vars", args.getattr("vars")?),
        ],
    )?;
    within(&scope, |_| routed_command(args, handlers.as_ref()))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(dispatch_cli_command, module)?)
}
