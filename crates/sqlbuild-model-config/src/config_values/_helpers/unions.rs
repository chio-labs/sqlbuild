//! The unions `_merged_with_tag_union` makes of string sequences and row-diff tolerances.

use crate::config_values::_helpers::entries::{inserted, set_entry};
use crate::config_values::constants::AUDIT_OVERRIDE_SECTIONS;
use crate::config_values::models::ConfigNode;
use crate::types::{AuthoredNode, NodeKind};

/// `_as_string_list(value)`: `str()` of each list or tuple item.
fn string_items<H: Clone>(value: &ConfigNode<H>) -> Vec<String> {
    match value.kind() {
        NodeKind::List | NodeKind::Tuple => {
            value.items().iter().map(AuthoredNode::python_str).collect()
        }
        _ => Vec::new(),
    }
}

/// The strings of `base` then the new strings of `overlay`, as `_merge_string_sequence`.
pub(crate) fn merged_strings<H: Clone>(
    base: &ConfigNode<H>,
    overlay: &ConfigNode<H>,
) -> Vec<ConfigNode<H>> {
    let mut merged: Vec<String> = string_items(base);
    for item in string_items(overlay) {
        if !merged.contains(&item) {
            merged.push(item);
        }
    }
    merged.into_iter().map(ConfigNode::Str).collect()
}

/// Row-diff tolerances deep-merged by section, as `_merge_row_diff_tolerances_mapping`.
pub(crate) fn merged_tolerances<H: Clone>(
    base: &ConfigNode<H>,
    overlay: &ConfigNode<H>,
) -> ConfigNode<H> {
    if base.kind() != NodeKind::Map || overlay.kind() != NodeKind::Map {
        return overlay.clone();
    }
    let (base, overlay) = (base.entries(), overlay.entries());
    let mut merged = base.clone();
    for section in AUDIT_OVERRIDE_SECTIONS {
        let Some(overlay_section) = set_entry(&overlay, section) else {
            continue;
        };
        let value: ConfigNode<H> = match set_entry(&base, section) {
            Some(base_section)
                if base_section.kind() == NodeKind::Map
                    && overlay_section.kind() == NodeKind::Map =>
            {
                let mut values = base_section.entries();
                for (key, item) in overlay_section.entries() {
                    values = inserted(values, key, item);
                }
                ConfigNode::Map(values)
            }
            _ => overlay_section.clone(),
        };
        merged = inserted(merged, ConfigNode::Str(section.to_owned()), value);
    }
    for (key, item) in &overlay {
        if key.kind() == NodeKind::Str
            && !AUDIT_OVERRIDE_SECTIONS
                .iter()
                .any(|section| key.is_text(section))
        {
            merged = inserted(merged, key.clone(), item.clone());
        }
    }
    ConfigNode::Map(merged)
}
