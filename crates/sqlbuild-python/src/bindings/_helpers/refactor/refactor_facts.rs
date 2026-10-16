//! Refactoring facts read from a compiled project, and the shared scope placement host.

use std::collections::HashMap;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use sqlbuild_refactor::refactoring::models::{
    AuthoredFile, DeclarationPlacement, DependencyFacts, DestinationFacts, DiscoveredFile,
    ExpansionFacts, ExpansionSpan, LocationFacts, ManualLocation, ModelFacts, PlacedDeclaration,
    RefactorFacts, RefactorOperation, RefactorRequest, RelocatedDeclaration, ResourceColumnsFacts,
    SchemaColumnFacts, SqlFileRole,
};

use crate::bindings::_helpers::scopes::scope_lookup::build_scope_lookup;
use crate::bindings::_helpers::scopes::scope_reports::scope_move_preview;
use crate::bindings::_helpers::scopes::scope_validation::scope_relocated_declarations;

const NATIVE_MODULE: &str = "sqlbuild._native";
const CONFIG_MODULE: &str = "sqlbuild._native";
const SCOPE_MODELS: &str = "sqlbuild._native";
const SCOPE_TYPES: &str = "sqlbuild._native";
const GENERIC_DIALECT: &str = "generic";
const MATERIALIZED_KEY: &str = "materialized";
const MIGRATE_FROM_KEY: &str = "migrate_from";
const MODEL_KIND_PREFIX: &str = "model:";

fn posix(path: &Bound<'_, PyAny>) -> PyResult<String> {
    path.call_method0("as_posix")?.extract()
}

fn native<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import(NATIVE_MODULE)?.getattr(name)
}

fn discovered_files(files: &Bound<'_, PyAny>) -> PyResult<Vec<DiscoveredFile>> {
    let mut discovered: Vec<DiscoveredFile> = Vec::new();
    for item in files.try_iter()? {
        let item: Bound<'_, PyAny> = item?;
        discovered.push(DiscoveredFile {
            path: posix(&item.getattr("relative_path")?)?,
            contents: item.getattr("contents")?.extract()?,
        });
    }
    Ok(discovered)
}

fn column_names(columns: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    columns
        .try_iter()?
        .map(|column| column?.getattr("name")?.extract())
        .collect()
}

fn resource_columns(
    resources: &Bound<'_, PyAny>,
    entry: &str,
) -> PyResult<Vec<ResourceColumnsFacts>> {
    let mut facts: Vec<ResourceColumnsFacts> = Vec::new();
    for resource in resources.try_iter()? {
        let resource: Bound<'_, PyAny> = resource?;
        facts.push(ResourceColumnsFacts {
            name: resource.getattr("name")?.extract()?,
            columns: column_names(&resource.getattr(entry)?.getattr("columns")?)?,
        });
    }
    Ok(facts)
}

fn spans(spans: &Bound<'_, PyAny>) -> PyResult<Vec<ExpansionSpan>> {
    let mut read: Vec<ExpansionSpan> = Vec::new();
    for span in spans.try_iter()? {
        let span: Bound<'_, PyAny> = span?;
        read.push(ExpansionSpan {
            source_start: span.getattr("source_start")?.extract()?,
            source_end: span.getattr("source_end")?.extract()?,
            output_start: span.getattr("output_start")?.extract()?,
            output_end: span.getattr("output_end")?.extract()?,
        });
    }
    Ok(read)
}

fn expansion_facts(expansion: &Bound<'_, PyAny>) -> PyResult<ExpansionFacts> {
    Ok(ExpansionFacts {
        expanded_sql: expansion.getattr("expanded_sql")?.extract()?,
        passes: expansion
            .getattr("passes")?
            .try_iter()?
            .map(|pass| spans(&pass?))
            .collect::<PyResult<_>>()?,
    })
}

fn schema_columns(entry: &Bound<'_, PyAny>) -> PyResult<Option<Vec<SchemaColumnFacts>>> {
    if entry.is_none() {
        return Ok(None);
    }
    let mut columns: Vec<SchemaColumnFacts> = Vec::new();
    for column in entry.getattr("columns")?.try_iter()? {
        let column: Bound<'_, PyAny> = column?;
        let location: Bound<'_, PyAny> = column.getattr("location")?;
        columns.push(SchemaColumnFacts {
            name: column.getattr("name")?.extract()?,
            migrate_from: !column.getattr("migrate_from")?.is_none(),
            location: if location.is_none() {
                None
            } else {
                Some(LocationFacts {
                    path: posix(&location.getattr("path")?)?,
                    line: location.getattr("line")?.extract()?,
                    column: location.getattr("column")?.extract()?,
                })
            },
        });
    }
    Ok(Some(columns))
}

fn model(model: &Bound<'_, PyAny>, expansion: Option<&Bound<'_, PyAny>>) -> PyResult<ModelFacts> {
    let py: Python<'_> = model.py();
    let values: Bound<'_, PyDict> = PyDict::new(py);
    values.call_method1("update", (model.getattr("config")?.getattr("values")?,))?;
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("values", &values)?;
    options.set_item("key", MATERIALIZED_KEY)?;
    let materialized: Option<String> = py
        .import(CONFIG_MODULE)?
        .getattr("get_config_str")?
        .call((), Some(&options))?
        .extract()?;
    let migrate_from: Option<Bound<'_, PyAny>> = values.get_item(MIGRATE_FROM_KEY)?;
    let mut deps: Vec<DependencyFacts> = Vec::new();
    for dep in model.getattr("deps")?.try_iter()? {
        let dep: Bound<'_, PyAny> = dep?;
        deps.push(DependencyFacts {
            resource_type: dep.getattr("resource_type")?.str()?.extract()?,
            name: dep.getattr("name")?.extract()?,
        });
    }
    let destination: Bound<'_, PyAny> = model.getattr("destination")?;
    let inferred: Bound<'_, PyAny> = model.getattr("inferred_columns")?;
    Ok(ModelFacts {
        name: model.getattr("name")?.extract()?,
        path: posix(&model.getattr("relative_path")?)?,
        deps,
        query_sql: model.getattr("query_sql")?.extract()?,
        authored_query_sql: model.getattr("authored_query_sql")?.extract()?,
        materialized,
        declares_migrate_from: migrate_from.is_some(),
        migrate_from_set: migrate_from.is_some_and(|value| !value.is_none()),
        destination: DestinationFacts {
            database: destination.getattr("database")?.extract()?,
            schema: destination.getattr("schema")?.extract()?,
            name: destination.getattr("name")?.extract()?,
        },
        inferred_columns: if inferred.is_none() {
            Vec::new()
        } else {
            column_names(&inferred)?
        },
        schema_columns: schema_columns(&model.getattr("schema_entry")?)?,
        expansion: expansion.map(expansion_facts).transpose()?,
    })
}

/// Every compiled model's refactoring facts, or none without a project.
pub(crate) fn model_facts(
    refactor_project: &Bound<'_, PyAny>,
) -> PyResult<Option<Vec<ModelFacts>>> {
    if refactor_project.is_none() {
        return Ok(None);
    }
    let project: Bound<'_, PyAny> = refactor_project.getattr("graph")?.getattr("project")?;
    let project_dir: Bound<'_, PyAny> = refactor_project.getattr("project_dir")?;
    let mut expansions: HashMap<String, Bound<'_, PyAny>> = HashMap::new();
    let items: Vec<Bound<'_, PyAny>> = project
        .getattr("sql_expansions")?
        .call_method0("items")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    for item in items.iter().rev() {
        let (path, expansion): (Bound<'_, PyAny>, Bound<'_, PyAny>) = item.extract()?;
        expansions.insert(path.call_method0("resolve")?.str()?.extract()?, expansion);
    }
    let mut facts: Vec<ModelFacts> = Vec::new();
    for compiled in project.getattr("models")?.try_iter()? {
        let compiled: Bound<'_, PyAny> = compiled?;
        let resolved: String = project_dir
            .div(compiled.getattr("relative_path")?)?
            .call_method0("resolve")?
            .str()?
            .extract()?;
        facts.push(model(&compiled, expansions.get(&resolved))?);
    }
    Ok(Some(facts))
}

fn block_bodies(blocks: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    blocks
        .try_iter()?
        .map(|block| block?.getattr("sql_body")?.extract())
        .collect()
}

fn authored_files(discovered: &Bound<'_, PyAny>) -> PyResult<Vec<AuthoredFile>> {
    let groups: [(SqlFileRole, &str, Option<&str>, bool); 6] = [
        (SqlFileRole::Test, "test_files", None, true),
        (
            SqlFileRole::Scenario,
            "scenario_files",
            Some("sql_body"),
            false,
        ),
        (SqlFileRole::Audit, "audit_files", None, true),
        (SqlFileRole::Hook, "sql_hook_files", Some("sql_body"), false),
        (
            SqlFileRole::Function,
            "sql_function_files",
            Some("body_sql"),
            false,
        ),
        (SqlFileRole::Schema, "model_schema_files", None, false),
    ];
    let mut files: Vec<AuthoredFile> = Vec::new();
    for (role, attribute, body, blocks) in groups {
        for item in discovered.getattr(attribute)?.try_iter()? {
            let item: Bound<'_, PyAny> = item?;
            let texts: Vec<String> = match (body, blocks) {
                (Some(body), _) => vec![item.getattr(body)?.extract()?],
                (None, true) => block_bodies(&item.getattr("blocks")?)?,
                (None, false) => Vec::new(),
            };
            files.push(AuthoredFile {
                role,
                path: posix(&item.getattr("relative_path")?)?,
                contents: item.getattr("contents")?.extract()?,
                texts,
            });
        }
    }
    Ok(files)
}

fn python_locations(
    project: &Bound<'_, PyAny>,
    request: &RefactorRequest,
) -> PyResult<Vec<ManualLocation>> {
    let py: Python<'_> = project.py();
    let old: &str = &request.model_name;
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("project_dir", project.getattr("project_dir")?)?;
    options.set_item("discovered", project.getattr("discovered")?)?;
    if request.operation == RefactorOperation::RenameColumn {
        let column: &str = request.column_name.as_deref().unwrap_or_default();
        options.set_item("names", PyTuple::new(py, [column])?)?;
        options.set_item(
            "reason",
            format!("Python SQL may read column {column} of {old}; check it by hand"),
        )?;
        options.set_item("context", old)?;
    } else {
        options.set_item("names", PyTuple::new(py, [old])?)?;
        options.set_item(
            "reason",
            format!("Python code names model {old}; update it by hand"),
        )?;
    }
    let mut locations: Vec<ManualLocation> = Vec::new();
    for location in native(py, "find_python_string_locations")?
        .call((), Some(&options))?
        .try_iter()?
    {
        let location: Bound<'_, PyAny> = location?;
        locations.push(ManualLocation {
            path: location.getattr("path")?.extract()?,
            line: location.getattr("line")?.extract()?,
            column: location.getattr("column")?.extract()?,
            reason: location.getattr("reason")?.extract()?,
        });
    }
    Ok(locations)
}

/// The facts one refactoring plan reads.
pub(crate) fn refactor_facts(
    project: &Bound<'_, PyAny>,
    request: &RefactorRequest,
) -> PyResult<RefactorFacts> {
    let compiled: Bound<'_, PyAny> = project.getattr("graph")?.getattr("project")?;
    let discovered: Bound<'_, PyAny> = project.getattr("discovered")?;
    let dialect: Option<String> = compiled.getattr("sql_analysis_dialect")?.extract()?;
    let mut yaml_files: Vec<DiscoveredFile> =
        discovered_files(&discovered.getattr("source_files")?)?;
    yaml_files.extend(discovered_files(&discovered.getattr("schema_files")?)?);
    Ok(RefactorFacts {
        project_dir: project.getattr("project_dir")?.str()?.extract()?,
        dialect: dialect
            .filter(|dialect| !dialect.is_empty())
            .unwrap_or_else(|| GENERIC_DIALECT.to_owned()),
        models: model_facts(project)?.unwrap_or_default(),
        sources: resource_columns(&compiled.getattr("sources")?, "source_entry")?,
        seeds: resource_columns(&compiled.getattr("seeds")?, "schema_entry")?,
        model_files: discovered_files(&discovered.getattr("model_files")?)?,
        authored_files: authored_files(&discovered)?,
        yaml_files,
        python_locations: python_locations(project, request)?,
    })
}

fn identity_key(identity: &Bound<'_, PyAny>) -> PyResult<String> {
    identity.repr()?.extract()
}

/// Where the shared scope placement puts declarations when `model` moves to `destination`.
pub(crate) fn declaration_placement(
    project: &Bound<'_, PyAny>,
    (model, destination): (&str, &str),
) -> PyResult<DeclarationPlacement> {
    let py: Python<'_> = project.py();
    let index: Bound<'_, PyAny> = project
        .getattr("graph")?
        .getattr("project")?
        .getattr("scope_index")?;
    let lookup: Bound<'_, PyAny> = build_scope_lookup(py, &index)?.into_bound(py);
    let (preview, diagnostics) = scope_move_preview(
        py,
        &lookup,
        &PyString::new(py, &format!("{MODEL_KIND_PREFIX}{model}")).into_any(),
        &PyString::new(py, destination).into_any(),
    )?;
    let diagnostics: Bound<'_, PyAny> = diagnostics.into_bound(py);
    let relocated: Option<Vec<RelocatedDeclaration>> = if preview.is_none() {
        None
    } else {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item(
            "kind",
            py.import(SCOPE_TYPES)?
                .getattr("ResourceKind")?
                .getattr("MODEL")?,
        )?;
        options.set_item("name", model)?;
        let resource: Bound<'_, PyAny> = py
            .import(SCOPE_MODELS)?
            .getattr("ResourceIdentity")?
            .call((), Some(&options))?;
        let records: Option<Py<PyTuple>> =
            scope_relocated_declarations(py, &index, &resource, destination)?;
        if let Some(records) = records {
            let records: Bound<'_, PyAny> = records.into_bound(py).into_any();
            let sort: Bound<'_, PyDict> = PyDict::new(py);
            sort.set_item(
                "key",
                py.import("operator")?
                    .getattr("attrgetter")?
                    .call1(("identity",))?,
            )?;
            let mut relocated: Vec<RelocatedDeclaration> = Vec::new();
            for record in py
                .import("builtins")?
                .getattr("sorted")?
                .call((records,), Some(&sort))?
                .try_iter()?
            {
                let record: Bound<'_, PyAny> = record?;
                relocated.push(RelocatedDeclaration {
                    key: identity_key(&record.getattr("identity")?)?,
                    path: record.getattr("path")?.extract()?,
                });
            }
            Some(relocated)
        } else {
            None
        }
    };
    let mut declarations: Vec<PlacedDeclaration> = Vec::new();
    for record in index.getattr("declarations")?.try_iter()? {
        let record: Bound<'_, PyAny> = record?;
        let identity: Bound<'_, PyAny> = record.getattr("identity")?;
        let kind: String = identity.getattr("kind")?.getattr("value")?.extract()?;
        let name: String = identity.getattr("name")?.extract()?;
        declarations.push(PlacedDeclaration {
            key: identity_key(&identity)?,
            label: format!("{kind}:{name}"),
            path: record.getattr("path")?.extract()?,
            line: record.getattr("line")?.extract()?,
            column: record.getattr("column")?.extract()?,
        });
    }
    Ok(DeclarationPlacement {
        relocated,
        diagnostics: diagnostics
            .try_iter()?
            .map(|item| item?.getattr("message")?.extract())
            .collect::<PyResult<_>>()?,
        declarations,
    })
}
