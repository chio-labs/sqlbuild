//! The named declaration groups of a valid declaration layout, memoised per snapshot.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_discovery::declarations::main::declaration_layout::declaration_layout;
use sqlbuild_discovery::declarations::models::{DeclarationGroup, DeclarationLayout};
use sqlbuild_discovery::models::{DiscoveryFailure, StageFailure};

use crate::bindings::_helpers::discovery::project_files::path_object;
use crate::bindings::_helpers::discovery::raised::{discovery_error, stage_error};
use crate::bindings::_helpers::discovery::snapshot::{project_tree, seed_listings, snapshot_memo};
use crate::bindings::models::NativeProjectTree;

const GROUPS_MEMO_KEY: &str = "native_declaration_groups";

/// The rows to memoise: `(root, directory)` pairs, or the failure's `(kind, message, help)`.
fn memoised<'py>(
    py: Python<'py>,
    tree: &Bound<'py, NativeProjectTree>,
    groups: Result<Vec<DeclarationGroup>, DiscoveryFailure>,
) -> PyResult<Bound<'py, PyAny>> {
    match groups {
        Ok(groups) => {
            let rows: Vec<Bound<'py, PyTuple>> = groups
                .into_iter()
                .map(|group| {
                    PyTuple::new(
                        py,
                        [
                            path_object(py, &tree.get().inner, group.root)?,
                            path_object(py, &tree.get().inner, group.directory)?,
                        ],
                    )
                })
                .collect::<PyResult<_>>()?;
            Ok(PyList::new(py, rows)?.into_any())
        }
        Err(failure) => Ok(PyTuple::new(
            py,
            [
                failure.kind.as_str().into_bound_py_any(py)?,
                failure.message.into_bound_py_any(py)?,
                failure.help.into_bound_py_any(py)?,
            ],
        )?
        .into_any()),
    }
}

/// The `(canonical root, group directory)` pairs of a valid named declaration layout.
#[pyfunction]
#[pyo3(signature = (*, project_dir))]
pub(crate) fn declaration_groups<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let py: Python<'py> = project_dir.py();
    let memo: Bound<'py, PyDict> = snapshot_memo(project_dir)?;
    let groups: Bound<'py, PyAny> = match memo.get_item(GROUPS_MEMO_KEY)? {
        Some(groups) => groups,
        None => {
            let tree: Bound<'py, NativeProjectTree> = project_tree(project_dir)?;
            let layout: Result<DeclarationLayout, StageFailure> = {
                let inner = &tree.get().inner;
                py.detach(|| declaration_layout(inner, None))
            };
            let layout: DeclarationLayout =
                layout.map_err(|failure| stage_error(&tree.get().inner, project_dir, failure))?;
            seed_listings(project_dir, &tree)?;
            let groups: Bound<'py, PyAny> = memoised(py, &tree, layout.named_groups)?;
            memo.set_item(GROUPS_MEMO_KEY, &groups)?;
            groups
        }
    };
    if let Ok(rows) = groups.downcast::<PyList>() {
        return Ok(rows.clone());
    }
    let (kind, message, help): (String, String, Option<String>) = groups.extract()?;
    Err(discovery_error(py, &kind, message, help))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(declaration_groups, module)?)
}
