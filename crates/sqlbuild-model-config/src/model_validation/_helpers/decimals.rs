//! `decimal.Decimal(text)` as CPython's `_decimal` reads a string, and exact comparison.

use std::cmp::Ordering;

use sqlbuild_core::text::main::is_python_decimal::is_python_decimal;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;

/// A finite decimal: its sign, its digits without leading zeros, and its exponent.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct FiniteDecimal {
    negative: bool,
    digits: String,
    exponent: i64,
}

/// What `Decimal(text)` gives.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum DecimalText {
    Finite(FiniteDecimal),
    /// `Infinity`, `NaN` or `sNaN`, which no integer equals.
    Special,
    /// `InvalidOperation`: the text is no decimal.
    Invalid,
    /// A digit outside ASCII that Python would read; SQLBuild asks for ASCII digits.
    NonAsciiDigit,
}

const SPECIAL_NAMES: [&str; 4] = ["inf", "infinity", "nan", "snan"];

/// Read `text` as `Decimal(text)`: Python whitespace around it and every `_` are ignored.
pub(crate) fn decimal_text(python: PythonText, text: &str) -> DecimalText {
    let trimmed: &str = text.trim_matches(is_python_space);
    if trimmed
        .chars()
        .any(|character| !character.is_ascii() && is_python_decimal(python, character))
    {
        return DecimalText::NonAsciiDigit;
    }
    let ascii: String = trimmed
        .chars()
        .filter(|character| *character != '_')
        .collect();
    if !ascii.is_ascii() {
        return DecimalText::Invalid;
    }
    parse_ascii(&ascii)
}

fn parse_ascii(text: &str) -> DecimalText {
    let unsigned: &str = text.strip_prefix(['+', '-']).unwrap_or(text);
    let negative: bool = text.starts_with('-');
    let lowered: String = unsigned.to_ascii_lowercase();
    let special_payload = |name: &str| {
        lowered
            .strip_prefix(name)
            .is_some_and(|payload| payload.bytes().all(|byte| byte.is_ascii_digit()))
    };
    if SPECIAL_NAMES[..2].contains(&lowered.as_str()) || special_payload("snan") {
        return DecimalText::Special;
    }
    if special_payload("nan") {
        return DecimalText::Special;
    }
    let (mantissa, exponent_text) = match unsigned.find(['e', 'E']) {
        Some(at) => (&unsigned[..at], Some(&unsigned[at + 1..])),
        None => (unsigned, None),
    };
    let (whole, fraction) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    let all_digits = |part: &str| part.bytes().all(|byte| byte.is_ascii_digit());
    if (whole.is_empty() && fraction.is_empty()) || !all_digits(whole) || !all_digits(fraction) {
        return DecimalText::Invalid;
    }
    let exponent: i64 = match exponent_text {
        None => 0,
        Some(exponent) => {
            let digits: &str = exponent.strip_prefix(['+', '-']).unwrap_or(exponent);
            if digits.is_empty() || !all_digits(digits) {
                return DecimalText::Invalid;
            }
            match exponent.parse::<i64>() {
                Ok(value) => value,
                Err(_) => return DecimalText::Invalid,
            }
        }
    };
    let Ok(places) = i64::try_from(fraction.len()) else {
        return DecimalText::Invalid;
    };
    let Some(exponent) = exponent.checked_sub(places) else {
        return DecimalText::Invalid;
    };
    let digits: String = format!("{whole}{fraction}")
        .trim_start_matches('0')
        .to_owned();
    DecimalText::Finite(FiniteDecimal {
        negative: negative && !digits.is_empty(),
        digits,
        exponent,
    })
}

impl FiniteDecimal {
    /// The decimal of a Python `int`.
    pub(crate) fn integer(value: i64) -> Self {
        let digits: String = value
            .unsigned_abs()
            .to_string()
            .trim_start_matches('0')
            .to_owned();
        Self {
            negative: value < 0,
            digits,
            exponent: 0,
        }
    }

    /// Whether `value == int(value)`.
    pub(crate) fn is_integral(&self) -> bool {
        self.exponent >= 0
            || usize::try_from(self.exponent.unsigned_abs()).is_ok_and(|places| {
                self.digits.len() <= places && self.digits.bytes().all(|byte| byte == b'0')
                    || self.digits.len() > places
                        && self.digits[self.digits.len() - places..]
                            .bytes()
                            .all(|byte| byte == b'0')
            })
    }

    /// Compare two decimals by value.
    pub(crate) fn compare(&self, other: &Self) -> Ordering {
        match (self.digits.is_empty(), other.digits.is_empty()) {
            (true, true) => return Ordering::Equal,
            (true, false) => {
                return if other.negative {
                    Ordering::Greater
                } else {
                    Ordering::Less
                };
            }
            (false, true) => {
                return if self.negative {
                    Ordering::Less
                } else {
                    Ordering::Greater
                };
            }
            (false, false) => {}
        }
        if self.negative != other.negative {
            return if self.negative {
                Ordering::Less
            } else {
                Ordering::Greater
            };
        }
        let magnitude: Ordering = self.magnitude_order(other);
        if self.negative {
            magnitude.reverse()
        } else {
            magnitude
        }
    }

    fn magnitude_order(&self, other: &Self) -> Ordering {
        let adjusted = |decimal: &Self| {
            i128::from(decimal.exponent) + i128::try_from(decimal.digits.len()).unwrap_or(0)
        };
        adjusted(self).cmp(&adjusted(other)).then_with(|| {
            let left: &str = self.digits.trim_end_matches('0');
            let right: &str = other.digits.trim_end_matches('0');
            left.cmp(right)
        })
    }
}
