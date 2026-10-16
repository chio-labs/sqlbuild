//! Diagnose literal references to compatibility-only old names.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::planner_migrations::column_objects::{native, text};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyStringMethods, PyTuple};

fn old_relation<'py>(
    old: &Bound<'py, PyAny>,
    name: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = old.py();
    let reference = call_with(
        &host::entry(py, UserCodeHost::SqlResourceRef)?,
        &[
            (
                "kind",
                host::entry(py, UserCodeHost::SqlResourceRefKind)?.getattr("MODEL")?,
            ),
            ("name", name.clone()),
        ],
    )?;
    let relation = call_with(
        &imported(py, "sqlbuild.compiler.references.models", "RelationName")?,
        &[
            ("name", old.getattr("name")?),
            ("schema", old.getattr("schema")?),
            ("database", old.getattr("database")?),
        ],
    )?;
    call_with(
        &imported(py, "sqlbuild.compiler.references.models", "ProjectRelation")?,
        &[
            ("ref", reference),
            ("relation", relation),
            ("compatibility_for", name),
        ],
    )
}

pub(super) fn errors<'py>(
    runtime: &Bound<'py, PyAny>,
    views: &Bound<'py, PyAny>,
    entries: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = runtime.py();
    let literals = runtime
        .getattr("project")?
        .getattr("unmatched_literal_sql_relations")?;
    if !literals.is_truthy()? {
        return Ok(Vec::new());
    }
    let relations = PyDict::new(py);
    for view in views.try_iter()? {
        let view = view?;
        relations.set_item(
            old_relation(&view.getattr("old")?, view.getattr("destination_model")?)?,
            py.None(),
        )?;
    }
    for entry in entries.try_iter()? {
        let entry = entry?;
        if entry.getattr("runs_steps")?.is_truthy()? {
            relations.set_item(
                old_relation(&entry.getattr("origin")?, entry.getattr("model_name")?)?,
                py.None(),
            )?;
        }
    }
    let index = call_with(
        &imported(
            py,
            "sqlbuild.compiler.references.models",
            "ProjectRelationIndex",
        )?,
        &[("relations", PyTuple::new(py, relations.keys())?.into_any())],
    )?;
    let mut errors: Vec<Bound<'py, PyAny>> = Vec::new();
    for literal in literals.try_iter()? {
        let literal = literal?;
        let relation = literal.getattr("relation")?;
        let matched = native(
            py,
            NativeAttr::MatchProjectRelation,
            &[("index", index.clone()), ("relation", relation.clone())],
        )?;
        if matched.is_none() || matched.getattr("compatibility_for")?.is_none() {
            continue;
        }
        let mut parts: Vec<String> = Vec::new();
        for field in ["database", "schema", "name"] {
            let part = relation.getattr(field)?;
            if part.is_truthy()? {
                parts.push(part.extract()?);
            }
        }
        let message: String = native(
            py,
            NativeAttr::OldNameReferenceMessage,
            &[
                ("owner_label", literal.getattr("owner_label")?),
                ("written", text(py, &parts.join("."))),
                ("method", literal.getattr("method")?),
                ("model_name", matched.getattr("compatibility_for")?),
            ],
        )?
        .extract()?;
        let remedy: String = native(
            py,
            NativeAttr::HardCodedRelationRemedy,
            &[
                ("owner_kind", literal.getattr("owner_kind")?),
                ("ref", matched.getattr("ref")?),
            ],
        )?
        .extract()?;
        let path = literal
            .getattr("relative_path")?
            .str()?
            .to_str()?
            .to_owned();
        let line = literal.getattr("line")?.str()?.to_str()?.to_owned();
        errors.push(native(
            py,
            RecordId::PlanWarning,
            &[
                ("model_name", py.None().into_bound(py)),
                (
                    "severity",
                    registry::class(py, RecordId::WarningSeverity)?.getattr("ERROR")?,
                ),
                (
                    "message",
                    text(py, &format!("{path}:{line}: {message}; {remedy}")),
                ),
                ("code", text(py, "P008")),
            ],
        )?);
    }
    Ok(errors)
}
