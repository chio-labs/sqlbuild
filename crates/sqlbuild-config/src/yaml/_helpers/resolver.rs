//! PyYAML's YAML 1.1 implicit resolvers for plain scalars, without regular expressions.

use crate::yaml::_helpers::patterns::PatternCursor;

/// A plain-scalar matcher, the tag it resolves to, and the first characters PyYAML tries it for.
type ScalarResolver = (fn(&str) -> bool, &'static str, &'static str);
use crate::yaml::_helpers::timestamps::matches_implicit_timestamp;
use crate::yaml::constants::{
    BOOL_TAG, BOOL_WORDS, FLOAT_TAG, INT_TAG, MERGE_KEY, MERGE_TAG, NULL_TAG, NULL_WORDS, STR_TAG,
    TIMESTAMP_TAG, VALUE_KEY, VALUE_TAG,
};

fn is_digit(byte: u8) -> bool {
    byte.is_ascii_digit()
}

fn is_digit_or_underscore(byte: u8) -> bool {
    byte.is_ascii_digit() || byte == b'_'
}

fn matches_float(text: &str) -> bool {
    let alternatives: [fn(&mut PatternCursor<'_>) -> bool; 5] = [
        |cursor| {
            cursor.sign()
                && cursor.one(is_digit)
                && cursor.many(is_digit_or_underscore)
                && cursor.literal(".")
                && cursor.many(is_digit_or_underscore)
                && cursor.exponent()
        },
        |cursor| {
            cursor.literal(".")
                && cursor.one(is_digit)
                && cursor.many(is_digit_or_underscore)
                && cursor.exponent()
        },
        |cursor| {
            cursor.sign()
                && cursor.one(is_digit)
                && cursor.many(is_digit_or_underscore)
                && cursor.sexagesimal_groups()
                && cursor.literal(".")
                && cursor.many(is_digit_or_underscore)
        },
        |cursor| cursor.sign() && cursor.any_literal(&[".inf", ".Inf", ".INF"]),
        |cursor| cursor.any_literal(&[".nan", ".NaN", ".NAN"]),
    ];
    PatternCursor::matches_any(text, &alternatives)
}

fn matches_int(text: &str) -> bool {
    let alternatives: [fn(&mut PatternCursor<'_>) -> bool; 6] = [
        |cursor| {
            cursor.sign()
                && cursor.literal("0b")
                && cursor.some(|byte| matches!(byte, b'0' | b'1' | b'_'))
        },
        |cursor| {
            cursor.sign()
                && cursor.literal("0")
                && cursor.some(|byte| matches!(byte, b'0'..=b'7' | b'_'))
        },
        |cursor| cursor.sign() && cursor.literal("0"),
        |cursor| {
            cursor.sign()
                && cursor.one(|byte| matches!(byte, b'1'..=b'9'))
                && cursor.many(is_digit_or_underscore)
        },
        |cursor| {
            cursor.sign()
                && cursor.literal("0x")
                && cursor.some(|byte| byte.is_ascii_hexdigit() || byte == b'_')
        },
        |cursor| {
            cursor.sign()
                && cursor.one(|byte| matches!(byte, b'1'..=b'9'))
                && cursor.many(is_digit_or_underscore)
                && cursor.sexagesimal_groups()
        },
    ];
    PatternCursor::matches_any(text, &alternatives)
}

/// The tag PyYAML's `Resolver.resolve` gives a scalar; `implicit` is true for plain scalars.
pub(crate) fn resolve_scalar(value: &str, implicit: bool) -> &'static str {
    if !implicit {
        return STR_TAG;
    }
    let candidate = value.strip_suffix('\n').unwrap_or(value);
    let resolvers: [ScalarResolver; 7] = [
        (
            |text| BOOL_WORDS.iter().any(|(word, _)| *word == text),
            BOOL_TAG,
            "yYnNtTfFoO",
        ),
        (matches_float, FLOAT_TAG, "-+0123456789."),
        (matches_int, INT_TAG, "-+0123456789"),
        (|text| text == MERGE_KEY, MERGE_TAG, "<"),
        (|text| NULL_WORDS.contains(&text), NULL_TAG, "~nN"),
        (matches_implicit_timestamp, TIMESTAMP_TAG, "0123456789"),
        (|text| text == VALUE_KEY, VALUE_TAG, "="),
    ];
    let first = value.chars().next();
    resolvers
        .iter()
        .filter(|(_, tag, first_characters)| {
            first.map_or(*tag == NULL_TAG, |character| {
                first_characters.contains(character)
            })
        })
        .find(|(matches, _, _)| matches(candidate))
        .map_or(STR_TAG, |(_, tag, _)| tag)
}
