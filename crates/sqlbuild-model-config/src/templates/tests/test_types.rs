use std::cell::RefCell;

use crate::templates::models::{ContextValue, Scalar, StringExpansion, TemplateFailure};
use crate::templates::types::TemplateHost;

/// A template value standing in for the Python objects the bindings evaluate.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Value {
    Null,
    Bool(bool),
    Text(String),
    /// A value only Python can render, such as a float or a mapping.
    Opaque,
}

/// Fixed variables, environment and context, recording reads like the Python resolver.
pub(super) struct TestHost {
    pub(super) variables: Vec<(&'static str, Value)>,
    pub(super) environment: Vec<(&'static str, &'static str)>,
    pub(super) context: Vec<(&'static str, Option<&'static str>)>,
    pub(super) reads: RefCell<Vec<String>>,
}

impl TemplateHost for TestHost {
    type Value = Value;

    fn variable(&self, name: &str) -> Result<Option<Value>, TemplateFailure> {
        Ok(self
            .variables
            .iter()
            .find(|(key, _)| *key == name)
            .map(|(_, value)| value.clone()))
    }

    fn environment(&self, name: &str) -> Result<Option<Value>, TemplateFailure> {
        self.reads.borrow_mut().push(format!("ENV:{name}"));
        Ok(self
            .environment
            .iter()
            .find(|(key, _)| *key == name)
            .map(|(_, value)| Value::Text((*value).to_owned())))
    }

    fn context(&self, name: &str) -> Result<ContextValue<Value>, TemplateFailure> {
        self.reads.borrow_mut().push(format!("CTX:{name}"));
        Ok(match self.context.iter().find(|(key, _)| *key == name) {
            None => ContextValue::Unknown,
            Some((_, None)) => ContextValue::Unavailable,
            Some((_, Some(value))) => ContextValue::Value(Value::Text((*value).to_owned())),
        })
    }

    fn text(&self, text: &str) -> Result<Value, TemplateFailure> {
        Ok(Value::Text(text.to_owned()))
    }

    fn boolean(&self, flag: bool) -> Result<Value, TemplateFailure> {
        Ok(Value::Bool(flag))
    }

    fn null(&self) -> Value {
        Value::Null
    }

    fn scalar(&self, value: &Value) -> Option<Scalar> {
        match value {
            Value::Null => Some(Scalar::Null),
            Value::Bool(flag) => Some(Scalar::Bool(*flag)),
            Value::Text(text) => Some(Scalar::Text(text.clone())),
            Value::Opaque => None,
        }
    }
}

/// One template string, its expansion and the reads it records.
pub(super) struct TemplateTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected: Result<StringExpansion<Value>, TemplateFailure>,
    pub(super) expected_reads: &'static [&'static str],
}
