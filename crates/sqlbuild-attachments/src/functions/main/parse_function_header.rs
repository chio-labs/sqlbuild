//! Python's SQL and Python function header parsing, before template expansion.

use crate::functions::_helpers::values::{
    TABLE_RETURN_KEY, description, lookup, named_types, stripped_list, stripped_text,
};
use crate::functions::models::{
    FunctionHeader, FunctionLanguage, FunctionReturns, HeaderValue, NamedType,
};

/// The parsed header, or None wherever Python raises for its shape.
#[must_use]
pub fn parse_function_header(
    header: &[(String, HeaderValue)],
    language: FunctionLanguage,
) -> Option<FunctionHeader> {
    let returns: FunctionReturns = match (language, lookup(header, "returns")?) {
        (_, HeaderValue::Text(_)) => {
            FunctionReturns::Type(stripped_text(lookup(header, "returns"))?)
        }
        (FunctionLanguage::Sql, HeaderValue::Map(entries)) => table_returns(entries)?,
        _ => return None,
    };
    let arguments: Vec<NamedType> = match lookup(header, "arguments") {
        None => Vec::new(),
        Some(HeaderValue::Map(entries)) => named_types(entries)?,
        Some(_) => return None,
    };
    let python: bool = language == FunctionLanguage::Python;
    Some(FunctionHeader {
        arguments,
        returns,
        runtime_version: if python {
            Some(stripped_text(lookup(header, "runtime_version"))?)
        } else {
            None
        },
        entry_point: if python {
            Some(stripped_text(lookup(header, "entry_point"))?)
        } else {
            None
        },
        packages: if python {
            stripped_list(lookup(header, "packages"))?
        } else {
            Vec::new()
        },
        tags: stripped_list(lookup(header, "tags"))?,
        description: description(lookup(header, "description"))?,
    })
}

/// Python's `returns (table (...))`: exactly the `table` key with a non-empty column map.
fn table_returns(entries: &[(HeaderValue, HeaderValue)]) -> Option<FunctionReturns> {
    let [(HeaderValue::Text(key), HeaderValue::Map(columns))] = entries else {
        return None;
    };
    if key != TABLE_RETURN_KEY || columns.is_empty() {
        return None;
    }
    Some(FunctionReturns::Table(named_types(columns)?))
}
