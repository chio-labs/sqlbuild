//! Register the native model analysis session functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::analysis_session::{
    model_analyses, oracle, outcome_objects, query_columns, session, stage_functions,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    session::register(module)?;
    model_analyses::register(module)?;
    outcome_objects::register(module)?;
    query_columns::register(module)?;
    stage_functions::register(module)?;
    oracle::register(module)
}
