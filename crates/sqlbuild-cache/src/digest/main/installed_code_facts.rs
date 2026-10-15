//! The installed distribution versions and editable flag behind the installed code identity.

use std::path::PathBuf;

use crate::digest::_helpers::distributions::{
    distribution_directory, distribution_version, optional_bytes,
};
use crate::digest::constants::{
    CODE_IDENTITY_DISTRIBUTIONS, DIRECT_URL_FILE, SQLBUILD_DISTRIBUTION, UNKNOWN_VERSION,
};

/// Each identity distribution's version along `search_paths`, and whether SQLBuild is editable.
#[must_use]
pub fn installed_code_facts(search_paths: &[PathBuf]) -> (Vec<String>, bool) {
    let versions: Vec<String> = CODE_IDENTITY_DISTRIBUTIONS
        .iter()
        .map(|name| {
            distribution_directory(search_paths, name)
                .and_then(|directory| distribution_version(&directory))
                .unwrap_or_else(|| UNKNOWN_VERSION.to_owned())
        })
        .collect();
    let editable: bool =
        distribution_directory(search_paths, SQLBUILD_DISTRIBUTION).is_none_or(|directory| {
            optional_bytes(&directory.join(DIRECT_URL_FILE))
                .is_some_and(|bytes| editable_direct_url(&bytes))
        });
    (versions, editable)
}

/// Whether `direct_url.json` marks an editable install; unreadable payloads count as editable.
fn editable_direct_url(bytes: &[u8]) -> bool {
    let Ok(payload) = serde_json::from_slice::<serde_json::Value>(bytes) else {
        return true;
    };
    let Some(payload) = payload.as_object() else {
        return true;
    };
    payload
        .get("dir_info")
        .and_then(serde_json::Value::as_object)
        .and_then(|dir_info| dir_info.get("editable"))
        .is_some_and(|editable| editable == &serde_json::Value::Bool(true))
}
