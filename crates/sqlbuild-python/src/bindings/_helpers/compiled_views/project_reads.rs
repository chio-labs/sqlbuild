//! A compiled project's resource collections, read from its native view.

use pyo3::prelude::{Bound, PyAny, PyResult, Python};

use crate::bindings::_helpers::compile_driver::stage_work::{COMPILED_VIEW_FALLBACKS, count_stage};
use crate::bindings::_helpers::compiled_views::project_view::NativeProjectView;
use crate::bindings::_helpers::records::fields::field as native_field;

/// The native view behind a project object; any other object is a Python-built record, counted.
#[inline]
fn native_project<'a>(project: &'a Bound<'_, PyAny>) -> PyResult<Option<&'a NativeProjectView>> {
    if let Ok(view) = project.cast::<NativeProjectView>() {
        return Ok(Some(view.get()));
    }
    count_stage(project.py(), COMPILED_VIEW_FALLBACKS, 1)?;
    Ok(None)
}

/// The project's compiled models, in compile order.
pub(crate) fn models<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    if let Some(view) = native_project(project)? {
        return Ok(view.models(py).into_bound(py).into_any());
    }
    native_field(project, "models")
}

/// The project's compiled sources.
pub(crate) fn sources<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    if let Some(view) = native_project(project)? {
        return Ok(view.sources(py).into_bound(py));
    }
    native_field(project, "sources")
}

/// The project's compiled functions.
pub(crate) fn functions<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    if let Some(view) = native_project(project)? {
        return Ok(view.functions(py).into_bound(py));
    }
    native_field(project, "functions")
}

/// The project's compiled seeds.
pub(crate) fn seeds<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    if let Some(view) = native_project(project)? {
        return Ok(view.seeds(py).into_bound(py));
    }
    native_field(project, "seeds")
}

/// The project's compiled audits.
pub(crate) fn audits<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    if let Some(view) = native_project(project)? {
        return Ok(view.audits(py).into_bound(py));
    }
    native_field(project, "audits")
}
