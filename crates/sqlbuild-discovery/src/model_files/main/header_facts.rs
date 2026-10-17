//! What a model's native header values show, read as their Python projection reads.

use sqlbuild_model_config::config_presence::main::blocks_config_reuse::blocks_config_reuse;
use sqlbuild_model_config::config_presence::main::contains_template::contains_template;
use sqlbuild_model_config::config_presence::main::entry_macro_path::entry_macro_path;
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::ParsedColumn;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::model_files::_helpers::header_columns::{COLUMNS_KEY, NULL_VALUE, native_column};
use crate::model_files::_helpers::native_nodes::{NativeNode, dict_entries, exactly};
use crate::model_files::models::{EntryFacts, HeaderFacts, NativeColumn};

/// The header facts of one model's native authored values; `path` names it in parse messages.
#[must_use]
pub fn header_facts(values: &[(String, AuthoredValue)], path: &str) -> HeaderFacts {
    let entries: Vec<(&str, &AuthoredValue)> = dict_entries(values);
    let facts: Vec<(String, EntryFacts)> = entries
        .iter()
        .map(|&(key, value)| {
            let node: NativeNode<'_> = NativeNode::Value(value);
            (
                key.to_owned(),
                EntryFacts {
                    template: contains_template(&node),
                    macro_path: entry_macro_path(&NativeNode::Key(key), &node),
                    blocks_reuse: blocks_config_reuse(&node),
                },
            )
        })
        .collect();
    let columns: Option<Vec<NativeColumn>> = entries
        .iter()
        .find(|(key, _)| *key == COLUMNS_KEY)
        .map(|&(_, value)| value)
        .filter(|value| **value != AuthoredValue::Null)
        .and_then(|value| {
            let (metadata, exact) = exactly(|| {
                parse_header_metadata(
                    &NativeNode::Value(value),
                    &NativeNode::Value(&NULL_VALUE),
                    path,
                )
            });
            let Ok(columns) = metadata.columns else {
                return None;
            };
            let columns: Vec<ParsedColumn<NativeNode<'_>>> = exact.then_some(columns)?;
            Some(columns.iter().map(native_column).collect())
        });
    HeaderFacts {
        entries: facts,
        columns,
    }
}
