use crate::models::PolicyConfig;
use crate::rules::models::ResolvedThresholdOverride;

pub(crate) fn resolve_threshold_overrides(
    config: &PolicyConfig,
) -> Result<Vec<ResolvedThresholdOverride>, String> {
    crate::rules::_helpers::evaluation::resolve_threshold_overrides(config)
}
