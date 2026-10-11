use crate::json::models::{JsonInteger, JsonValue};

fn string(text: &str) -> JsonValue {
    JsonValue::String(text.to_owned())
}

fn integer(text: &str) -> JsonValue {
    JsonValue::Integer(JsonInteger::parse(text).expect("test integers are decimal"))
}

/// A value exercising escapes, big integers, float layouts, empty containers and key order.
pub(super) fn sample_document(largest_integer: &str) -> JsonValue {
    let floats = [0.1, -0.0, 1e16, 1e-5, 2.5e-7, 1e15, 100.0];
    JsonValue::Object(vec![
        ("name".to_owned(), string("café ☕ 😀")),
        ("control".to_owned(), string("\u{0}\u{1f}\u{7f}\t\n\"\\/")),
        (
            "ints".to_owned(),
            JsonValue::Array(vec![
                integer("0"),
                integer("-1"),
                integer("9223372036854775808"),
                integer(largest_integer),
            ]),
        ),
        (
            "floats".to_owned(),
            JsonValue::Array(floats.into_iter().map(JsonValue::Float).collect()),
        ),
        (
            "empty".to_owned(),
            JsonValue::Array(vec![JsonValue::Object(vec![]), JsonValue::Array(vec![])]),
        ),
        ("z".to_owned(), JsonValue::Null),
        ("a".to_owned(), JsonValue::Bool(true)),
    ])
}

pub(super) fn non_finite_floats() -> JsonValue {
    JsonValue::Array(vec![
        JsonValue::Float(f64::NAN),
        JsonValue::Float(f64::INFINITY),
        JsonValue::Float(f64::NEG_INFINITY),
    ])
}

/// An integer written with `count` decimal digits.
pub(super) fn digits(count: usize) -> JsonValue {
    integer(&"9".repeat(count))
}

/// `depth` arrays nested inside one another.
pub(super) fn nested_arrays(depth: usize) -> JsonValue {
    (1..depth).fold(JsonValue::Array(Vec::new()), |inner, _| {
        JsonValue::Array(vec![inner])
    })
}

/// `"q"\` then a lone low surrogate, a non-BMP pair, and a lone high surrogate, as UTF-16.
pub(super) fn lone_surrogate_text() -> JsonValue {
    JsonValue::Utf16(vec![
        0x0022, 0x0071, 0x0022, 0x005c, 0x00e9, 0xdcff, 0xd83d, 0xde00, 0xd83d,
    ])
}

/// `inner` wrapped in `depth` single-item lists.
pub(super) fn wrapped_in_arrays(depth: usize, inner: JsonValue) -> JsonValue {
    (0..depth).fold(inner, |value, _| JsonValue::Array(vec![value]))
}

/// Run `check` on a thread with room for Python-depth recursion.
pub(super) fn on_large_stack(check: impl FnOnce() -> bool + Send + 'static) -> bool {
    std::thread::Builder::new()
        .stack_size(LARGE_STACK_BYTES)
        .spawn(check)
        .expect("test thread")
        .join()
        .expect("test thread result")
}

const LARGE_STACK_BYTES: usize = 256 * 1024 * 1024;
