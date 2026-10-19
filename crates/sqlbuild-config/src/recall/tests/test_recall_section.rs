use crate::models::ConfigValue;
use crate::recall::main::recall_section::recall_section;
use crate::recall::models::RecallSection;

fn table(entries: &[(&str, ConfigValue)]) -> ConfigValue {
    ConfigValue::Map(
        entries
            .iter()
            .map(|(key, value)| (ConfigValue::String((*key).to_owned()), value.clone()))
            .collect(),
    )
}

fn text(value: &str) -> ConfigValue {
    ConfigValue::String(value.to_owned())
}

#[test]
fn given_every_key_when_validated_then_settings_are_typed() {
    let section = recall_section(
        &table(&[
            ("enabled", ConfigValue::Bool(false)),
            ("connection", text(" history ")),
            ("retention", text("720h")),
            ("shutdown_timeout", text("1500ms")),
            ("diagnostics_min_severity", text("debug")),
        ]),
        "recall",
    );
    assert_eq!(
        section,
        Ok(RecallSection {
            enabled: Some(false),
            connection: Some("history".to_owned()),
            retention_days: Some(30),
            shutdown_timeout_ms: Some(1500),
            diagnostics_min_severity: Some("debug".to_owned()),
        })
    );
}

#[test]
fn given_invalid_values_when_validated_then_the_message_names_the_key() {
    let cases: [(&str, ConfigValue, &str); 6] = [
        (
            "unknown key",
            table(&[("mode", text("x"))]),
            "recall contains unknown key(s): mode",
        ),
        (
            "bad retention",
            table(&[("retention", text("30x"))]),
            "recall.retention must be",
        ),
        (
            "hours not days",
            table(&[("retention", text("25h"))]),
            "recall.retention must be",
        ),
        (
            "zero days",
            table(&[("retention", text("0d"))]),
            "recall.retention must be",
        ),
        (
            "timeout too long",
            table(&[("shutdown_timeout", text("601s"))]),
            "recall.shutdown_timeout must be",
        ),
        (
            "severity",
            table(&[("diagnostics_min_severity", text("loud"))]),
            "recall.diagnostics_min_severity must be one of",
        ),
    ];
    for (description, value, expected) in cases {
        let message = recall_section(&value, "recall").expect_err(description);
        assert!(message.starts_with(expected), "{description}: {message}");
    }
    assert_eq!(
        recall_section(&text("x"), "targets.dev.recall"),
        Err("targets.dev.recall must be a table".to_owned())
    );
}
