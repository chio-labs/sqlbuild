//! How an edit changed one model file's header.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::header_changes::_helpers::references::references_read;
use crate::header_changes::constants::{MATERIALIZED_KEY, PATCHED_KEYS, PATCHED_MATERIALIZATIONS};
use crate::header_changes::main::header_key_digests::header_key_digests;
use crate::header_changes::models::HeaderChange;
use crate::header_changes::types::HeaderKeys;
use crate::model_files::main::model_file_options::model_file_options;
use crate::model_files::main::parse_model_text::parse_model_text;

/// How the header of the model file at `path` changed against its recorded keys.
#[must_use]
pub fn header_change(
    project_dir: &Path,
    relative_path: &str,
    (stored, upstream): (Option<&HeaderKeys>, &[(String, String)]),
) -> HeaderChange {
    let Some(stored) = stored else {
        return HeaderChange::Unsupported(format!("{relative_path} has no recorded header"));
    };
    let Ok(contents) = std::fs::read_to_string(project_dir.join(relative_path)) else {
        return HeaderChange::Unparsed;
    };
    let file_path: String = project_dir
        .join(relative_path)
        .to_string_lossy()
        .into_owned();
    let Ok(parsed) = parse_model_text(
        &file_path,
        contents,
        &model_file_options((false, false), None),
    ) else {
        return HeaderChange::Unparsed;
    };
    if !references_read(&parsed.query_sql, upstream) {
        return HeaderChange::Unsupported(format!("{relative_path} changed what it references"));
    }
    let current: HeaderKeys = header_key_digests(&parsed.header_values);
    let stored_map: BTreeMap<&str, &str> = stored
        .iter()
        .map(|(key, digest)| (key.as_str(), digest.as_str()))
        .collect();
    let current_map: BTreeMap<&str, &str> = current
        .iter()
        .map(|(key, digest)| (key.as_str(), digest.as_str()))
        .collect();
    let changed: BTreeSet<String> = stored_map
        .keys()
        .chain(current_map.keys())
        .filter(|key| stored_map.get(*key) != current_map.get(*key))
        .map(|key| (*key).to_owned())
        .collect();
    if changed.is_empty() {
        return HeaderChange::Unchanged;
    }
    for key in &changed {
        if key == MATERIALIZED_KEY {
            let value = parsed.header_values.iter().find(|(name, _)| name == key);
            let supported: bool = matches!(
                value,
                Some((_, AuthoredValue::BareWord(word) | AuthoredValue::String(word)))
                    if PATCHED_MATERIALIZATIONS.contains(&word.as_str())
            );
            if !supported {
                return HeaderChange::Unsupported(format!(
                    "{relative_path} changed its materialization beyond views and tables"
                ));
            }
        } else if !PATCHED_KEYS.contains(&key.as_str()) {
            return HeaderChange::Unsupported(format!(
                "{relative_path} changed its {key} header key"
            ));
        }
    }
    HeaderChange::Patched(changed)
}
