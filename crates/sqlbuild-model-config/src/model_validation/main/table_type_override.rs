//! Read a MODEL header's `table_type` as `resolve_table_type` does.

use crate::errors::ConfigError;
use crate::model_validation::_helpers::config::text_if_string;
use crate::model_validation::constants::{
    INHERIT_POLICY, PERMANENT_TABLE_TYPE, TRANSIENT_TABLE_TYPE,
};
use crate::model_validation::models::{TableTypeOverride, ValidationStop};
use crate::types::{AuthoredNode, NodeKind};

/// Return the header table-type override, the error Python raises, or a deferral.
pub fn table_type_override<N: AuthoredNode>(
    value: Option<&N>,
    model_name: &str,
) -> Result<TableTypeOverride, ValidationStop> {
    let Some(value) = value.filter(|node| node.kind() != NodeKind::Null) else {
        return Ok(TableTypeOverride::Inherit);
    };
    match text_if_string(value)?.as_deref() {
        Some(INHERIT_POLICY) => Ok(TableTypeOverride::Inherit),
        Some(PERMANENT_TABLE_TYPE) => Ok(TableTypeOverride::Permanent),
        Some(TRANSIENT_TABLE_TYPE) => Ok(TableTypeOverride::Transient),
        _ => Err(ValidationStop::Error(ConfigError::compile(format!(
            "model '{model_name}': table_type must be permanent, transient, or inherit"
        )))),
    }
}
