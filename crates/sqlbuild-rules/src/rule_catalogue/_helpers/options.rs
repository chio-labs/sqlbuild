//! Python `isinstance` and equality semantics over option values.

use crate::rule_catalogue::constants::OBJECT_TYPE;
use crate::rule_catalogue::models::{OptionKind, OptionValue};

/// `isinstance(value, kind)`, where `bool` is a subclass of `int`.
pub(crate) fn is_instance(value: &OptionValue, kind: &OptionKind) -> bool {
    match (kind, value) {
        (OptionKind::Bool, OptionValue::Bool(_))
        | (OptionKind::Int, OptionValue::Int(_) | OptionValue::Bool(_))
        | (OptionKind::Str, OptionValue::Str(_))
        | (OptionKind::Tuple, OptionValue::Tuple(_)) => true,
        (OptionKind::Other(name), _) if name == OBJECT_TYPE => true,
        (OptionKind::Other(name), OptionValue::Other(type_name)) => name == type_name,
        _ => false,
    }
}

/// Whether `value` has the declared type, where a bool is not an `int` value.
pub(crate) fn has_value_type(value: &OptionValue, kind: &OptionKind) -> bool {
    is_instance(value, kind)
        && !(matches!(kind, OptionKind::Int) && matches!(value, OptionValue::Bool(_)))
}

/// Python `==` between two option values, where `True == 1`.
pub(crate) fn python_equal(left: &OptionValue, right: &OptionValue) -> bool {
    match (left, right) {
        (OptionValue::Bool(a), OptionValue::Bool(b)) => a == b,
        (OptionValue::Int(a), OptionValue::Int(b)) => a == b,
        (OptionValue::Bool(a), OptionValue::Int(b))
        | (OptionValue::Int(b), OptionValue::Bool(a)) => i64::from(*a) == *b,
        (OptionValue::Str(a), OptionValue::Str(b)) => a == b,
        (OptionValue::Tuple(a), OptionValue::Tuple(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(x, y)| python_equal(x, y))
        }
        _ => false,
    }
}

/// The integer value Python's `isinstance(value, int) and not isinstance(value, bool)` admits.
pub(crate) fn plain_integer(value: &OptionValue) -> Option<i64> {
    match value {
        OptionValue::Int(integer) => Some(*integer),
        _ => None,
    }
}
