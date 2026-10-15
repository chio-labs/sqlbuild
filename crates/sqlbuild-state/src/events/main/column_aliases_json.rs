//! `column_aliases_json`: the stored text of an old-name view's column aliases.

use std::collections::BTreeMap;

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::events::constants::{ALIAS_ITEM_SEPARATOR, ALIAS_KEY_SEPARATOR};

/// Compact sorted ASCII JSON of `dict(aliases)`, or `None` when there are no aliases.
pub fn column_aliases_json(aliases: &[(String, String)]) -> Result<Option<String>, JsonEmitError> {
    if aliases.is_empty() {
        return Ok(None);
    }
    let mapping: BTreeMap<&str, &str> = aliases
        .iter()
        .map(|(old, new)| (old.as_str(), new.as_str()))
        .collect();
    let value = JsonValue::Object(
        mapping
            .into_iter()
            .map(|(old, new)| (old.to_owned(), JsonValue::String(new.to_owned())))
            .collect(),
    );
    let options = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(ALIAS_ITEM_SEPARATOR, ALIAS_KEY_SEPARATOR)
    };
    dumps(&value, &JsonDialect::Stdlib(options)).map(Some)
}
