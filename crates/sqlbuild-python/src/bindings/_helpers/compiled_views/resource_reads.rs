//! A compiled resource's attributes read alike for models, functions, seeds and sources.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyResult, Python};

use crate::bindings::_helpers::compile_driver::stage_work::{COMPILED_VIEW_FALLBACKS, count_stage};
use crate::bindings::_helpers::compiled_views::compiled_model_view::NativeCompiledModel;
use crate::bindings::_helpers::compiled_views::function_views::NativeCompiledFunction;
use crate::bindings::_helpers::compiled_views::seed_views::NativeCompiledSeed;
use crate::bindings::_helpers::compiled_views::source_views::NativeCompiledSource;
use crate::bindings::_helpers::records::fields::field as native_field;

/// A resource's `deps` from whichever native view it is; any other object is read by attribute, counted.
pub(crate) fn deps<'py>(resource: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resource.py();
    if let Ok(view) = resource.cast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return view.deps(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledFunction>() {
        let view: &NativeCompiledFunction = view.get();
        return view.deps(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSeed>() {
        let view: &NativeCompiledSeed = view.get();
        return view.deps(py).into_bound_py_any(py);
    }
    if let Ok(view) = resource.cast::<NativeCompiledSource>() {
        let view: &NativeCompiledSource = view.get();
        return view.deps(py).into_bound_py_any(py);
    }
    count_stage(py, COMPILED_VIEW_FALLBACKS, 1)?;
    native_field(resource, "deps")
}

/// A resource's `destination` from whichever native view it is; any other object is read by attribute, counted.
pub(crate) fn destination<'py>(resource: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resource.py();
    if let Ok(view) = resource.cast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return view
            .destination(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledFunction>() {
        let view: &NativeCompiledFunction = view.get();
        return view
            .destination(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSeed>() {
        let view: &NativeCompiledSeed = view.get();
        return view
            .destination(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    count_stage(py, COMPILED_VIEW_FALLBACKS, 1)?;
    native_field(resource, "destination")
}

/// A resource's `key` from whichever native view it is; any other object is read by attribute, counted.
pub(crate) fn key<'py>(resource: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resource.py();
    if let Ok(view) = resource.cast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return view.key(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledFunction>() {
        let view: &NativeCompiledFunction = view.get();
        return view.key(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSeed>() {
        let view: &NativeCompiledSeed = view.get();
        return view.key(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSource>() {
        let view: &NativeCompiledSource = view.get();
        return view.key(py).and_then(|value| value.into_bound_py_any(py));
    }
    count_stage(py, COMPILED_VIEW_FALLBACKS, 1)?;
    native_field(resource, "key")
}

/// A resource's `name` from whichever native view it is; any other object is read by attribute, counted.
pub(crate) fn name<'py>(resource: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resource.py();
    if let Ok(view) = resource.cast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return view.name(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledFunction>() {
        let view: &NativeCompiledFunction = view.get();
        return view.name(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSeed>() {
        let view: &NativeCompiledSeed = view.get();
        return view.name(py).and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSource>() {
        let view: &NativeCompiledSource = view.get();
        return view.name(py).and_then(|value| value.into_bound_py_any(py));
    }
    count_stage(py, COMPILED_VIEW_FALLBACKS, 1)?;
    native_field(resource, "name")
}

/// A resource's `references` from whichever native view it is; any other object is read by attribute, counted.
pub(crate) fn references<'py>(resource: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resource.py();
    if let Ok(view) = resource.cast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return view
            .references(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledFunction>() {
        let view: &NativeCompiledFunction = view.get();
        return view
            .references(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    count_stage(py, COMPILED_VIEW_FALLBACKS, 1)?;
    native_field(resource, "references")
}

/// A resource's `schema_entry` from whichever native view it is; any other object is read by attribute, counted.
pub(crate) fn schema_entry<'py>(resource: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resource.py();
    if let Ok(view) = resource.cast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return view
            .schema_entry(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    if let Ok(view) = resource.cast::<NativeCompiledSeed>() {
        let view: &NativeCompiledSeed = view.get();
        return view
            .schema_entry(py)
            .and_then(|value| value.into_bound_py_any(py));
    }
    count_stage(py, COMPILED_VIEW_FALLBACKS, 1)?;
    native_field(resource, "schema_entry")
}
