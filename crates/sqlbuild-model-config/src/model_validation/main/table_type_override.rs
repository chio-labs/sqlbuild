//! Read a MODEL header's `table_type` as `resolve_table_type` does.

use crate::model_validation::_helpers::config::optional_text;
use crate::model_validation::constants::{
    INHERIT_POLICY, PERMANENT_TABLE_TYPE, TRANSIENT_TABLE_TYPE,
};
use crate::model_validation::models::{Rejected, TableTypeOverride};
use crate::types::AuthoredNode;

/// Return the header table-type override, or reject a value Python refuses.
pub fn table_type_override<N: AuthoredNode>(
    value: Option<&N>,
) -> Result<TableTypeOverride, Rejected> {
    match optional_text(value)?.as_deref() {
        None | Some(INHERIT_POLICY) => Ok(TableTypeOverride::Inherit),
        Some(PERMANENT_TABLE_TYPE) => Ok(TableTypeOverride::Permanent),
        Some(TRANSIENT_TABLE_TYPE) => Ok(TableTypeOverride::Transient),
        Some(_) => Err(Rejected),
    }
}
