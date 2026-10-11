//! The text of a deferred target's schema or database template, split around known variables.

use crate::templates::_helpers::deferred::{PLACEHOLDER_OPEN, placeholders, substitute_context};
use crate::templates::models::DeferredSegment;

/// `template` with deferred context keys replaced by `logical`, split at each known `${name}`.
pub fn deferred_target_segments(
    template: &str,
    logical: &str,
    context_keys: &[String],
    variables: &[String],
) -> Vec<DeferredSegment> {
    let text = substitute_context(template, context_keys, logical);
    let mut segments: Vec<DeferredSegment> = Vec::new();
    let mut copied = 0;
    for (start, end, name) in placeholders(&text, PLACEHOLDER_OPEN, Some(':')) {
        if variables.iter().any(|known| known == name) {
            segments.push(DeferredSegment::Text(text[copied..start].to_owned()));
            segments.push(DeferredSegment::Variable(name.to_owned()));
            copied = end;
        }
    }
    segments.push(DeferredSegment::Text(text[copied..].to_owned()));
    segments
}
