//! `parse_column_encoding`: how a stored column's ClickHouse type is written.

use crate::clickhouse::_helpers::digits::leading_number;
use crate::clickhouse::constants::MAX_DATETIME64_PRECISION;
use crate::clickhouse::models::ColumnEncoding;

/// The encoding and nullability of `type_text`, `None` for a type Recall never creates.
#[must_use]
pub fn parse_column_encoding(type_text: &str) -> Option<(ColumnEncoding, bool)> {
    let text: &str = type_text.trim();
    if let Some(inner) = text
        .strip_prefix("Nullable(")
        .and_then(|rest| rest.strip_suffix(')'))
    {
        return parse_column_encoding(inner)
            .filter(|(_, nullable)| !nullable)
            .map(|(encoding, _)| (encoding, true));
    }
    let encoding = match text {
        "String" => ColumnEncoding::String,
        "Int64" => ColumnEncoding::Int64,
        "Float64" => ColumnEncoding::Float64,
        "UInt8" | "Bool" => ColumnEncoding::UInt8,
        _ => {
            let arguments: &str = text.strip_prefix("DateTime64(")?;
            let precision: u64 = leading_number(arguments)?;
            if precision > MAX_DATETIME64_PRECISION {
                return None;
            }
            ColumnEncoding::DateTime64(precision)
        }
    };
    Some((encoding, false))
}
