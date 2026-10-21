//! The Python host's slots beside the compiled project's records.

use std::fmt::{Debug, Formatter, Result as FmtResult};

use sqlbuild_project::types::ProjectHost;

use crate::bindings::_helpers::compiled_views::compiled_model_view::CompiledRecord;
use crate::bindings::_helpers::compiled_views::model_input_view::{
    ModelInputHandles, SchemaHandles,
};

/// The extension's host: Python handles and the views built from them.
pub(crate) struct PyProjectHost;

impl ProjectHost for PyProjectHost {
    type ModelInput = ModelInputHandles;
    type Schema = SchemaHandles;
    type CompiledModel = CompiledRecord;
}

impl Debug for ModelInputHandles {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> FmtResult {
        formatter
            .debug_struct("ModelInputHandles")
            .finish_non_exhaustive()
    }
}

impl Debug for SchemaHandles {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> FmtResult {
        formatter
            .debug_struct("SchemaHandles")
            .finish_non_exhaustive()
    }
}

impl Debug for CompiledRecord {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> FmtResult {
        formatter
            .debug_struct("CompiledRecord")
            .finish_non_exhaustive()
    }
}
