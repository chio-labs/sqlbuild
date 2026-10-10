//! The project stat snapshot whole-project compile reuse compares, taken natively.

use std::path::PathBuf;

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_cache::project_snapshot::main::snapshot_project_files::snapshot_project_files;
use sqlbuild_cache::project_snapshot::models::{PathStamp, SnapshotRules};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

type StampRow = (String, &'static str, u64, i128, i128, u64, Option<String>);

/// The directories, suffixes and output files the walk treats specially.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct SnapshotRulesPy {
    excluded: Vec<String>,
    excluded_root: Vec<String>,
    presence_suffixes: Vec<String>,
    output_files: Vec<(u64, u64)>,
}

/// Every stamped path as `(relative, kind, size, mtime_ns, ctime_ns, inode, link)`, or `None`.
#[pyfunction]
fn snapshot_project_paths(
    py: Python<'_>,
    project_dir: PathBuf,
    rules: SnapshotRulesPy,
) -> PyResult<Option<Vec<StampRow>>> {
    compiler_guard(|| {
        let rules: SnapshotRules = SnapshotRules {
            excluded: rules.excluded,
            excluded_root: rules.excluded_root,
            presence_suffixes: rules.presence_suffixes,
            output_files: rules.output_files,
        };
        let stamps: Option<Vec<PathStamp>> =
            py.detach(|| snapshot_project_files(&project_dir, &rules));
        Ok(stamps.map(|stamps| stamps.into_iter().map(stamp_row).collect()))
    })
}

fn stamp_row(stamp: PathStamp) -> StampRow {
    (
        stamp.relative_path,
        stamp.kind,
        stamp.size,
        stamp.mtime_ns,
        stamp.ctime_ns,
        stamp.inode,
        stamp.link,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(snapshot_project_paths, module)?)
}
