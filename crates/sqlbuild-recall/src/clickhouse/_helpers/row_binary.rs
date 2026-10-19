//! `RowBinary` encoding of one Recall value; each function takes the block and returns it extended.

use crate::clickhouse::constants::{
    DECIMAL_SCALE, MICROS_DIGITS, VARINT_CONTINUE, VARINT_MASK, VARINT_PAYLOAD_BITS,
};
use crate::clickhouse::models::{ColumnEncoding, StoredColumn};
use crate::records::main::timestamp_micros::timestamp_micros;
use crate::records::models::RecallValue;

fn varint(mut block: Vec<u8>, mut value: u64) -> Vec<u8> {
    loop {
        let byte = u8::try_from(value & VARINT_MASK).unwrap_or_default();
        value >>= VARINT_PAYLOAD_BITS;
        if value == 0 {
            block.push(byte);
            return block;
        }
        block.push(byte | VARINT_CONTINUE);
    }
}

fn bytes(block: Vec<u8>, data: &[u8]) -> Vec<u8> {
    let mut block = varint(block, u64::try_from(data.len()).unwrap_or(u64::MAX));
    block.extend_from_slice(data);
    block
}

/// `micros` scaled to `precision` fractional digits.
pub(crate) fn scaled(micros: i64, precision: u64) -> i64 {
    let mut value: i64 = micros;
    for _ in MICROS_DIGITS..precision {
        value = value.saturating_mul(DECIMAL_SCALE);
    }
    for _ in precision..MICROS_DIGITS {
        value /= DECIMAL_SCALE;
    }
    value
}

fn mismatch(column: &StoredColumn, expected: &str) -> String {
    format!(
        "Recall column {} holds a value that is not {expected}",
        column.name
    )
}

fn payload(block: Vec<u8>, column: &StoredColumn, value: &RecallValue) -> Result<Vec<u8>, String> {
    let mut block = block;
    match (column.encoding, value) {
        (ColumnEncoding::String, RecallValue::Text(text)) => {
            return Ok(bytes(block, text.as_bytes()));
        }
        (ColumnEncoding::String, RecallValue::Blob(data)) => return Ok(bytes(block, data)),
        (ColumnEncoding::String, RecallValue::Null) => return Ok(bytes(block, b"")),
        (ColumnEncoding::Int64, RecallValue::Integer(number)) => {
            block.extend_from_slice(&number.to_le_bytes());
        }
        (
            ColumnEncoding::Int64 | ColumnEncoding::UInt8 | ColumnEncoding::Float64,
            RecallValue::Null,
        ) => {
            let width: usize = if column.encoding == ColumnEncoding::UInt8 {
                1
            } else {
                8
            };
            block.extend(std::iter::repeat_n(0, width));
        }
        (ColumnEncoding::UInt8, RecallValue::Integer(number)) => block.push(u8::from(*number != 0)),
        (ColumnEncoding::Float64, RecallValue::Real(number)) => {
            block.extend_from_slice(&number.to_le_bytes());
        }
        (ColumnEncoding::Float64, RecallValue::Integer(number)) => {
            let real: f64 = *number as f64;
            block.extend_from_slice(&real.to_le_bytes());
        }
        (ColumnEncoding::DateTime64(precision), RecallValue::Text(text)) => {
            let micros = timestamp_micros(text).ok_or_else(|| mismatch(column, "a timestamp"))?;
            block.extend_from_slice(&scaled(micros, precision).to_le_bytes());
        }
        (ColumnEncoding::DateTime64(_), RecallValue::Null) => {
            block.extend_from_slice(&0_i64.to_le_bytes())
        }
        (ColumnEncoding::String, _) => return Err(mismatch(column, "text")),
        (ColumnEncoding::Int64 | ColumnEncoding::UInt8, _) => {
            return Err(mismatch(column, "an integer"));
        }
        (ColumnEncoding::Float64, _) => return Err(mismatch(column, "a number")),
        (ColumnEncoding::DateTime64(_), _) => return Err(mismatch(column, "a timestamp")),
    }
    Ok(block)
}

/// `block` with `value` appended as `column` stores it; `Err` names a value the column cannot hold.
pub(crate) fn encoded(
    block: Vec<u8>,
    column: &StoredColumn,
    value: &RecallValue,
) -> Result<Vec<u8>, String> {
    if !column.nullable {
        return payload(block, column, value);
    }
    let mut block = block;
    let missing: bool = matches!(value, RecallValue::Null);
    block.push(u8::from(missing));
    if missing {
        return Ok(block);
    }
    payload(block, column, value)
}
