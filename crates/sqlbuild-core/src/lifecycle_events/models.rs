//! Lifecycle event definitions and the JSON payload values validation reads.

/// The validation contract of one catalogued lifecycle event type.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EventDefinition {
    pub event_type: &'static str,
    pub required_correlations: &'static [&'static str],
    pub required_payload: &'static [&'static str],
    pub allowed_payload: &'static [&'static str],
    pub terminal: bool,
}

/// One frozen JSON payload value.
#[derive(Clone, Debug, PartialEq)]
pub enum PayloadValue {
    Null,
    Bool(bool),
    /// An integer, saturated into `i128`, with its exact decimal text.
    Integer {
        value: i128,
        text: String,
    },
    Float(f64),
    Text(String),
    Array(Vec<PayloadValue>),
    Object(Vec<(String, PayloadValue)>),
}

/// The envelope facts of one lifecycle event that catalogue validation reads.
#[derive(Clone, Debug, PartialEq)]
pub struct KnownEventFacts {
    pub schema_version: i64,
    pub event_type: String,
    /// Each correlation field name with whether it is set.
    pub correlations: Vec<(&'static str, bool)>,
    pub payload: Vec<(String, PayloadValue)>,
}
