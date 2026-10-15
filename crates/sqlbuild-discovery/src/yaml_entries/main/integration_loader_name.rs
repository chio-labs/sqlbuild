//! The loader name a declarative integration source runs under.

use crate::yaml_entries::constants::DLT_LOADER_KIND;

/// The source name for dlt sources, `<kind>__<source>` for every other integration.
pub fn integration_loader_name(kind: &str, source_name: &str) -> String {
    if kind == DLT_LOADER_KIND {
        source_name.to_owned()
    } else {
        format!("{kind}__{source_name}")
    }
}
