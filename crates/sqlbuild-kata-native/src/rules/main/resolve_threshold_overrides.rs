use crate::models::KataConfig;
use crate::rules::models::ResolvedThresholdOverride;

pub(crate) fn resolve_threshold_overrides(
    config: &KataConfig,
) -> Result<Vec<ResolvedThresholdOverride>, String> {
    crate::rules::_helpers::evaluation::resolve_threshold_overrides(config)
}
