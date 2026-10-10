//! Python's `str(expand_template_data(...))` over scalar variables, the environment and context.

use std::cell::RefCell;

use sqlbuild_model_config::templates::main::expand_template_string::expand_template_string;
use sqlbuild_model_config::templates::models::{
    ContextValue, Scalar, StringExpansion, TemplateFailure, TemplateOptions,
};
use sqlbuild_model_config::templates::types::TemplateHost;

use crate::assembly::project::constants::{
    PROJECT_VAR_FALSE, PROJECT_VAR_TRUE, PYTHON_FALSE, PYTHON_NONE, PYTHON_TRUE, TEMPLATE_DEFERRAL,
    TEMPLATE_LABEL, TEMPLATE_OPEN_TOKEN,
};
use crate::assembly::project::models::{InputRead, Variable};
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

/// One expansion's inputs and context values.
struct ScalarHost<'a> {
    inputs: &'a TemplateInputs<'a>,
    context: &'a Context<'a>,
}

impl TemplateHost for ScalarHost<'_> {
    type Value = Scalar;

    fn variable(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        match self
            .inputs
            .variables
            .iter()
            .find(|(variable, _)| variable == name)
        {
            None => Ok(None),
            Some((_, Variable::Scalar(value))) => Ok(Some(value.clone())),
            Some((_, Variable::Unsupported)) => Err(TemplateFailure::Host),
        }
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
            None => Err(TemplateFailure::Host),
            Some((_, value)) => Ok(value.clone().map(Scalar::Text)),
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
            Some((_, Some(value))) => ContextValue::Value(Scalar::Text(value.clone())),
        })
    }

    fn text(&self, text: &str) -> Result<Self::Value, TemplateFailure> {
        Ok(Scalar::Text(text.to_owned()))
    }

    fn boolean(&self, flag: bool) -> Result<Self::Value, TemplateFailure> {
        Ok(Scalar::Bool(flag))
    }

    fn null(&self) -> Self::Value {
        Scalar::Null
    }

    fn scalar(&self, value: &Self::Value) -> Result<Scalar, TemplateFailure> {
        Ok(value.clone())
    }

    fn render(&self, value: &Self::Value, _label: &str) -> Result<String, TemplateFailure> {
        Ok(match value {
            Scalar::Null => String::new(),
            Scalar::Bool(true) => PROJECT_VAR_TRUE.to_owned(),
            Scalar::Bool(false) => PROJECT_VAR_FALSE.to_owned(),
            Scalar::Text(text) => text.clone(),
        })
    }

    fn label(&self) -> &str {
        TEMPLATE_LABEL
    }
}

/// `str(expand_template_data(value=text, ...))`; context is allowed only where Some.
pub(crate) fn expanded_text(
    text: &str,
    inputs: &TemplateInputs<'_>,
    context: Option<&Context<'_>>,
) -> Fact<String> {
    if !text.contains(TEMPLATE_OPEN_TOKEN) {
        return Ok(text.to_owned());
    }
    let options = TemplateOptions {
        allow_context: context.is_some(),
        preserve_context_tokens: false,
        preserve_unknown_context: false,
    };
    let host = ScalarHost {
        inputs,
        context: context.unwrap_or_default(),
    };
    match expand_template_string(&host, text, options) {
        Ok(StringExpansion::Unchanged) => Ok(text.to_owned()),
        Ok(StringExpansion::Value(value)) => Ok(python_str(value)),
        Ok(StringExpansion::Text(expanded)) => Ok(expanded),
        Err(_) => Err(TEMPLATE_DEFERRAL.to_owned()),
    }
}

/// Python's `str()` of a scalar.
fn python_str(value: Scalar) -> String {
    match value {
        Scalar::Null => PYTHON_NONE.to_owned(),
        Scalar::Bool(true) => PYTHON_TRUE.to_owned(),
        Scalar::Bool(false) => PYTHON_FALSE.to_owned(),
        Scalar::Text(text) => text,
    }
}
