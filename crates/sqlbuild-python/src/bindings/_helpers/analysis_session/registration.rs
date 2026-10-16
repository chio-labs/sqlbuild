//! Register the native model analysis session functions.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

use crate::bindings::_helpers::analysis_session::{
    fixture_columns, fixture_inferences, oracle, outcome_objects, query_columns, session,
    stage_functions,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    session::register(module)?;
    fixture_columns::register(module)?;
    module.add_class::<fixture_inferences::FixtureColumnInferences>()?;
    outcome_objects::register(module)?;
    query_columns::register(module)?;
    stage_functions::register(module)?;
    oracle::register(module)
}
