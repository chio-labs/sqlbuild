use crate::compiled_project::models::{AnalysisGate, AnalysisOverride, ModelLoopSettings};

/// Whether the model's SQL is analysed under the project switches and its override.
pub fn analysis_gate(
    settings: ModelLoopSettings,
    analysis_override: AnalysisOverride,
) -> AnalysisGate {
    crate::compiled_project::_helpers::plain::analysis_gate(settings, analysis_override)
}
