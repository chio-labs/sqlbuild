//! The Python host's slots beside the compiled project's records.

use std::fmt::{Debug, Formatter, Result as FmtResult};

use sqlbuild_project::types::ProjectHost;

use crate::bindings::_helpers::compiled_views::compiled_model_analysis::AnalysisProjections;
use crate::bindings::_helpers::compiled_views::compiled_model_view::CompiledProjections;
use crate::bindings::_helpers::compiled_views::model_input_view::{
    ModelInputHandles, SchemaHandles,
};

/// The extension's host: Python handles and the views built from them.
pub(crate) struct PyProjectHost;

impl ProjectHost for PyProjectHost {
    type ModelInput = ModelInputHandles;
    type Schema = SchemaHandles;
    type CompiledModel = CompiledProjections;
    type Analysis = AnalysisProjections;
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

impl Debug for CompiledProjections {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> FmtResult {
        formatter
            .debug_struct("CompiledProjections")
            .finish_non_exhaustive()
    }
}

impl Debug for AnalysisProjections {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> FmtResult {
        formatter
            .debug_struct("AnalysisProjections")
            .finish_non_exhaustive()
    }
}
