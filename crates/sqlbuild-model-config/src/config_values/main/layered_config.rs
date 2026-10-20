//! One config layer merged over another, as `_merged_with_tag_union` merges them.

use crate::config_values::_helpers::entries::{inserted, set_entry};
use crate::config_values::_helpers::unions::{merged_strings, merged_tolerances};
use crate::config_values::constants::{
    ROW_DIFF_EXCLUDE_COLUMNS_KEY, ROW_DIFF_TOLERANCES_KEY, TAGS_KEY,
};
use crate::config_values::models::{ConfigNode, LayeredConfig};
use crate::config_values::types::{HostObject, ItemText};
use crate::types::{AuthoredNode, NodeKind};

/// `overlay` over a copy of `base`, unioning tags, row-diff exclusions and tolerances; `text` prints non-scalar items.
pub fn layered_config<H: HostObject, E>(
    base: &[(ConfigNode<H>, ConfigNode<H>)],
    overlay: &[(ConfigNode<H>, ConfigNode<H>)],
    text: ItemText<'_, H, E>,
) -> Result<LayeredConfig<H>, E> {
    let mut entries = base.to_vec();
    for (key, value) in overlay {
        entries = inserted(entries, key.clone(), value.clone());
    }
    let mut unioned_keys: Vec<&'static str> = Vec::new();
    for (key, tuple) in [(TAGS_KEY, false), (ROW_DIFF_EXCLUDE_COLUMNS_KEY, true)] {
        if let (Some(base_items), Some(overlay_items)) =
            (set_entry(base, key), set_entry(overlay, key))
        {
            let items: Vec<ConfigNode<H>> = merged_strings(base_items, overlay_items, text)?;
            let merged: ConfigNode<H> = if tuple {
                ConfigNode::Tuple(items)
            } else {
                ConfigNode::List(items)
            };
            entries = inserted(entries, ConfigNode::Str(key.to_owned()), merged);
            unioned_keys.push(key);
        }
    }
    if let (Some(base_tolerances), Some(overlay_tolerances)) = (
        set_entry(base, ROW_DIFF_TOLERANCES_KEY),
        set_entry(overlay, ROW_DIFF_TOLERANCES_KEY),
    ) {
        entries = inserted(
            entries,
            ConfigNode::Str(ROW_DIFF_TOLERANCES_KEY.to_owned()),
            merged_tolerances(base_tolerances, overlay_tolerances),
        );
        if base_tolerances.kind() == NodeKind::Map && overlay_tolerances.kind() == NodeKind::Map {
            unioned_keys.push(ROW_DIFF_TOLERANCES_KEY);
        }
    }
    Ok(LayeredConfig {
        entries,
        unioned_keys,
    })
}
