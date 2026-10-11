//! Python's `str(expand_template_data(...))` over project variables, the environment and context.

use std::cell::{Cell, RefCell};

use sqlbuild_model_config::templates::errors::TemplateError;
use sqlbuild_model_config::templates::main::expand_template_string::expand_template_string;
use sqlbuild_model_config::templates::main::template_error_message::template_error_message;
use sqlbuild_model_config::templates::models::{
    ContextValue, Scalar, StringExpansion, TemplateFailure, TemplateOptions,
};
use sqlbuild_model_config::templates::types::TemplateHost;

use crate::assembly::project::constants::{
    PROJECT_VAR_FALSE, PROJECT_VAR_TRUE, PYTHON_FALSE, PYTHON_NONE, PYTHON_TRUE,
    TEMPLATE_OPEN_TOKEN, UNLISTED_ENVIRONMENT,
};
use crate::assembly::project::errors::AssemblyError;
use crate::assembly::project::models::{InputRead, OpaqueRender, OpaqueVariable, Variable};
use crate::assembly::project::types::Fact;

/// Context values by name; None is a known key whose value Python holds as None.
pub(crate) type Context<'a> = [(&'static str, Option<String>)];

/// The variables and environment target templates read, and every lookup they make in order.
pub(crate) struct TemplateInputs<'a> {
    pub(crate) variables: &'a [(String, Variable)],
    /// Python's `os.environ.get` of each name the templates may read.
    pub(crate) environment: &'a [(String, Option<String>)],
    pub(crate) reads: RefCell<Vec<InputRead>>,
}

/// One evaluated value: a scalar, or a variable value only Python renders.
#[derive(Clone)]
enum TargetValue {
    Scalar(Scalar),
    Opaque(OpaqueVariable),
}

/// One expansion's inputs, context values and the label its errors name.
struct TargetHost<'a> {
    inputs: &'a TemplateInputs<'a>,
    context: &'a Context<'a>,
    label: &'a str,
    /// Why the host stopped evaluation: the exception Python raises, or an internal failure.
    stopped: Cell<Option<AssemblyError>>,
}

impl TargetHost<'_> {
    fn stop(&self, error: AssemblyError) -> TemplateFailure {
        self.stopped.set(Some(error));
        TemplateFailure::Host
    }
}

impl TemplateHost for TargetHost<'_> {
    type Value = TargetValue;

    fn variable(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        Ok(self
            .inputs
            .variables
            .iter()
            .find(|(variable, _)| variable == name)
            .map(|(_, value)| match value {
                Variable::Scalar(value) => TargetValue::Scalar(value.clone()),
                Variable::Opaque(value) => TargetValue::Opaque(value.clone()),
            }))
    }

    fn environment(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        self.inputs
            .reads
            .borrow_mut()
            .push(InputRead::Environment(name.to_owned()));
        match self
            .inputs
            .environment
            .iter()
            .find(|(variable, _)| variable == name)
        {
            None => Err(self.stop(AssemblyError::Internal(format!(
                "{UNLISTED_ENVIRONMENT} '{name}'"
            )))),
            Some((_, value)) => Ok(value
                .clone()
                .map(|text| TargetValue::Scalar(Scalar::Text(text)))),
        }
    }

    fn context(&self, name: &str) -> Result<ContextValue<Self::Value>, TemplateFailure> {
        self.inputs
            .reads
            .borrow_mut()
            .push(InputRead::Context(name.to_owned()));
        Ok(match self.context.iter().find(|(key, _)| *key == name) {
            None => ContextValue::Unknown,
            Some((_, None)) => ContextValue::Unavailable,
            Some((_, Some(value))) => {
                ContextValue::Value(TargetValue::Scalar(Scalar::Text(value.clone())))
            }
        })
    }

    fn text(&self, text: &str) -> Result<Self::Value, TemplateFailure> {
        Ok(TargetValue::Scalar(Scalar::Text(text.to_owned())))
    }

    fn boolean(&self, flag: bool) -> Result<Self::Value, TemplateFailure> {
        Ok(TargetValue::Scalar(Scalar::Bool(flag)))
    }

    fn null(&self) -> Self::Value {
        TargetValue::Scalar(Scalar::Null)
    }

    fn scalar(&self, value: &Self::Value) -> Result<Scalar, TemplateFailure> {
        Ok(match value {
            TargetValue::Scalar(value) => value.clone(),
            TargetValue::Opaque(value) => Scalar::Text(value.text.clone()),
        })
    }

    fn render(&self, value: &Self::Value, label: &str) -> Result<String, TemplateFailure> {
        match value {
            TargetValue::Scalar(Scalar::Null) => Ok(String::new()),
            TargetValue::Scalar(Scalar::Bool(true)) => Ok(PROJECT_VAR_TRUE.to_owned()),
            TargetValue::Scalar(Scalar::Bool(false)) => Ok(PROJECT_VAR_FALSE.to_owned()),
            TargetValue::Scalar(Scalar::Text(text)) => Ok(text.clone()),
            TargetValue::Opaque(value) => match &value.render {
                OpaqueRender::Text(text) => Ok(text.clone()),
                OpaqueRender::Rejected(rest) => Err(TemplateFailure::Invalid(
                    TemplateError::Message(format!("{label}{rest}")),
                )),
                OpaqueRender::Raises(index) => Err(self.stop(AssemblyError::Raise(*index))),
            },
        }
    }

    fn label(&self) -> &str {
        self.label
    }
}

/// `str(expand_template_data(value=text, context_label=label, ...))`; context only where Some.
pub(crate) fn expanded_text(
    text: &str,
    inputs: &TemplateInputs<'_>,
    context: Option<&Context<'_>>,
    label: &str,
) -> Fact<String> {
    if !text.contains(TEMPLATE_OPEN_TOKEN) {
        return Ok(text.to_owned());
    }
    let options = TemplateOptions {
        allow_context: context.is_some(),
        preserve_context_tokens: false,
        preserve_unknown_context: false,
    };
    let host = TargetHost {
        inputs,
        context: context.unwrap_or_default(),
        label,
        stopped: Cell::new(None),
    };
    match expand_template_string(&host, text, options) {
        Ok(StringExpansion::Unchanged) => Ok(text.to_owned()),
        Ok(StringExpansion::Value(value)) => Ok(python_str(value)),
        Ok(StringExpansion::Text(expanded)) => Ok(expanded),
        Err(TemplateFailure::Missing(error) | TemplateFailure::Invalid(error)) => {
            Err(AssemblyError::CompileInput {
                message: template_error_message(&error, label),
                help: None,
            })
        }
        Err(TemplateFailure::Host) => Err(host.stopped.take().unwrap_or_else(|| {
            AssemblyError::Internal("template expansion stopped without an error".to_owned())
        })),
    }
}

/// Python's `str()` of a value.
fn python_str(value: TargetValue) -> String {
    match value {
        TargetValue::Scalar(Scalar::Null) => PYTHON_NONE.to_owned(),
        TargetValue::Scalar(Scalar::Bool(true)) => PYTHON_TRUE.to_owned(),
        TargetValue::Scalar(Scalar::Bool(false)) => PYTHON_FALSE.to_owned(),
        TargetValue::Scalar(Scalar::Text(text)) => text,
        TargetValue::Opaque(value) => value.text,
    }
}
