//! `recall_section`: validate one Recall settings table.

use crate::models::ConfigValue;
use crate::recall::_helpers::values::{non_empty, output_bytes, retention_days, timeout_ms};
use crate::recall::constants::{
    MAX_RETENTION_DAYS, RECALL_KEYS, RECALL_SEVERITIES, REMOVED_CONNECTION_KEY,
};
use crate::recall::models::RecallSection;

/// The settings of `value`, or the message naming its first problem at `label`.
pub fn recall_section(value: &ConfigValue, label: &str) -> Result<RecallSection, String> {
    let Some(entries) = value.as_map() else {
        return Err(format!("{label} must be a table"));
    };
    let mut section = RecallSection::default();
    for (key, value) in entries {
        let ConfigValue::String(key) = key else {
            return Err(format!("{label} keys must be strings"));
        };
        match key.as_str() {
            "enabled" => match value {
                ConfigValue::Bool(flag) => section.enabled = Some(*flag),
                _ => return Err(format!("{label}.enabled must be true or false")),
            },
            "write_connection" => {
                section.write_connection = Some(non_empty(value, label, key)?.to_owned());
            }
            "read_connection" => {
                section.read_connection = Some(non_empty(value, label, key)?.to_owned());
            }
            REMOVED_CONNECTION_KEY => return Err(removed_connection(value, label)),
            "retention" => {
                let text = non_empty(value, label, key)?;
                section.retention_days = Some(retention_days(text).ok_or_else(|| {
                    format!(
                        "{label}.retention must be a whole number of days such as '30d', \
                         at most {MAX_RETENTION_DAYS}d"
                    )
                })?);
            }
            "shutdown_timeout" => {
                let text = non_empty(value, label, key)?;
                section.shutdown_timeout_ms = Some(timeout_ms(text).ok_or_else(|| {
                    format!(
                        "{label}.shutdown_timeout must be a duration such as '3s' or '500ms', \
                         at most 600s"
                    )
                })?);
            }
            "max_output_bytes" => {
                section.max_output_bytes = Some(output_bytes(value).ok_or_else(|| {
                    format!(
                        "{label}.max_output_bytes must be a whole number of bytes, such as \
                         2097152, or 0 to record all output"
                    )
                })?);
            }
            "diagnostics_min_severity" => {
                let text = non_empty(value, label, key)?;
                if !RECALL_SEVERITIES.contains(&text) {
                    return Err(format!(
                        "{label}.diagnostics_min_severity must be one of: {}",
                        RECALL_SEVERITIES.join(", ")
                    ));
                }
                section.diagnostics_min_severity = Some(text.to_owned());
            }
            other => {
                return Err(format!(
                    "{label} contains unknown key(s): {other}. Allowed keys: {}",
                    RECALL_KEYS.join(", ")
                ));
            }
        }
    }
    Ok(section)
}

/// The message for the removed `connection` key, naming its replacements.
fn removed_connection(value: &ConfigValue, label: &str) -> String {
    let name: String = match value {
        ConfigValue::String(name) if !name.trim().is_empty() => name.trim().to_owned(),
        _ => "<name>".to_owned(),
    };
    format!(
        "{label}.connection was replaced by write_connection and read_connection: set \
         write_connection = \"{name}\" and read_connection = \"{name}\" (or a separate \
         read-only connection), or only read_connection to read shared history while this \
         machine records to the local store"
    )
}
