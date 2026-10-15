//! `CommandOutputRecord.__post_init__`: the command-output wire contract, field by field.

use crate::command_output::constants::{
    COMMAND_OUTPUT_LOSS_RECORD_TYPE, COMMAND_OUTPUT_RECORD_TYPE, CURRENT_SCHEMA_VERSION,
};
use crate::command_output::models::RecordShape;

fn at_least(name: &str, value: Option<i64>, minimum: i64) -> Result<i64, String> {
    value
        .filter(|value| *value >= minimum)
        .ok_or_else(|| format!("{name} must be an integer of at least {minimum}"))
}

/// The first contract violation, in the order Python checks fields.
pub fn validate_output_record(shape: &RecordShape) -> Result<(), String> {
    for (name, value) in &shape.identity {
        if value.as_deref().is_none_or(str::is_empty) {
            return Err(format!("{name} must be a non-empty string"));
        }
    }
    if let Some(run_id) = &shape.run_id
        && run_id.as_deref().is_none_or(str::is_empty)
    {
        return Err("run_id must be null or a non-empty string".to_owned());
    }
    if shape.sequence.is_none_or(|sequence| sequence < 0) {
        return Err("sequence must be a non-negative integer".to_owned());
    }
    if !shape.occurred_at_is_utc {
        return Err("occurred_at must be a timezone-aware UTC datetime".to_owned());
    }
    if !shape.stream_is_known {
        return Err("stream must be stdout or stderr".to_owned());
    }
    if !shape.message_is_text {
        return Err("message must be a string".to_owned());
    }
    let chunk_index = at_least("chunk_index", shape.chunk_index, 0)?;
    let chunk_count = at_least("chunk_count", shape.chunk_count, 1)?;
    let dropped = at_least("dropped_records", shape.dropped_records, 0)?;
    if chunk_index >= chunk_count {
        return Err("chunk_index must be less than chunk_count".to_owned());
    }
    if !shape.priority_is_known {
        return Err("priority must be bulk or terminal".to_owned());
    }
    match shape.record_type.as_deref() {
        Some(COMMAND_OUTPUT_RECORD_TYPE) if dropped != 0 => {
            return Err("command_output records must have zero dropped_records".to_owned());
        }
        Some(COMMAND_OUTPUT_LOSS_RECORD_TYPE) if dropped < 1 => {
            return Err("command_output_loss records must report dropped_records".to_owned());
        }
        Some(COMMAND_OUTPUT_RECORD_TYPE | COMMAND_OUTPUT_LOSS_RECORD_TYPE) => {}
        _ => return Err("record_type is unknown".to_owned()),
    }
    if shape.schema_version != Some(CURRENT_SCHEMA_VERSION) {
        return Err(format!("schema_version must be {CURRENT_SCHEMA_VERSION}"));
    }
    Ok(())
}
