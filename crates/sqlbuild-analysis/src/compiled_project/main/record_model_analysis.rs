use crate::compiled_project::models::{CompiledProjectFacts, ModelAnalysisFact};

/// Attach a recorded model's typed analysis result; `false` when the model was never recorded.
pub fn record_model_analysis(
    project: &mut CompiledProjectFacts,
    name: &str,
    analysis: ModelAnalysisFact,
) -> bool {
    project.record_analysis(name, analysis)
}
