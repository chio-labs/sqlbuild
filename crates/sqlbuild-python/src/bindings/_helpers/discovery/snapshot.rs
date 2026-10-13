//! The Python directory snapshot one discovery pass shares, and the native tree it memoises.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple};
use sqlbuild_discovery::models::ProjectRoot;
use sqlbuild_discovery::tree::models::ProjectTree;
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Mutex;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};
use crate::bindings::_helpers::discovery::raised::discovery_error;
use crate::bindings::models::NativeProjectTree;

const SNAPSHOT_MODULE: &str = "sqlbuild.compiler.discovery.classes.directory_snapshot";
const SNAPSHOT_CLASS: &str = "DirectorySnapshot";
const DISCOVERY_TYPES_MODULE: &str = "sqlbuild.compiler.discovery.types";
const SNAPSHOT_ENTRY_CLASS: &str = "DirectorySnapshotEntry";
const TREE_MEMO_KEY: &str = "native_project_tree";
const DISPLAY_PROBE: &str = "_";
const PROJECT_PATH_KIND: &str = "project_path";
const SURROGATE_ESCAPE_BASE: u32 = 0xDC00;
const ESCAPED_BYTE_FIRST: u16 = 0xDC80;
const ESCAPED_BYTE_LAST: u16 = 0xDCFF;
const UTF16_ENCODING: &str = "utf-16-le";
const SURROGATE_PASS: &str = "surrogatepass";

/// Run `body` inside `DirectorySnapshot.scope(project_dir=project_dir)`.
pub(crate) fn in_snapshot<'py, T>(
    project_dir: &Bound<'py, PyAny>,
    body: impl FnOnce() -> PyResult<T>,
) -> PyResult<T> {
    let py: Python<'py> = project_dir.py();
    let scope: Bound<'py, PyAny> = call_with(
        &imported(py, SNAPSHOT_MODULE, SNAPSHOT_CLASS)?.getattr("scope")?,
        &[("project_dir", project_dir.clone())],
    )?;
    within(&scope, |_| body())
}

/// `DirectorySnapshot.current(project_dir=project_dir).memo`.
pub(crate) fn snapshot_memo<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    current_snapshot(project_dir)?
        .getattr("memo")?
        .downcast_into::<PyDict>()
        .map_err(Into::into)
}

fn current_snapshot<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(project_dir.py(), SNAPSHOT_MODULE, SNAPSHOT_CLASS)?.getattr("current")?,
        &[("project_dir", project_dir.clone())],
    )
}

/// `str(project_dir / "_")` without its probe: the text printed before a relative path.
pub(crate) fn display_prefix(project_dir: &Bound<'_, PyAny>) -> PyResult<String> {
    let probed: String = project_dir.div(DISPLAY_PROBE)?.str()?.to_str()?.to_owned();
    Ok(probed[..probed.len() - DISPLAY_PROBE.len()].to_owned())
}

/// The project root native discovery reads, named as Python prints it.
pub(crate) fn project_root(project_dir: &Bound<'_, PyAny>) -> PyResult<ProjectRoot> {
    Ok(ProjectRoot {
        directory: PathBuf::from(project_dir.str()?.to_str()?),
        display_prefix: display_prefix(project_dir)?,
    })
}

/// The native listings shared by every native call of the pass, created once per snapshot.
pub(crate) fn project_tree<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, NativeProjectTree>> {
    let py: Python<'py> = project_dir.py();
    let memo: Bound<'py, PyDict> = snapshot_memo(project_dir)?;
    if let Some(tree) = memo.get_item(TREE_MEMO_KEY)?
        && let Ok(tree) = tree.downcast_into::<NativeProjectTree>()
    {
        return Ok(tree);
    }
    let directory: Bound<'py, PyString> = project_dir.str()?;
    let prefixed: Bound<'py, PyString> = project_dir.div(DISPLAY_PROBE)?.str()?;
    for text in [&directory, &prefixed] {
        if text.to_str().is_err() {
            let mut shown: String = escaped(text)?;
            if text.is(&prefixed) {
                shown.truncate(shown.len() - DISPLAY_PROBE.len());
            }
            return Err(discovery_error(
                py,
                PROJECT_PATH_KIND,
                format!(
                    "Project directory {shown} is not valid UTF-8; move the project to a \
                     directory whose path is valid UTF-8"
                ),
                None,
            ));
        }
    }
    let created: Bound<'py, NativeProjectTree> = Bound::new(
        py,
        NativeProjectTree {
            inner: ProjectTree::new(std::path::Path::new(directory.to_str()?)),
            exported: Mutex::new(HashSet::new()),
        },
    )?;
    memo.set_item(TREE_MEMO_KEY, &created)?;
    Ok(created)
}

/// Share the native walk's new listings with the pass's Python directory snapshot.
pub(crate) fn seed_listings(
    project_dir: &Bound<'_, PyAny>,
    tree: &Bound<'_, NativeProjectTree>,
) -> PyResult<()> {
    let py: Python<'_> = project_dir.py();
    let entry_class: Bound<'_, PyAny> = imported(py, DISCOVERY_TYPES_MODULE, SNAPSHOT_ENTRY_CLASS)?;
    let listings: Bound<'_, PyDict> = PyDict::new(py);
    for (directory, entries) in tree.get().exported_listings(py)? {
        let entries: Vec<Bound<'_, PyAny>> = entries
            .into_iter()
            .map(|(name, is_dir, walkable)| entry_class.call1((name, is_dir, walkable)))
            .collect::<PyResult<_>>()?;
        listings.set_item(
            project_dir.div(directory.bind(py))?,
            PyTuple::new(py, entries)?,
        )?;
    }
    current_snapshot(project_dir)?.call_method1("seed_listings", (listings,))?;
    Ok(())
}

/// Python's `_escaped`: undecodable name bytes as `\xNN`, other lone surrogates as `\uXXXX`.
pub(crate) fn escaped(text: &Bound<'_, PyString>) -> PyResult<String> {
    let encoded: Vec<u8> = text
        .call_method1("encode", (UTF16_ENCODING, SURROGATE_PASS))?
        .extract()?;
    let units = encoded
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| u16::from_le_bytes(*pair));
    Ok(char::decode_utf16(units)
        .map(|decoded| match decoded {
            Ok(character) => character.to_string(),
            Err(error) => escaped_unit(error.unpaired_surrogate()),
        })
        .collect())
}

fn escaped_unit(unit: u16) -> String {
    if cfg!(unix) && (ESCAPED_BYTE_FIRST..=ESCAPED_BYTE_LAST).contains(&unit) {
        return format!("\\x{:02x}", u32::from(unit) - SURROGATE_ESCAPE_BASE);
    }
    format!("\\u{unit:04x}")
}
