//! `parse_audit_instances`: an authored audit list, with or without null read as empty.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::audits::audit_list;
use crate::header_metadata::_helpers::text::Site;
use crate::header_metadata::models::ParsedAudit;
use crate::types::{AuthoredNode, NodeKind};

/// Parse the audits `label` declares in the file at `path`; null is empty only when asked.
pub fn parse_audit_list<N: AuthoredNode>(
    audits: Option<&N>,
    path: &str,
    label: &str,
    null_as_empty: bool,
) -> Result<Vec<ParsedAudit<N>>, ConfigError> {
    let site: Site<'_> = Site {
        path,
        label,
        column: None,
    };
    match audits {
        None => Ok(Vec::new()),
        Some(node) if node.kind() == NodeKind::Null && !null_as_empty => {
            Err(site.error("audits must be a list"))
        }
        Some(node) => audit_list(node, site),
    }
}
