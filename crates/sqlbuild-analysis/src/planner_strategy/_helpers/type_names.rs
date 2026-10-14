//! Cursor types of warehouse type names and Polyglot type arguments.

use serde_json::{Map, Value};

use crate::planner_strategy::constants::{INTEGER_TYPE_NAMES, TIMESTAMP_TYPE_NAMES};
use crate::planner_strategy::models::CursorType;

/// The cursor type of a known type name.
pub(crate) fn named_type(name: &str) -> Option<CursorType> {
    if TIMESTAMP_TYPE_NAMES.contains(&name) {
        return Some(CursorType::Timestamp);
    }
    INTEGER_TYPE_NAMES
        .contains(&name)
        .then_some(CursorType::Integer)
}

/// Python's `str()` of one parsed type argument, upper-cased.
pub(crate) fn argument(args: &Map<String, Value>, key: &str) -> String {
    match args.get(key) {
        None => String::new(),
        Some(Value::String(text)) => text.to_uppercase(),
        Some(Value::Null) => "NONE".to_owned(),
        Some(Value::Bool(flag)) => if *flag { "TRUE" } else { "FALSE" }.to_owned(),
        Some(other) => other.to_string().to_uppercase(),
    }
}
