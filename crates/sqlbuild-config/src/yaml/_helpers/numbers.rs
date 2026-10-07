//! PyYAML's `construct_yaml_int` and `construct_yaml_float` with Python's integer sizes.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::yaml::constants::{PYTHON_INT_MAX_STR_DIGITS, SEXAGESIMAL_BASE, ZERO_TEXT};

const LIMB_BASE: u64 = 1_000_000_000;
const LIMB_DIGITS: usize = 9;

/// A non-negative arbitrary-precision integer in base 10^9 limbs, least significant first.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct Natural {
    limbs: Vec<u32>,
}

impl Natural {
    fn multiply_add(self, factor: u32, addend: u32) -> Self {
        let mut carry = u64::from(addend);
        let mut limbs: Vec<u32> = self
            .limbs
            .into_iter()
            .map(|limb| {
                let total = u64::from(limb) * u64::from(factor) + carry;
                carry = total / LIMB_BASE;
                u32::try_from(total % LIMB_BASE).unwrap_or_default()
            })
            .collect();
        while carry > 0 {
            limbs.push(u32::try_from(carry % LIMB_BASE).unwrap_or_default());
            carry /= LIMB_BASE;
        }
        Self { limbs }
    }

    fn add(self, other: &Self) -> Self {
        let length = self.limbs.len().max(other.limbs.len());
        let mut carry = 0_u64;
        let mut limbs: Vec<u32> = (0..length)
            .map(|index| {
                let total = u64::from(self.limbs.get(index).copied().unwrap_or_default())
                    + u64::from(other.limbs.get(index).copied().unwrap_or_default())
                    + carry;
                carry = total / LIMB_BASE;
                u32::try_from(total % LIMB_BASE).unwrap_or_default()
            })
            .collect();
        if carry > 0 {
            limbs.push(u32::try_from(carry).unwrap_or_default());
        }
        Self { limbs }
    }

    fn decimal(&self) -> String {
        let mut limbs = self.limbs.iter().rev().skip_while(|limb| **limb == 0);
        let Some(first) = limbs.next() else {
            return "0".to_owned();
        };
        limbs.fold(first.to_string(), |text, limb| {
            format!("{text}{limb:0LIMB_DIGITS$}")
        })
    }
}

fn construct_error(message: String) -> ConfigError {
    ConfigError::new(ConfigErrorKind::Construct, message)
}

/// Python's `int(text, radix)` for the ASCII inputs PyYAML passes after removing underscores.
fn python_int(text: &str, radix: u32) -> Result<(bool, Natural), ConfigError> {
    let trimmed = text.trim_matches(|character: char| character.is_ascii_whitespace());
    let (negative, unsigned) = match trimmed.as_bytes().first() {
        Some(b'-') => (true, &trimmed[1..]),
        Some(b'+') => (false, &trimmed[1..]),
        _ => (false, trimmed),
    };
    let prefix = match radix {
        2 => ["0b", "0B"],
        8 => ["0o", "0O"],
        16 => ["0x", "0X"],
        _ => ["", ""],
    };
    let digits = prefix
        .iter()
        .filter(|prefix| !prefix.is_empty())
        .find_map(|prefix| unsigned.strip_prefix(prefix))
        .unwrap_or(unsigned);
    if digits.is_empty() {
        return Err(construct_error(format!(
            "invalid literal for int() with base {radix}: {text:?}"
        )));
    }
    let mut value = Natural::default();
    for character in digits.chars() {
        let Some(digit) = character.to_digit(radix) else {
            return Err(construct_error(format!(
                "invalid literal for int() with base {radix}: {text:?}"
            )));
        };
        value = value.multiply_add(radix, digit);
    }
    Ok((negative, value))
}

fn integer_value(negative: bool, value: &Natural) -> ConfigValue {
    let decimal = value.decimal();
    let signed = if negative && decimal != ZERO_TEXT {
        format!("-{decimal}")
    } else {
        decimal
    };
    match signed.parse::<i64>() {
        Ok(small) => ConfigValue::Integer(small),
        Err(_) => ConfigValue::BigInteger(signed),
    }
}

fn split_sign(text: &str) -> Result<(bool, &str), ConfigError> {
    match text.as_bytes().first() {
        None => Err(construct_error("string index out of range".to_owned())),
        Some(b'-') => Ok((true, &text[1..])),
        Some(b'+') => Ok((false, &text[1..])),
        Some(_) => Ok((false, text)),
    }
}

/// PyYAML's `construct_yaml_int`, including binary, octal, hexadecimal and base 60.
pub(crate) fn construct_int(text: &str) -> Result<ConfigValue, ConfigError> {
    let cleaned = text.replace('_', "");
    let (negative, value) = split_sign(&cleaned)?;
    if value.len() > PYTHON_INT_MAX_STR_DIGITS {
        return Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            "integers longer than Python's string conversion limit are left to Python",
        ));
    }
    let (inner_negative, magnitude) = if value == ZERO_TEXT {
        (false, Natural::default())
    } else if let Some(binary) = value.strip_prefix("0b") {
        python_int(binary, 2)?
    } else if let Some(hexadecimal) = value.strip_prefix("0x") {
        python_int(hexadecimal, 16)?
    } else if value.starts_with('0') {
        python_int(value, 8)?
    } else if value.contains(':') {
        value
            .split(':')
            .try_fold((false, Natural::default()), |(_, total), part| {
                let (part_negative, digit) = python_int(part, 10)?;
                if part_negative {
                    return Err(construct_error(
                        "negative sexagesimal digits are left to Python".to_owned(),
                    ));
                }
                Ok((false, total.multiply_add(SEXAGESIMAL_BASE, 0).add(&digit)))
            })?
    } else {
        python_int(value, 10)?
    };
    Ok(integer_value(negative != inner_negative, &magnitude))
}

/// Python's `float(text)` for the ASCII inputs PyYAML passes.
fn python_float(text: &str) -> Result<f64, ConfigError> {
    text.trim_matches(|character: char| character.is_ascii_whitespace())
        .parse::<f64>()
        .map_err(|_| construct_error(format!("could not convert string to float: {text:?}")))
}

/// Base-60 digits summed from the least significant one, in PyYAML's floating-point order.
fn sexagesimal_float(text: &str) -> Result<f64, ConfigError> {
    let digits = text
        .split(':')
        .map(python_float)
        .collect::<Result<Vec<_>, _>>()?;
    let (total, _) = digits
        .iter()
        .rev()
        .fold((0.0, 1.0), |(total, base), digit| {
            (total + digit * base, base * f64::from(SEXAGESIMAL_BASE))
        });
    Ok(total)
}

/// PyYAML's `construct_yaml_float`, including `.inf`, `.nan` and base 60.
pub(crate) fn construct_float(text: &str) -> Result<ConfigValue, ConfigError> {
    let cleaned = text.replace('_', "").to_lowercase();
    let (negative, value) = split_sign(&cleaned)?;
    let sign = if negative { -1.0 } else { 1.0 };
    let magnitude = match value {
        ".inf" => f64::INFINITY,
        ".nan" => return Ok(ConfigValue::Float(f64::NAN)),
        _ if value.contains(':') => sexagesimal_float(value)?,
        _ => python_float(value)?,
    };
    Ok(ConfigValue::Float(sign * magnitude))
}
