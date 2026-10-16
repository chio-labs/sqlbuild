//! Source read deferral for managed source loaders.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::planner_phases::objects::{
    native, optional_text, planner_error, replace, text,
};
use crate::bindings::_helpers::planner_warehouse::constants::{
    MODEL_HOOK_CONFIG_KEYS, SQL_HOOK_ENTRY,
};
use crate::bindings::_helpers::records::ids::NativeAttr;
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::PyDict as KeywordDict;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use sqlbuild_analysis::planner_warehouse::main::source_call_names::source_call_names;
use sqlbuild_analysis::planner_warehouse::main::source_deferral_field::source_deferral_field;
use std::collections::BTreeSet;

fn managed_names(project: &Bound<'_, PyAny>) -> PyResult<BTreeSet<String>> {
    let mut names: BTreeSet<_> = BTreeSet::new();
    for source in project.getattr("sources")?.try_iter()? {
        let entry = source?.getattr("source_entry")?;
        if !entry.getattr("loader")?.is_none() {
            names.insert(entry.getattr("name")?.extract()?);
        }
    }
    Ok(names)
}

fn sql_source_reads(sql: &Bound<'_, PyAny>, managed: &BTreeSet<String>) -> PyResult<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    for name in source_call_names(&sql.extract::<String>()?) {
        if managed.contains(&name) {
            names.push(name);
        }
    }
    Ok(names)
}

fn hook_source_reads(
    model: &Bound<'_, PyAny>,
    managed: &BTreeSet<String>,
) -> PyResult<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    let py = model.py();
    let hook_entry = registry::class(py, SQL_HOOK_ENTRY)?;
    let source_kind = host::entry(py, UserCodeHost::SqlResourceRefKind)?.getattr("SOURCE")?;
    let values = model.getattr("config")?.getattr("values")?;
    for key in MODEL_HOOK_CONFIG_KEYS {
        let value = values.call_method1("get", (key,))?;
        let entries: Vec<Bound<'_, PyAny>> =
            if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
                value.try_iter()?.collect::<PyResult<_>>()?
            } else {
                vec![value]
            };
        for entry in entries {
            if !entry.is_instance(&hook_entry)? {
                continue;
            }
            for reference in entry.getattr("reads")?.try_iter()? {
                let reference = reference?;
                if reference.getattr("kind")?.is(&source_kind) {
                    let name: String = reference.getattr("name")?.extract()?;
                    if managed.contains(&name) {
                        names.push(name);
                    }
                }
            }
        }
    }
    Ok(names)
}

fn selected_managed_refs(
    project: &Bound<'_, PyAny>,
    selected: &Bound<'_, PyAny>,
    managed: &BTreeSet<String>,
) -> PyResult<BTreeSet<String>> {
    let mut names: BTreeSet<_> = BTreeSet::new();
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        if !selected.contains(model.getattr("key")?)? {
            continue;
        }
        names.extend(sql_source_reads(&model.getattr("query_sql")?, managed)?);
        names.extend(hook_source_reads(&model, managed)?);
    }
    for function in project.getattr("functions")?.try_iter()? {
        let function = function?;
        if selected.contains(function.getattr("key")?)? {
            names.extend(sql_source_reads(&function.getattr("body_sql")?, managed)?);
        }
    }
    for audit in project.getattr("audits")?.try_iter()? {
        let audit = audit?;
        let deps = audit.getattr("scope_deps")?;
        if deps.is_truthy()? {
            let mut any = false;
            for dep in deps.try_iter()? {
                if selected.contains(dep?)? {
                    any = true;
                    break;
                }
            }
            if !any {
                continue;
            }
        }
        for reference in audit.getattr("references")?.try_iter()? {
            let reference = reference?;
            let name: String = reference.getattr("ref_name")?.extract()?;
            if reference.getattr("ref_kind")?.eq("source")? && managed.contains(&name) {
                names.insert(name);
            }
        }
        names.extend(sql_source_reads(&audit.getattr("sql_body")?, managed)?);
    }
    Ok(names)
}

fn resolve_target<'py>(
    project_config: &Bound<'py, PyAny>,
    local_config: &Bound<'py, PyAny>,
    target_name: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    native(
        project_config.py(),
        NativeAttr::ResolveTargetConfig,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
            ("target_name", target_name),
        ],
    )
}

fn source_target_name<'py>(
    project: &Bound<'py, PyAny>,
    (project_config, local_config): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    defer_sources_to: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    if !defer_sources_to.is_none() {
        return Ok(defer_sources_to.clone());
    }
    let active = project.getattr("effective_target_name")?;
    if active.is_none() || project_config.is_none() || local_config.is_none() {
        return Ok(py.None().into_bound(py));
    }
    let deferred = resolve_target(project_config, local_config, active.clone())?
        .getattr("defer_sources_to")?;
    Ok(if deferred.is_truthy()? {
        deferred
    } else {
        active
    })
}

fn raw_source_entry<'py>(source: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let declared = source.getattr("source_entry")?;
    let name = declared.getattr("name")?;
    for entry in source
        .getattr("source_file")?
        .getattr("source_entries")?
        .try_iter()?
    {
        let entry = entry?;
        if entry.getattr("name")?.eq(&name)? {
            return Ok(entry);
        }
    }
    Ok(declared)
}

fn target_field<'py>(
    target_value: &Bound<'py, PyAny>,
    logical_value: &Bound<'py, PyAny>,
    effective_vars: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = target_value.py();
    let target: Option<String> = target_value.extract()?;
    let logical: Option<String> = logical_value.extract()?;
    let resolved = source_deferral_field(
        (target.as_deref(), logical.as_deref()),
        |name: &str| -> PyResult<Option<String>> {
            if !effective_vars.contains(name)? {
                return Ok(None);
            }
            Ok(Some(
                native(
                    py,
                    NativeAttr::RenderProjectVarText,
                    &[
                        ("value", effective_vars.get_item(name)?),
                        (
                            "label",
                            text(py, &format!("source deferral variable '${{{name}}}'")),
                        ),
                    ],
                )?
                .extract()?,
            ))
        },
    )?;
    Ok(optional_text(py, resolved.as_deref()))
}

fn entry_for_environment<'py>(
    entry: &Bound<'py, PyAny>,
    target: &Bound<'py, PyAny>,
    effective_vars: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if !entry.getattr("expression")?.is_none() {
        return Ok(entry.clone());
    }
    let mut database = entry.getattr("database")?;
    if database.is_none() {
        database = target_field(&target.getattr("database")?, &database, effective_vars)?;
    }
    let mut schema = entry.getattr("schema")?;
    if schema.is_none() {
        let loader_schema = target.getattr("loader_schema")?;
        let target_schema = if loader_schema.is_truthy()? {
            loader_schema
        } else {
            target.getattr("schema")?
        };
        schema = target_field(&target_schema, &schema, effective_vars)?;
    }
    replace(entry, &[("database", database), ("schema", schema)])
}

/// Resolve source reads for selected SQL, or for `read_source_names` when given.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_source_read_map<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<Bound<'py, PyDict>> {
    let args = KeywordArguments::read(
        py,
        "build_source_read_map",
        options,
        (
            &[
                "project",
                "source_map",
                "selected_keys",
                "project_config",
                "local_config",
                "defer_sources_to",
            ],
            &["read_source_names"],
        ),
    )?;
    let project = &args.value("project")?;
    let source_map = args.value("source_map")?.downcast_into::<PyDict>()?;
    let source_map = &source_map;
    let selected_keys = &args.value("selected_keys")?;
    let project_config = &args.value("project_config")?;
    let local_config = &args.value("local_config")?;
    let defer_sources_to = &args.value("defer_sources_to")?;
    let read_source_names = &args.value("read_source_names")?;

    let py = project.py();
    let managed = managed_names(project)?;
    let selected: BTreeSet<String> = match Some(read_source_names).filter(|names| !names.is_none())
    {
        Some(names) => names
            .try_iter()?
            .map(|name| name?.extract::<String>())
            .collect::<PyResult<BTreeSet<_>>>()?
            .intersection(&managed)
            .cloned()
            .collect(),
        None => selected_managed_refs(project, selected_keys, &managed)?,
    };
    if selected.is_empty() {
        return Ok(source_map.clone());
    }
    let target_name =
        source_target_name(project, (project_config, local_config), defer_sources_to)?;
    if target_name.is_none() || project_config.is_none() || local_config.is_none() {
        return Ok(source_map.clone());
    }
    if !project_config.getattr("targets")?.contains(&target_name)?
        && !local_config.getattr("targets")?.contains(&target_name)?
    {
        return Err(planner_error(
            py,
            &format!("Unknown source deferral target '{}'", target_name.str()?),
            (None, None),
        ));
    }
    let target = resolve_target(project_config, local_config, target_name)?;
    let effective_vars = project.getattr("effective_vars")?;
    let result = source_map.copy()?;
    for source in project.getattr("sources")?.try_iter()? {
        let source = source?;
        let name: String = source.getattr("source_entry")?.getattr("name")?.extract()?;
        if !selected.contains(&name) {
            continue;
        }
        let entry = raw_source_entry(&source)?;
        result.set_item(
            name,
            entry_for_environment(&entry, &target, &effective_vars)?,
        )?;
    }
    Ok(result)
}

/// Add declared project sources that no selected SQL resource reads to a source map.
#[pyfunction]
#[pyo3(signature = (*, project, source_map, source_names))]
pub(crate) fn with_declared_source_reads<'py>(
    project: &Bound<'py, PyAny>,
    source_map: &Bound<'py, PyDict>,
    source_names: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let mut missing: BTreeSet<_> = BTreeSet::new();
    for name in source_names.try_iter()? {
        let name: String = name?.extract()?;
        if !source_map.contains(&name)? {
            missing.insert(name);
        }
    }
    if missing.is_empty() {
        return Ok(source_map.clone());
    }
    let result = source_map.copy()?;
    for source in project.getattr("sources")?.try_iter()? {
        let entry = source?.getattr("source_entry")?;
        let name: String = entry.getattr("name")?.extract()?;
        if missing.contains(&name) {
            result.set_item(name, entry)?;
        }
    }
    Ok(result)
}
