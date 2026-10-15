//! Python `Decimal` arithmetic in the default context: 28 digits, `ROUND_HALF_EVEN`.

use std::cmp::Ordering;

#[cfg(test)]
use crate::cost_allocation::constants::SMALLEST_PLAIN_LEFT_DIGITS;
use crate::cost_allocation::constants::{DECIMAL_PRECISION, HALF_DIGIT, MAX_DIGIT};
use crate::cost_allocation::models::PyDecimal;
use crate::json::main::python_float_repr::python_float_repr;

/// Digits without leading zeros; zero is `[0]`.
fn normalized(mut digits: Vec<u8>) -> Vec<u8> {
    let leading: usize = digits.iter().take_while(|digit| **digit == 0).count();
    digits.drain(..leading.min(digits.len().saturating_sub(1)));
    if digits.is_empty() {
        digits.push(0);
    }
    digits
}

fn is_zero(digits: &[u8]) -> bool {
    digits.iter().all(|digit| *digit == 0)
}

/// An exact integer as a decimal with exponent zero.
pub(crate) fn integer(value: u64) -> PyDecimal {
    PyDecimal {
        digits: value.to_string().bytes().map(|byte| byte - b'0').collect(),
        exponent: 0,
    }
}

/// A signed decimal exponent such as `+16` or `-06`.
fn exponent_value(text: &str) -> Option<i64> {
    let (negative, digits): (bool, &str) = match text.as_bytes().first() {
        Some(b'-') => (true, &text[1..]),
        Some(b'+') => (false, &text[1..]),
        _ => (false, text),
    };
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let magnitude: i64 = digits.bytes().fold(0_i64, |value, byte| {
        value
            .saturating_mul(10)
            .saturating_add(i64::from(byte - b'0'))
    });
    Some(if negative { -magnitude } else { magnitude })
}

/// `Decimal(text)` for plain decimal or scientific text of a non-negative finite number.
pub(crate) fn parse(text: &str) -> Option<PyDecimal> {
    let (mantissa, exponent): (&str, i64) = match text.find(['e', 'E']) {
        Some(index) => (&text[..index], exponent_value(&text[index + 1..])?),
        None => (text, 0),
    };
    let (whole, fraction): (&str, &str) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    if whole.is_empty() && fraction.is_empty() {
        return None;
    }
    let digits: Vec<u8> = whole
        .bytes()
        .chain(fraction.bytes())
        .map(|byte| byte.is_ascii_digit().then(|| byte - b'0'))
        .collect::<Option<_>>()?;
    let fraction_length: i64 = i64::try_from(fraction.len()).unwrap_or(i64::MAX);
    Some(PyDecimal {
        digits: normalized(digits),
        exponent: exponent - fraction_length,
    })
}

/// Round to the context precision with `ROUND_HALF_EVEN`, as `Decimal._fix` does.
pub(crate) fn rounded(digits: Vec<u8>, exponent: i64) -> PyDecimal {
    let digits: Vec<u8> = normalized(digits);
    if digits.len() <= DECIMAL_PRECISION {
        return PyDecimal { digits, exponent };
    }
    let dropped: usize = digits.len() - DECIMAL_PRECISION;
    let mut kept: Vec<u8> = digits[..DECIMAL_PRECISION].to_vec();
    let rest: &[u8] = &digits[DECIMAL_PRECISION..];
    let round_up: bool = match rest[0].cmp(&HALF_DIGIT) {
        Ordering::Greater => true,
        Ordering::Less => false,
        Ordering::Equal => !is_zero(&rest[1..]) || kept[DECIMAL_PRECISION - 1] % 2 == 1,
    };
    let mut exponent: i64 = exponent + i64::try_from(dropped).unwrap_or(i64::MAX);
    if round_up {
        let mut index: usize = kept.len();
        loop {
            if index == 0 {
                kept.insert(0, 1);
                break;
            }
            index -= 1;
            if kept[index] == MAX_DIGIT {
                kept[index] = 0;
            } else {
                kept[index] += 1;
                break;
            }
        }
        if kept.len() > DECIMAL_PRECISION {
            kept.pop();
            exponent += 1;
        }
    }
    PyDecimal {
        digits: kept,
        exponent,
    }
}

fn shifted(value: &PyDecimal, exponent: i64) -> Vec<u8> {
    let zeros: usize = usize::try_from(value.exponent - exponent).unwrap_or(0);
    let mut digits: Vec<u8> = value.digits.clone();
    digits.extend(std::iter::repeat_n(0, zeros));
    digits
}

/// `left + right`.
pub(crate) fn add(left: &PyDecimal, right: &PyDecimal) -> PyDecimal {
    let exponent: i64 = left.exponent.min(right.exponent);
    let (mut first, mut second) = (shifted(left, exponent), shifted(right, exponent));
    let width: usize = first.len().max(second.len()) + 1;
    first.splice(0..0, std::iter::repeat_n(0, width - first.len()));
    second.splice(0..0, std::iter::repeat_n(0, width - second.len()));
    let mut carry: u8 = 0;
    let mut sum: Vec<u8> = vec![0; width];
    for index in (0..width).rev() {
        let total: u8 = first[index] + second[index] + carry;
        sum[index] = total % 10;
        carry = total / 10;
    }
    rounded(sum, exponent)
}

/// `left * right`.
pub(crate) fn multiply(left: &PyDecimal, right: &PyDecimal) -> PyDecimal {
    let mut product: Vec<u32> = vec![0; left.digits.len() + right.digits.len()];
    for (left_index, left_digit) in left.digits.iter().enumerate().rev() {
        for (right_index, right_digit) in right.digits.iter().enumerate().rev() {
            product[left_index + right_index + 1] +=
                u32::from(*left_digit) * u32::from(*right_digit);
        }
    }
    for index in (1..product.len()).rev() {
        product[index - 1] += product[index] / 10;
        product[index] %= 10;
    }
    let digits: Vec<u8> = product
        .into_iter()
        .map(|digit| u8::try_from(digit).unwrap_or(0))
        .collect();
    rounded(digits, left.exponent + right.exponent)
}

/// Quotient and remainder of a digit string divided by a small positive integer.
fn divide_digits(digits: &[u8], divisor: u64) -> (Vec<u8>, bool) {
    let mut remainder: u128 = 0;
    let mut quotient: Vec<u8> = Vec::with_capacity(digits.len());
    for digit in digits {
        remainder = remainder * 10 + u128::from(*digit);
        quotient.push(u8::try_from(remainder / u128::from(divisor)).unwrap_or(0));
        remainder %= u128::from(divisor);
    }
    (normalized(quotient), remainder != 0)
}

fn last_digit(digits: &[u8]) -> u8 {
    digits.last().copied().unwrap_or(0)
}

/// `dividend / Decimal(divisor)` for a positive integer divisor, as `Decimal.__truediv__`.
pub(crate) fn divide(dividend: &PyDecimal, divisor: u64) -> PyDecimal {
    if is_zero(&dividend.digits) {
        return PyDecimal {
            digits: vec![0],
            exponent: dividend.exponent,
        };
    }
    let divisor_length: i64 = i64::try_from(divisor.to_string().len()).unwrap_or(0);
    let dividend_length: i64 = i64::try_from(dividend.digits.len()).unwrap_or(0);
    let precision: i64 = i64::try_from(DECIMAL_PRECISION).unwrap_or(0);
    let shift: i64 = divisor_length - dividend_length + precision + 1;
    let mut exponent: i64 = dividend.exponent - shift;
    let (mut quotient, inexact) = if shift >= 0 {
        let mut digits: Vec<u8> = dividend.digits.clone();
        digits.extend(std::iter::repeat_n(0, usize::try_from(shift).unwrap_or(0)));
        divide_digits(&digits, divisor)
    } else {
        let split: usize = dividend.digits.len() - usize::try_from(-shift).unwrap_or(0);
        let (high, low) = dividend.digits.split_at(split);
        let (quotient, remainder) = divide_digits(high, divisor);
        (quotient, remainder || !is_zero(low))
    };
    if inexact {
        if last_digit(&quotient).is_multiple_of(HALF_DIGIT) {
            let index: usize = quotient.len() - 1;
            quotient[index] += 1;
        }
    } else {
        while exponent < dividend.exponent && quotient.len() > 1 && last_digit(&quotient) == 0 {
            quotient.pop();
            exponent += 1;
        }
    }
    rounded(quotient, exponent)
}

/// Numeric order of two decimals, ignoring their exponents' representation.
pub(crate) fn compare(left: &PyDecimal, right: &PyDecimal) -> Ordering {
    match (is_zero(&left.digits), is_zero(&right.digits)) {
        (true, true) => return Ordering::Equal,
        (true, false) => return Ordering::Less,
        (false, true) => return Ordering::Greater,
        (false, false) => {}
    }
    let adjusted = |value: &PyDecimal| -> i64 {
        value.exponent + i64::try_from(value.digits.len()).unwrap_or(0)
    };
    adjusted(left).cmp(&adjusted(right)).then_with(|| {
        let width: usize = left.digits.len().max(right.digits.len());
        let padded = |digits: &[u8]| -> Vec<u8> {
            let mut padded: Vec<u8> = digits.to_vec();
            padded.resize(width, 0);
            padded
        };
        padded(&left.digits).cmp(&padded(&right.digits))
    })
}

/// `str(Decimal)`: scientific notation when the exponent is positive or the value is tiny.
#[cfg(test)]
pub(crate) fn text(value: &PyDecimal) -> String {
    let digits: String = value
        .digits
        .iter()
        .map(|digit| char::from(b'0' + digit))
        .collect();
    let length: i64 = i64::try_from(digits.len()).unwrap_or(0);
    let left_digits: i64 = value.exponent + length;
    let dot_place: i64 = if value.exponent <= 0 && left_digits > SMALLEST_PLAIN_LEFT_DIGITS {
        left_digits
    } else {
        1
    };
    let (integer_part, fraction_part): (String, String) = if dot_place <= 0 {
        (
            "0".to_owned(),
            format!(
                ".{}{digits}",
                "0".repeat(usize::try_from(-dot_place).unwrap_or(0))
            ),
        )
    } else if dot_place >= length {
        (
            format!(
                "{digits}{}",
                "0".repeat(usize::try_from(dot_place - length).unwrap_or(0))
            ),
            String::new(),
        )
    } else {
        let split: usize = usize::try_from(dot_place).unwrap_or(0);
        (digits[..split].to_owned(), format!(".{}", &digits[split..]))
    };
    let suffix: String = if left_digits == dot_place {
        String::new()
    } else {
        format!("E{:+}", left_digits - dot_place)
    };
    format!("{integer_part}{fraction_part}{suffix}")
}

/// `Decimal(str(value))` for a non-negative finite float; `None` for NaN or infinities.
pub(crate) fn from_float(value: f64) -> Option<PyDecimal> {
    parse(&python_float_repr(value))
}
