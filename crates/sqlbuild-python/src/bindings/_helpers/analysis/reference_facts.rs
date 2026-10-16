//! The explicit-reference facts of a compiled project, read from its Python views.

use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyList, PyTuple};
use sqlbuild_analysis::explicit_references::models::{
    AuditGate, GraphResource, ModelReferences, NamedRelation, PythonHook, Relation, SourceRelation,
    SqlHook,
};
use sqlbuild_analysis::explicit_references::types::ResourceKey;

const MODEL_HOOK_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
const MIGRATE_FROM_KEY: &str = "migrate_from";
const OLD_NAME_VIEW_KEY: &str = "old_name_view";

/// The project facts the explicit-reference checks and execution-gate edges read.
pub(crate) struct ProjectFacts {
    /// Models, then sources, seeds and functions, with their dependencies.
    pub(crate) resources: Vec<GraphResource>,
    pub(crate) models: Vec<ModelReferences>,
    pub(crate) sources: Vec<SourceRelation>,
    pub(crate) seeds: Vec<NamedRelation>,
    pub(crate) audits: Vec<AuditGate>,
    pub(crate) hooks: Vec<PythonHook>,
}

/// The facts of `project`; `retains_old_names` is whether the project keeps old-name views.
pub(crate) fn project_facts(
    project: &Bound<'_, PyAny>,
    retains_old_names: bool,
) -> PyResult<ProjectFacts> {
    let py: Python<'_> = project.py();
    let entries: HookEntries<'_> = HookEntries::imported(py)?;
    let mut resources: Vec<GraphResource> = Vec::new();
    let mut models: Vec<ModelReferences> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'_, PyAny> = model?;
        resources.push(GraphResource {
            key: model.getattr("key_row")?.extract()?,
            deps: model.getattr("dep_rows")?.extract()?,
        });
        models.push(model_references(&model, &entries, retains_old_names)?);
    }
    let mut sources: Vec<SourceRelation> = Vec::new();
    for source in project.getattr("sources")?.try_iter()? {
        let source: Bound<'_, PyAny> = source?;
        resources.push(graph_resource(&source)?);
        let entry: Bound<'_, PyAny> = source.getattr("source_entry")?;
        sources.push(SourceRelation {
            name: source.getattr("name")?.extract()?,
            table: entry.getattr("table")?.extract()?,
            schema: entry.getattr("schema")?.extract()?,
            database: entry.getattr("database")?.extract()?,
            expression: !entry.getattr("expression")?.is_none(),
        });
    }
    let mut seeds: Vec<NamedRelation> = Vec::new();
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed: Bound<'_, PyAny> = seed?;
        resources.push(graph_resource(&seed)?);
        let destination: Bound<'_, PyAny> = seed.getattr("destination")?;
        seeds.push(NamedRelation {
            name: seed.getattr("name")?.extract()?,
            relation: Relation {
                name: destination.getattr("name")?.extract()?,
                schema: destination.getattr("schema")?.extract()?,
                database: destination.getattr("database")?.extract()?,
            },
        });
    }
    for function in project.getattr("functions")?.try_iter()? {
        resources.push(graph_resource(&function?)?);
    }
    let mut audits: Vec<AuditGate> = Vec::new();
    for audit in project.getattr("audits")?.try_iter()? {
        audits.push(audit_gate(&audit?)?);
    }
    let mut hooks: Vec<PythonHook> = Vec::new();
    for hook in project.getattr("hook_functions")?.try_iter()? {
        let hook: Bound<'_, PyAny> = hook?;
        hooks.push(PythonHook {
            name: hook.getattr("name")?.extract()?,
            path: hook
                .getattr("relative_path")?
                .call_method0("as_posix")?
                .extract()?,
            reads: ref_keys(&hook.getattr("reads")?)?,
        });
    }
    Ok(ProjectFacts {
        resources,
        models,
        sources,
        seeds,
        audits,
        hooks,
    })
}

/// `PythonHookEntry` and `SqlHookEntry`, which model hook entries are instances of.
struct HookEntries<'py> {
    python: Bound<'py, PyAny>,
    sql: Bound<'py, PyAny>,
}

impl<'py> HookEntries<'py> {
    fn imported(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            python: registry::class(py, RecordId::PythonHookEntry)?,
            sql: registry::class(py, RecordId::SqlHookEntry)?,
        })
    }
}

fn model_references(
    model: &Bound<'_, PyAny>,
    entries: &HookEntries<'_>,
    retains_old_names: bool,
) -> PyResult<ModelReferences> {
    let values: Bound<'_, PyAny> = model.getattr("config")?.getattr("values")?;
    let (database, schema, name): (Option<String>, Option<String>, String) =
        model.getattr("destination_row")?.extract()?;
    let mut sql_hooks: Vec<SqlHook> = Vec::new();
    for hook_key in MODEL_HOOK_KEYS {
        for (index, entry) in hook_items(&values.call_method1("get", (hook_key,))?)?
            .into_iter()
            .enumerate()
        {
            if !entry.is_instance(&entries.sql)? || !entry.getattr("reads")?.is_truthy()? {
                continue;
            }
            let path: Bound<'_, PyAny> = entry.getattr("relative_path")?;
            sql_hooks.push(SqlHook {
                hook_key: hook_key.to_owned(),
                index,
                name: entry.getattr("name")?.extract()?,
                path: if path.is_none() {
                    None
                } else {
                    Some(path.str()?.extract()?)
                },
                reads: ref_keys(&entry.getattr("reads")?)?,
            });
        }
    }
    Ok(ModelReferences {
        name: model.getattr("name")?.extract()?,
        path: model.getattr("relative_path")?.str()?.extract()?,
        destination: Relation {
            name,
            schema,
            database,
        },
        python_hooks: python_hook_names(&values, entries)?,
        sql_hooks,
        migrate_from: migrate_from(&values, retains_old_names)?,
    })
}

/// `model_python_hook_names`: the model's Python hooks in lifecycle order, each once.
fn python_hook_names(
    values: &Bound<'_, PyAny>,
    entries: &HookEntries<'_>,
) -> PyResult<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    for hook_key in MODEL_HOOK_KEYS {
        let value: Bound<'_, PyAny> = values.call_method1("get", (hook_key,))?;
        let items: Vec<Bound<'_, PyAny>> = if value.is_instance(&entries.python)? {
            vec![value]
        } else if is_sequence(&value) {
            value.try_iter()?.collect::<PyResult<_>>()?
        } else {
            Vec::new()
        };
        for item in items {
            if !item.is_instance(&entries.python)? {
                continue;
            }
            let name: String = item.getattr("name")?.extract()?;
            if !names.contains(&name) {
                names.push(name);
            }
        }
    }
    Ok(names)
}

/// The entries of one hook key: a list or tuple's items, or the value itself.
fn hook_items<'py>(value: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    if is_sequence(value) {
        return value.try_iter()?.collect();
    }
    Ok(vec![value.clone()])
}

fn is_sequence(value: &Bound<'_, PyAny>) -> bool {
    value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>()
}

/// The `migrate_from` string when the model keeps an old-name view, as Python resolves it.
fn migrate_from(values: &Bound<'_, PyAny>, retains_old_names: bool) -> PyResult<Option<String>> {
    let raw: Bound<'_, PyAny> = values.call_method1("get", (MIGRATE_FROM_KEY,))?;
    let Ok(text) = raw.extract::<String>() else {
        return Ok(None);
    };
    let retained: bool = if values.contains(OLD_NAME_VIEW_KEY)? {
        !values
            .get_item(OLD_NAME_VIEW_KEY)?
            .is(PyBool::new(values.py(), false))
    } else {
        retains_old_names
    };
    Ok(retained.then_some(text))
}

fn audit_gate(audit: &Bound<'_, PyAny>) -> PyResult<AuditGate> {
    let kind: Bound<'_, PyAny> = audit.getattr("attached_target_kind")?;
    let name: Bound<'_, PyAny> = audit.getattr("attached_target_name")?;
    let target: Option<ResourceKey> = if kind.is_none() || name.is_none() {
        None
    } else {
        Some((kind.str()?.extract()?, name.extract()?))
    };
    Ok(AuditGate {
        name: audit.getattr("name")?.extract()?,
        path: audit
            .getattr("audit_file")?
            .getattr("relative_path")?
            .str()?
            .extract()?,
        target,
        scope_deps: object_keys(&audit.getattr("scope_deps")?)?,
    })
}

fn graph_resource(resource: &Bound<'_, PyAny>) -> PyResult<GraphResource> {
    Ok(GraphResource {
        key: object_key(&resource.getattr("key")?)?,
        deps: object_keys(&resource.getattr("deps")?)?,
    })
}

/// A `CompiledObjectKey` as its `(resource type, name)` pair.
fn object_key(key: &Bound<'_, PyAny>) -> PyResult<ResourceKey> {
    Ok((
        key.getattr("resource_type")?.str()?.extract()?,
        key.getattr("name")?.extract()?,
    ))
}

fn object_keys(keys: &Bound<'_, PyAny>) -> PyResult<Vec<ResourceKey>> {
    keys.try_iter()?.map(|key| object_key(&key?)).collect()
}

/// `SqlResourceRef`s as `(kind, name)` pairs.
pub(crate) fn ref_keys(refs: &Bound<'_, PyAny>) -> PyResult<Vec<ResourceKey>> {
    refs.try_iter()?
        .map(|reference| {
            let reference: Bound<'_, PyAny> = reference?;
            Ok((
                reference.getattr("kind")?.str()?.extract()?,
                reference.getattr("name")?.extract()?,
            ))
        })
        .collect()
}
