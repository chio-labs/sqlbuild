//! The discovery failure a YAML document the native reader rejects is reported as.

use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_config::errors::{ConfigError, ConfigErrorKind};

const UNSUPPORTED_HELP: &str = "SQLBuild reads plain YAML: block and flow mappings and \
                                sequences, plain and quoted scalars, literal and folded block \
                                scalars, anchors, aliases and merge keys. Rewrite this part in \
                                one of those forms.";

/// The failure of a document `file_path` names, at the error's position where known.
pub(crate) fn yaml_failure(
    file_path: &str,
    kind: FailureKind,
    error: ConfigError,
) -> DiscoveryFailure {
    let position: String = match (error.line, error.column) {
        (Some(line), Some(column)) => format!(" at line {line}, column {column}"),
        _ => String::new(),
    };
    match error.kind {
        ConfigErrorKind::Unsupported => DiscoveryFailure {
            kind,
            message: format!(
                "{file_path} uses YAML that SQLBuild does not support{position}: {}",
                error.message
            ),
            help: Some(UNSUPPORTED_HELP.to_owned()),
        },
        _ => DiscoveryFailure::new(
            kind,
            format!(
                "{file_path} contains invalid YAML{position}: {}",
                error.message
            ),
        ),
    }
}
