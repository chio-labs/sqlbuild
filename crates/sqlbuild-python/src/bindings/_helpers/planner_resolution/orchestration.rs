//! Model, function and SQL-hook orchestration through adapter-owned rendering.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_resolution::values::{NATIVE_MODULE, string};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use pyo3::{IntoPyObject, PyErr, pyfunction, wrap_pyfunction};

const CONFIG_MODULE: &str = "sqlbuild.compiler.planner._helpers.resolve.config";
const INTRINSICS_MODULE: &str = "sqlbuild.compiler.planner._helpers.resolve.cursor_intrinsics";
const MODELS_MODULE: &str = "sqlbuild.compiler.planner.models";
const HOOK_MODULE: &str = "sqlbuild.compiler.discovery.models";
const ERROR_MODULE: &str = "sqlbuild.compiler.planner.exceptions";

struct Resolution<'py> {
    adapter: Bound<'py, PyAny>,
    context: Bound<'py, PyAny>,
    external: Bound<'py, PyAny>,
}

impl<'py> Resolution<'py> {
    fn resolve(
        &self,
        sql: Bound<'py, PyAny>,
        cursor: &[(&str, Bound<'py, PyAny>)],
    ) -> PyResult<Bound<'py, PyAny>> {
        let py = self.adapter.py();
        let mut source = vec![("query_sql", sql), ("adapter", self.adapter.clone())];
        for key in [
            "source_map",
            "source_warehouse_columns",
            "star_exclude_keyword",
        ] {
            source.push((key, self.context.getattr(key)?));
        }
        source.extend_from_slice(cursor);
        let mut resolved = call_with(
            &imported(py, NATIVE_MODULE, "resolve_source_references")?,
            &source,
        )?;
        let mut refs = vec![("query_sql", resolved), ("adapter", self.adapter.clone())];
        for key in ["model_locations", "seed_locations"] {
            refs.push((key, self.context.getattr(key)?));
        }
        refs.extend_from_slice(cursor);
        resolved = call_with(
            &imported(py, NATIVE_MODULE, "resolve_ref_references")?,
            &refs,
        )?;
        resolved = call_with(
            &imported(py, NATIVE_MODULE, "resolve_dbt_ref_references")?,
            &[
                ("query_sql", resolved),
                ("external_sql_reference_resolver", self.external.clone()),
            ],
        )?;
        let locations = self.context.getattr("function_locations")?;
        let locations = if locations.is_truthy()? {
            locations
        } else {
            PyDict::new(py).into_any()
        };
        for name in [
            "resolve_udf_references",
            "resolve_table_function_references",
        ] {
            resolved = call_with(
                &imported(py, NATIVE_MODULE, name)?,
                &[
                    ("query_sql", resolved),
                    ("function_locations", locations.clone()),
                    ("adapter", self.adapter.clone()),
                ],
            )?;
        }
        Ok(resolved)
    }

    fn assert_resolved(&self, sql: &Bound<'py, PyAny>, label: &str) -> PyResult<()> {
        call_with(
            &imported(
                self.adapter.py(),
                NATIVE_MODULE,
                "assert_no_unresolved_sql_markers",
            )?,
            &[
                ("sql", sql.clone()),
                (
                    "context",
                    string(self.adapter.py(), &format!("{label} planned SQL")),
                ),
            ],
        )?;
        Ok(())
    }

    fn unbounded(&self, sql: Bound<'py, PyAny>, label: &str) -> PyResult<Bound<'py, PyAny>> {
        let py = self.adapter.py();
        let resolved = self.resolve(
            sql,
            &[
                ("cursor_bounds", py.None().into_bound(py)),
                ("cursor_filter_inputs", PyDict::new(py).into_any()),
                ("cursor_type", py.None().into_bound(py)),
                (
                    "lower_bound_inclusive",
                    true.into_pyobject(py)?.to_owned().into_any(),
                ),
            ],
        )?;
        self.assert_resolved(&resolved, label)?;
        Ok(resolved)
    }

    fn hook(&self, value: Bound<'py, PyAny>, label: &str) -> PyResult<Bound<'py, PyAny>> {
        let py = value.py();
        if value.is_instance(&imported(py, HOOK_MODULE, "SqlHookEntry")?)? {
            let kwargs = PyDict::new(py);
            kwargs.set_item(
                "statement",
                self.unbounded(value.getattr("statement")?, label)?,
            )?;
            return imported(py, "dataclasses", "replace")?.call((value,), Some(&kwargs));
        }
        let is_list = value.is_instance_of::<PyList>();
        if is_list || value.is_instance_of::<PyTuple>() {
            let mut resolved: Vec<Bound<'py, PyAny>> = Vec::new();
            for (index, item) in value.try_iter()?.enumerate() {
                resolved.push(self.hook(item?, &format!("{label}[{index}]"))?);
            }
            return if is_list {
                Ok(PyList::new(py, resolved)?.into_any())
            } else {
                Ok(PyTuple::new(py, resolved)?.into_any())
            };
        }
        Ok(value)
    }
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn resolve_model_sql<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "resolve_model_sql",
        kwargs,
        (
            &[
                "adapter",
                "model",
                "snapshot",
                "context",
                "backfill",
                "full_refresh",
                "cursor_overrides",
            ],
            &[
                "external_sql_reference_resolver",
                "replaces_relation",
                "full_rebuild_cause",
            ],
        ),
    )?;
    let model = args.value("model")?;
    let resolution = Resolution {
        adapter: args.value("adapter")?,
        context: args.value("context")?,
        external: args.value("external_sql_reference_resolver")?,
    };
    let cursor_type = call_with(
        &imported(py, NATIVE_MODULE, "get_config_str")?,
        &[
            ("values", model.getattr("config")?.getattr("values")?),
            ("key", string(py, "cursor_type")),
        ],
    )?;
    let overrides = args.value("cursor_overrides")?;
    let bounds = call_with(
        &imported(py, NATIVE_MODULE, "compute_model_cursor_bounds")?,
        &[
            ("model", model.clone()),
            ("snapshot", args.value("snapshot")?),
            ("backfill", args.value("backfill")?),
            ("full_refresh", args.value("full_refresh")?),
            (
                "start_cursor_override",
                overrides.getattr("start_cursor_override")?,
            ),
            (
                "end_cursor_override",
                overrides.getattr("end_cursor_override")?,
            ),
            (
                "runtime_cursor_producer_names",
                resolution
                    .context
                    .getattr("runtime_cursor_producer_names")?,
            ),
            ("context", resolution.context.clone()),
            (
                "replaces_relation",
                args.value_or_false("replaces_relation")?,
            ),
        ],
    )?;
    let roles = call_with(
        &imported(py, NATIVE_MODULE, "resolve_cursor_input_roles")?,
        &[("model", model.clone())],
    )?;
    let inclusive =
        imported(py, CONFIG_MODULE, "get_config_append_cursor_inclusive")?.call1((&model,))?;
    let mut sql = resolution.resolve(
        model.getattr("query_sql")?,
        &[
            ("cursor_bounds", bounds.clone()),
            ("cursor_filter_inputs", roles.getattr("filter_inputs")?),
            ("cursor_type", cursor_type.clone()),
            ("lower_bound_inclusive", inclusive),
        ],
    )?;
    let intrinsics = call_with(
        &imported(py, NATIVE_MODULE, "resolve_cursor_intrinsics")?,
        &[("sql", sql.clone())],
    )?;
    let name: String = model.getattr("name")?.extract()?;
    if intrinsics.get_item(1)?.is_truthy()? {
        if bounds.is_none() {
            let cause = args.value("full_rebuild_cause")?;
            let cause = if cause.is_truthy()? {
                Some(cause.extract::<String>()?)
            } else if args.flag("full_refresh")? {
                Some("--full-refresh".to_owned())
            } else {
                None
            };
            return Err(unresolved_bounds_error(py, &name, cause.as_deref())?);
        }
        sql = call_with(
            &imported(py, INTRINSICS_MODULE, "render_cursor_intrinsic_bounds")?,
            &[
                ("sql", sql),
                ("bounds", bounds),
                ("cursor_type", cursor_type),
                ("adapter", resolution.adapter.clone()),
            ],
        )?;
    }
    resolution.assert_resolved(&sql, &format!("Model '{name}'"))?;
    Ok(sql)
}

fn unresolved_bounds_error(py: Python<'_>, name: &str, cause: Option<&str>) -> PyResult<PyErr> {
    let error = imported(py, ERROR_MODULE, "PlannerInputError")?;
    let kwargs = PyDict::new(py);
    let message = if let Some(cause) = cause {
        kwargs.set_item("help", "rebuild it with an explicit cursor interval (--start-cursor-ts and --end-cursor-ts, or the -int forms), or make it a microbatch model so a full rebuild can run batch by batch")?;
        format!(
            "Model '{name}' was given a FULL backfill ({cause}), but it uses cursor intrinsics and a non-microbatch full rebuild has no cursor interval"
        )
    } else {
        format!("Model '{name}' uses cursor intrinsics, but cursor bounds could not be resolved")
    };
    Ok(PyErr::from_value(error.call((message,), Some(&kwargs))?))
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn resolve_function_sql<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "resolve_function_sql",
        kwargs,
        (
            &[
                "adapter",
                "function",
                "model_locations",
                "seed_locations",
                "function_locations",
                "source_map",
                "source_warehouse_columns",
                "star_exclude_keyword",
            ],
            &[],
        ),
    )?;
    let mut context = vec![("models_by_name", PyDict::new(py).into_any())];
    for key in [
        "model_locations",
        "seed_locations",
        "function_locations",
        "source_map",
        "source_warehouse_columns",
        "star_exclude_keyword",
    ] {
        context.push((key, args.value(key)?));
    }
    let resolution = Resolution {
        adapter: args.value("adapter")?,
        context: call_with(&imported(py, MODELS_MODULE, "ModelPlanContext")?, &context)?,
        external: py.None().into_bound(py),
    };
    let function = args.value("function")?;
    let name: String = function.getattr("name")?.extract()?;
    resolution.unbounded(function.getattr("body_sql")?, &format!("Function '{name}'"))
}

#[pyfunction]
#[pyo3(signature = (*, model, adapter, context, external_sql_reference_resolver))]
fn resolve_model_hook_entries<'py>(
    model: &Bound<'py, PyAny>,
    adapter: Bound<'py, PyAny>,
    context: Bound<'py, PyAny>,
    external_sql_reference_resolver: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let resolution = Resolution {
        adapter,
        context,
        external: external_sql_reference_resolver,
    };
    let values = model.getattr("config")?.getattr("values")?;
    let name: String = model.getattr("name")?.extract()?;
    let mut hooks: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in ["pre_hooks", "post_hooks"] {
        hooks.push(resolution.hook(
            values.call_method1("get", (key,))?,
            &format!("Model '{name}' {key}"),
        )?);
    }
    PyTuple::new(model.py(), hooks)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_model_sql, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_function_sql, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_model_hook_entries, module)?)
}
