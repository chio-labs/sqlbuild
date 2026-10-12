//! Static declaration visibility of scope targets and authored paths over a `ScopeLookup`.

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple, PyTupleMethods};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_scopes::scope_index::main::normalize_scope_path::normalize_scope_path;
use sqlbuild_scopes::scope_index::models::{
    OwnershipRoot, OwnershipRootKind, RejectedPath, ResourceIdentity, ResourceKind, ResourceRecord,
};

use crate::bindings::_helpers::scopes::scope_lookup::{
    NativeScopeLookup, ResolvedRows, TargetRows, path_message, scope_path_error,
};
use crate::bindings::_helpers::scopes::scope_objects::{
    ScopeClasses, qualified_row, read_resource, tuple_attribute,
};

type PyObject = Py<PyAny>;

const EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.scopes.exceptions";
const CURRENT_PATH: &str = ".";

fn native_lookup(lookup: &Bound<'_, PyAny>) -> PyResult<Py<NativeScopeLookup>> {
    lookup.getattr("native")?.extract()
}

/// Python's `query_target`: the resources or declarations `target` names.
fn target_query<'py>(
    classes: &ScopeClasses<'py>,
    lookup: &Bound<'py, PyAny>,
    target: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    let identity: bool = target.is_instance(&classes.model("ResourceIdentity")?)?
        || target.is_instance(&classes.model("DeclarationIdentity")?)?;
    let raw: String = if identity {
        String::new()
    } else {
        target.str()?.extract()?
    };
    let row = if identity {
        Some(qualified_row(target)?)
    } else {
        None
    };
    let (declarations, positions, identity_error, path_error): TargetRows =
        native_lookup(lookup)?.get().target(row, &raw)?;
    if let Some(message) = identity_error {
        return Err(PyErr::from_value(
            py.import(EXCEPTIONS_MODULE)?
                .getattr("InvalidQualifiedIdentityError")?
                .call1((message,))?,
        ));
    }
    if let Some(message) = path_error {
        return Err(scope_path_error(py, message)?);
    }
    let value: Bound<'py, PyAny> = if identity {
        target.clone()
    } else {
        raw.into_bound_py_any(py)?
    };
    let index: Bound<'py, PyAny> = lookup.getattr("index")?;
    let records: Bound<'py, PyTuple> = tuple_attribute(
        &index,
        if declarations {
            "declarations"
        } else {
            "resources"
        },
    )?;
    let matched: Vec<Bound<'py, PyAny>> = positions
        .iter()
        .map(|position| records.get_item(*position))
        .collect::<PyResult<_>>()?;
    let matched: Bound<'py, PyTuple> = PyTuple::new(py, matched)?;
    let keywords: Bound<'py, PyDict> = PyDict::new(py);
    keywords.set_item(
        if declarations {
            "declaration_matches"
        } else {
            "matches"
        },
        matched,
    )?;
    classes
        .model("ScopeTargetQuery")?
        .call((value,), Some(&keywords))
}

/// `query_target`: the `ScopeTargetQuery` of `target`; invalid text raises the scope error.
#[pyfunction]
fn scope_query_target(
    py: Python<'_>,
    lookup: &Bound<'_, PyAny>,
    target: &Bound<'_, PyAny>,
) -> PyResult<PyObject> {
    Ok(target_query(&ScopeClasses::new(py)?, lookup, target)?.unbind())
}

fn resolved(
    py: Python<'_>,
    lookup: &Bound<'_, PyAny>,
    resource: &ResourceRecord,
) -> PyResult<ResolvedRows> {
    let rows: ResolvedRows = native_lookup(lookup)?.get().resolve(py, resource)?;
    if let Some(message) = rows.2 {
        return Err(scope_path_error(py, message)?);
    }
    Ok(rows)
}

/// Every visible fact of each matched resource, and its inaccessible declarations.
#[pyfunction]
fn scope_resolve_visibility(
    py: Python<'_>,
    lookup: &Bound<'_, PyAny>,
    target: &Bound<'_, PyAny>,
    with_reasons: bool,
) -> PyResult<PyObject> {
    let classes: ScopeClasses<'_> = ScopeClasses::new(py)?;
    let query: Bound<'_, PyAny> = target_query(&classes, lookup, target)?;
    let index: Bound<'_, PyAny> = lookup.getattr("index")?;
    let identities: Bound<'_, PyTuple> =
        tuple_attribute(&lookup.getattr("visibility_index")?, "identities")?;
    let declarations: Bound<'_, PyTuple> = tuple_attribute(&index, "declarations")?;
    let grants: Bound<'_, PyTuple> = tuple_attribute(&index, "grants")?;
    let visible_class: Bound<'_, PyAny> = classes.model("VisibilityRecord")?;
    let inaccessible_class: Bound<'_, PyAny> = classes.model("InaccessibleRecord")?;
    let mut visible: Vec<Bound<'_, PyAny>> = Vec::new();
    let mut inaccessible: Vec<Bound<'_, PyAny>> = Vec::new();
    for resource in tuple_attribute(&query, "matches")?.iter() {
        let (resource_visible, resource_inaccessible, _) =
            resolved(py, lookup, &read_resource(&resource)?)?;
        let owner: Bound<'_, PyAny> = resource.getattr("identity")?;
        for (position, reason, grant) in resource_visible {
            let through: Option<Bound<'_, PyAny>> = grant
                .map(|grant| grants.get_item(grant)?.getattr("through"))
                .transpose()?;
            visible.push(visible_class.call1((
                &owner,
                identities.get_item(position)?,
                classes.member("VisibilityReason", reason)?,
                through,
            ))?);
        }
        for (position, reason) in resource_inaccessible {
            let identity: Bound<'_, PyAny> =
                declarations.get_item(position)?.getattr("identity")?;
            inaccessible.push(if with_reasons {
                inaccessible_class.call1((
                    &owner,
                    identity,
                    classes.member("InaccessibleReason", reason)?,
                ))?
            } else {
                identity
            });
        }
    }
    let result: &str = if with_reasons {
        "VisibilityResolution"
    } else {
        "DeclarationVisibility"
    };
    Ok(classes
        .model(result)?
        .call1((
            query,
            PyTuple::new(py, visible)?,
            PyTuple::new(py, inaccessible)?,
        ))?
        .unbind())
}

/// Visible and inaccessible declarations for an authored path, including declaration files.
#[pyfunction]
fn scope_resolve_path_visibility(
    py: Python<'_>,
    lookup: &Bound<'_, PyAny>,
    path: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyTuple>, Py<PyTuple>)> {
    let text: String = path.str()?.extract()?;
    let normalized: String = match normalize_scope_path(&text) {
        Ok(normalized) => normalized,
        Err(failure) => {
            let rejected: RejectedPath = RejectedPath {
                failure,
                path: text,
            };
            return Err(scope_path_error(py, path_message(&rejected))?);
        }
    };
    let resource: ResourceRecord = ResourceRecord {
        identity: ResourceIdentity {
            kind: ResourceKind::Model,
            name: format!("<path:{normalized}>"),
        },
        path: normalized,
        ownership_root: OwnershipRoot {
            path: CURRENT_PATH.to_owned(),
            kind: OwnershipRootKind::Resource,
            resource_kind: Some(ResourceKind::Model),
        },
    };
    let (visible, inaccessible, _) = resolved(py, lookup, &resource)?;
    let declarations: Bound<'_, PyTuple> =
        tuple_attribute(&lookup.getattr("index")?, "declarations")?;
    let pick = |positions: Vec<usize>| -> PyResult<Py<PyTuple>> {
        let records: Vec<Bound<'_, PyAny>> = positions
            .into_iter()
            .map(|position| declarations.get_item(position))
            .collect::<PyResult<_>>()?;
        Ok(PyTuple::new(py, records)?.unbind())
    };
    Ok((
        pick(
            visible
                .into_iter()
                .map(|(position, _, _)| position)
                .collect(),
        )?,
        pick(
            inaccessible
                .into_iter()
                .map(|(position, _)| position)
                .collect(),
        )?,
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_query_target, module)?)?;
    module.add_function(wrap_pyfunction!(scope_resolve_visibility, module)?)?;
    module.add_function(wrap_pyfunction!(scope_resolve_path_visibility, module)?)?;
    Ok(())
}
